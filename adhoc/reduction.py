"""Capture-avoiding beta reduction of quoted expression trees."""

from dataclasses import dataclass, fields, replace
from itertools import count

from .expression import ExpressionValue
from .syntax import (
    is_short_name,
    Assign, BackslashRef, Call, Diff, Fold, FuncDef, Import, Integral, Lambda, Limit, Node,
    NoOp, PyImport, Quote, Seq, SetBuilder, Var,
)


STEP_CAP = 10_000
_STATEMENTS = (Assign, FuncDef, Import, NoOp, PyImport, Seq)


class ReduceError(Exception):
    pass


@dataclass(frozen=True)
class _Bound(Node):
    index: int
    name: str
    spelling: str | None


def _children(node: Node, transform):
    changes = {}
    for field in fields(node):
        value = getattr(node, field.name)
        if isinstance(value, Node):
            changed = transform(value)
        elif isinstance(value, tuple):
            items = tuple(transform(item) if isinstance(item, Node) else item
                          for item in value)
            changed = (value if all(before is after for before, after in zip(value, items))
                       else items)
        else:
            continue
        if changed is not value:
            changes[field.name] = changed
    return replace(node, **changes) if changes else node


def _encode(node: Node, context: tuple[str, ...]) -> Node:
    if isinstance(node, _STATEMENTS):
        raise ReduceError("\\reduce needs an expression without statements")
    if isinstance(node, Quote):
        return node
    if isinstance(node, Var | BackslashRef):
        name = node.ch if isinstance(node, Var) else node.name
        if name in context:
            return _Bound(node.span, context.index(name), name, node.spelling)
        return node
    if isinstance(node, Lambda):
        return replace(node, body=_encode(node.body, tuple(reversed(node.params)) + context))
    if isinstance(node, Fold | Integral):
        return replace(node, bound=_encode(node.bound, context),
                       body=_encode(node.body, (node.var,) + context))
    if isinstance(node, Limit | Diff):
        return replace(node, point=_encode(node.point, context),
                       body=_encode(node.body, (node.var,) + context))
    if isinstance(node, SetBuilder):
        inner = (node.var,) + context
        return replace(node, domain=_encode(node.domain, context),
                       element=None if node.element is None else _encode(node.element, inner),
                       guards=tuple(_encode(g, inner) for g in node.guards))
    return _children(node, lambda child: _encode(child, context))


def _shift(node: Node, amount: int, depth: int = 0) -> Node:
    if isinstance(node, Quote):
        return node
    if isinstance(node, _Bound):
        return replace(node, index=node.index + amount) if node.index >= depth else node
    if isinstance(node, Lambda):
        return replace(node, body=_shift(node.body, amount, depth + len(node.params)))
    if isinstance(node, Fold | Integral):
        return replace(node, bound=_shift(node.bound, amount, depth),
                       body=_shift(node.body, amount, depth + 1))
    if isinstance(node, Limit | Diff):
        return replace(node, point=_shift(node.point, amount, depth),
                       body=_shift(node.body, amount, depth + 1))
    if isinstance(node, SetBuilder):
        return replace(node, domain=_shift(node.domain, amount, depth),
                       element=None if node.element is None
                       else _shift(node.element, amount, depth + 1),
                       guards=tuple(_shift(g, amount, depth + 1) for g in node.guards))
    return _children(node, lambda child: _shift(child, amount, depth))


def _substitute(node: Node, args: tuple[Node, ...], depth: int = 0) -> Node:
    if isinstance(node, Quote):
        return node
    if isinstance(node, _Bound):
        slot = node.index - depth
        if slot < 0:
            return node
        if slot < len(args):
            return _shift(args[-slot - 1], depth)
        return replace(node, index=node.index - len(args))
    if isinstance(node, Lambda):
        return replace(node, body=_substitute(node.body, args, depth + len(node.params)))
    if isinstance(node, Fold | Integral):
        return replace(node, bound=_substitute(node.bound, args, depth),
                       body=_substitute(node.body, args, depth + 1))
    if isinstance(node, Limit | Diff):
        return replace(node, point=_substitute(node.point, args, depth),
                       body=_substitute(node.body, args, depth + 1))
    if isinstance(node, SetBuilder):
        return replace(node, domain=_substitute(node.domain, args, depth),
                       element=None if node.element is None
                       else _substitute(node.element, args, depth + 1),
                       guards=tuple(_substitute(g, args, depth + 1) for g in node.guards))
    return _children(node, lambda child: _substitute(child, args, depth))


