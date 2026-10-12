"""Capture-avoiding beta reduction of quoted expression trees."""

from dataclasses import dataclass, fields, replace
from itertools import count

from .expression import ExpressionValue
from .syntax import (
    is_short_name, free_names,
    Assign, BackslashRef, Call, Diff, Fold, FuncDef, Import, Integral, Graph, Lambda, Limit, Node,
    NoOp, PyImport, Quote, Seq, SetBuilder, Generator, Var,
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


def _diff_order(node: Node, transform) -> dict:
    return {"order": transform(node.order)} if isinstance(node, Diff) and node.order is not None else {}


def _builder(node, context, transform, enter):
    clauses = []
    for clause in node.clauses:
        if isinstance(clause, Generator):
            clauses.append(replace(clause, domain=transform(clause.domain, context)))
            context = enter(context, clause.var)
        else:
            clauses.append(replace(clause, test=transform(clause.test, context)))
    return replace(node, clauses=tuple(clauses), element=None if node.element is None
                   else transform(node.element, context))


def _graph(node, context, transform, enter):
    inner = enter(context, node.axis.name) if node.expression_mode else context
    return replace(node, target=transform(node.target, inner),
                   axis=replace(node.axis, value=transform(node.axis.value, context)),
                   options=tuple(replace(kw, value=transform(kw.value, context))
                                 for kw in node.options))


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
    if isinstance(node, Graph):
        return _graph(node, context, _encode, lambda ctx, name: (name,) + ctx)
    if isinstance(node, Lambda):
        return replace(node, body=_encode(node.body, tuple(reversed(node.params)) + context))
    if isinstance(node, Fold | Integral):
        return replace(node, bound=_encode(node.bound, context),
                       body=_encode(node.body, (node.var,) + context))
    if isinstance(node, Limit | Diff):
        return replace(node, point=_encode(node.point, context),
                       body=_encode(node.body, (node.var,) + context),
                       **_diff_order(node, lambda child: _encode(child, context)))
    if isinstance(node, SetBuilder):
        return _builder(node, context, _encode, lambda ctx, name: (name,) + ctx)
    return _children(node, lambda child: _encode(child, context))


def _shift(node: Node, amount: int, depth: int = 0) -> Node:
    if isinstance(node, Quote):
        return node
    if isinstance(node, _Bound):
        return replace(node, index=node.index + amount) if node.index >= depth else node
    if isinstance(node, Graph):
        return _graph(node, depth, lambda child, level: _shift(child, amount, level),
                      lambda level, name: level + 1)
    if isinstance(node, Lambda):
        return replace(node, body=_shift(node.body, amount, depth + len(node.params)))
    if isinstance(node, Fold | Integral):
        return replace(node, bound=_shift(node.bound, amount, depth),
                       body=_shift(node.body, amount, depth + 1))
    if isinstance(node, Limit | Diff):
        return replace(node, point=_shift(node.point, amount, depth),
                       body=_shift(node.body, amount, depth + 1),
                       **_diff_order(node, lambda child: _shift(child, amount, depth)))
    if isinstance(node, SetBuilder):
        return _builder(node, depth, lambda child, level: _shift(child, amount, level),
                        lambda level, name: level + 1)
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
    if isinstance(node, Graph):
        return _graph(node, depth, lambda child, level: _substitute(child, args, level),
                      lambda level, name: level + 1)
    if isinstance(node, Lambda):
        return replace(node, body=_substitute(node.body, args, depth + len(node.params)))
    if isinstance(node, Fold | Integral):
        return replace(node, bound=_substitute(node.bound, args, depth),
                       body=_substitute(node.body, args, depth + 1))
    if isinstance(node, Limit | Diff):
        return replace(node, point=_substitute(node.point, args, depth),
                       body=_substitute(node.body, args, depth + 1),
                       **_diff_order(node, lambda child: _substitute(child, args, depth)))
    if isinstance(node, SetBuilder):
        return _builder(node, depth, lambda child, level: _substitute(child, args, level),
                        lambda level, name: level + 1)
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
    elif isinstance(node, Graph):
        names.add(node.axis.name)
    elif isinstance(node, Lambda):
        names.update(node.params)
    elif isinstance(node, Fold | Limit | Diff | Integral | Generator):
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
    if isinstance(node, Graph):
        name, spelling = node.axis.name, node.axis.spelling
        inner = context
        if node.expression_mode:
            forbidden = _free_names(node.target) | {bound for bound, _ in context}
            if name in forbidden:
                name = fresh(name)
                spelling = name
            inner = ((name, spelling),) + context
        target = _reify(node.target, inner, fresh)
        expression_mode = node.expression_mode
        if expression_mode and name not in free_names(target):
            target = Lambda(target.span, (name,), target, (spelling or name,))
            expression_mode = False
        elif not expression_mode and name in free_names(target):
            name = fresh(name)
            spelling = name
        return replace(node, axis=replace(node.axis, name=name, spelling=spelling,
                                         value=_reify(node.axis.value, context, fresh)),
                       target=target, expression_mode=expression_mode,
                       options=tuple(replace(kw, value=_reify(kw.value, context, fresh))
                                     for kw in node.options))
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
        clauses = []
        inner = context
        for index, clause in enumerate(node.clauses):
            if isinstance(clause, Generator):
                scoped = (*node.clauses[index + 1:], node.element)
                forbidden = set().union(*(_free_names(p) for p in scoped if p is not None))
                forbidden.update(name for name, _ in inner)
                name = fresh() if clause.var in forbidden else clause.var
                spelling = f"\\{name}" if name != clause.var else clause.var_spelling
                clauses.append(replace(clause, var=name, var_spelling=spelling,
                                       domain=_reify(clause.domain, inner, fresh)))
                inner = ((name, spelling),) + inner
            else:
                clauses.append(replace(clause, test=_reify(clause.test, inner, fresh)))
        return replace(node, clauses=tuple(clauses), element=None if node.element is None
                       else _reify(node.element, inner, fresh))
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
                       body=_reify(node.body, inner, fresh),
                       **_diff_order(node, lambda child: _reify(child, context, fresh)))
    return _children(node, lambda child: _reify(child, context, fresh))


def reduce_expression(value: ExpressionValue) -> ExpressionValue:
    if value.statement_body:
        raise ReduceError("\\reduce needs an expression quote")
    node = _encode(value.node, ())
    # TODO: Each beta step rescans the AST; use a zipper if large terms matter.
    # https://github.com/takeiteasy/adhoc/issues/3
    for steps in range(STEP_CAP + 1):
        node, changed = _reduce_once(node)
        if not changed:
            break
        if steps == STEP_CAP:
            raise ReduceError(f"\\reduce exceeded {STEP_CAP} beta steps")
    used = _all_names(node)
    numbers = count()

    def fresh(base: str | None = None) -> str:
        while True:
            number = next(numbers)
            name = f"{base[0]}_{number}" if base is not None else "reduce_" + _letters(number)
            if name not in used:
                used.add(name)
                return name

    return ExpressionValue(_reify(node, (), fresh), value.source, dimensions=value.dimensions)