def _reduce_once(node: Node) -> tuple[Node, bool]:
    if isinstance(node, Quote):
        return node, False
    if isinstance(node, Call) and isinstance(node.head, Lambda):
        if node.kwargs:
            raise ReduceError("\\reduce cannot apply a lambda with keyword arguments")
        if len(node.args) != len(node.head.params):
            raise ReduceError(f"lambda takes {len(node.head.params)} arguments, "
                              f"got {len(node.args)}")
        return _substitute(node.head.body, node.args), True
    for field in fields(node):
        value = getattr(node, field.name)
        if isinstance(value, Node):
            updated, changed = _reduce_once(value)
            if changed:
                return replace(node, **{field.name: updated}), True
        elif isinstance(value, tuple):
            for index, item in enumerate(value):
                if isinstance(item, Node):
                    updated, changed = _reduce_once(item)
                    if changed:
                        items = value[:index] + (updated,) + value[index + 1:]
                        return replace(node, **{field.name: items}), True
    return node, False


def _free_names(node: Node) -> set[str]:
    if isinstance(node, Quote):
        return set()
    if isinstance(node, Var):
        return {node.ch}
    if isinstance(node, BackslashRef):
        return {node.name}
    names = set()
    for field in fields(node):
        value = getattr(node, field.name)
        if isinstance(value, Node):
            names.update(_free_names(value))
        elif isinstance(value, tuple):
            for item in value:
                if isinstance(item, Node):
                    names.update(_free_names(item))
    return names


def _all_names(node: Node) -> set[str]:
    names = set()
    if isinstance(node, Var):
        names.add(node.ch)
    elif isinstance(node, BackslashRef):
        names.add(node.name)
    elif isinstance(node, Lambda):
        names.update(node.params)
    elif isinstance(node, Fold | Limit | Diff | Integral | SetBuilder):
        names.add(node.var)
    for field in fields(node):
        value = getattr(node, field.name)
        if isinstance(value, Node):
            names.update(_all_names(value))
        elif isinstance(value, tuple):
            for item in value:
                if isinstance(item, Node):
                    names.update(_all_names(item))
    return names


def _letters(number: int) -> str:
    text = ""
    while True:
        number, digit = divmod(number, 26)
        text = chr(ord("a") + digit) + text
        if number == 0:
            return text
        number -= 1


def _reify(node: Node, context: tuple[tuple[str, str | None], ...], fresh) -> Node:
    if isinstance(node, Quote):
        return node
    if isinstance(node, _Bound):
        name, spelling = context[node.index]
        written = node.spelling if name == node.name else spelling
        if is_short_name(name):
            return Var(node.span, name, written)
        return BackslashRef(node.span, name, written)
    if isinstance(node, Lambda):
        names = []
        spellings = []
        forbidden = _free_names(node.body) | {name for name, _ in context}
        for index, name in enumerate(node.params):
            if name in forbidden:
                name = fresh()
                spelling = f"\\{name}"
            else:
                spelling = (node.param_spellings[index] if index < len(node.param_spellings)
                            else name if is_short_name(name) else f"\\{name}")
            names.append(name)
            spellings.append(spelling)
            forbidden.add(name)
        inner = tuple(reversed(tuple(zip(names, spellings)))) + context
        return replace(node, params=tuple(names), param_spellings=tuple(spellings),
                       body=_reify(node.body, inner, fresh))
    if isinstance(node, SetBuilder):
        scoped = tuple(p for p in (node.element, *node.guards) if p is not None)
        forbidden = set().union(*map(_free_names, scoped)) | {name for name, _ in context}
        name = fresh() if node.var in forbidden else node.var
        spelling = f"\\{name}" if name != node.var else node.var_spelling
        inner = ((name, spelling),) + context
        return replace(node, var=name, var_spelling=spelling,
                       domain=_reify(node.domain, context, fresh),
                       element=None if node.element is None
                       else _reify(node.element, inner, fresh),
                       guards=tuple(_reify(g, inner, fresh) for g in node.guards))
    if isinstance(node, Fold | Limit | Diff | Integral):
        forbidden = _free_names(node.body) | {name for name, _ in context}
        name = fresh() if node.var in forbidden else node.var
        spelling = f"\\{name}" if name != node.var else node.var_spelling
        inner = ((name, spelling),) + context
        if isinstance(node, Fold | Integral):
            return replace(node, var=name, var_spelling=spelling,
                           bound=_reify(node.bound, context, fresh),
                           body=_reify(node.body, inner, fresh))
        return replace(node, var=name, var_spelling=spelling,
                       point=_reify(node.point, context, fresh),
                       body=_reify(node.body, inner, fresh))
    return _children(node, lambda child: _reify(child, context, fresh))


def reduce_expression(value: ExpressionValue) -> ExpressionValue:
    if value.statement_body:
        raise ReduceError("\\reduce needs an expression quote")
    node = _encode(value.node, ())
    # TODO: Each beta step rescans the AST; use a zipper if large terms matter.
    for steps in range(STEP_CAP + 1):
        node, changed = _reduce_once(node)
        if not changed:
            break
        if steps == STEP_CAP:
            raise ReduceError(f"\\reduce exceeded {STEP_CAP} beta steps")
    used = _all_names(node)
    numbers = count()

    def fresh() -> str:
        while True:
            name = "reduce_" + _letters(next(numbers))
            if name not in used:
                used.add(name)
                return name

    return ExpressionValue(_reify(node, (), fresh), value.source)
