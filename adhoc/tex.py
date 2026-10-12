"""LaTeX rendering of expression trees and values, behind `\\tex(e)` (docs/tex.md).

Formatting only: nothing here evaluates or does arithmetic on a user value."""

from contextlib import contextmanager
from contextvars import ContextVar
from fractions import Fraction
import math

import sympy

from . import tensor as tn
from .syntax import (
    SUBSCRIPTS, is_short_name,
    Assign, ArrayLit, BackslashRef, BinOp, BinOperator, Call, Congruence, Compare, CompareOperator, Diff, Equation,
    Eval, Fold, Hole, IfExpr, Index, Integral, Graph, KwArg, Lambda, Limit, Node, NumLit, OpRef,
    Piecewise, PowCall, Quote, Range, SetBuilder, Generator, Guard, SetLit, StrLit, TensorLit, Transpose,
    UnaryOperator, UnOp, Var, WholeAxis,
)


class TexError(Exception):
    pass


_GREEK = dict(zip("αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΥΦΨΩ", [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi",
    "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi",
    "Psi", "Omega"]))
_GREEK_NAMES = frozenset(_GREEK.values())
_FUNCTIONS = {"asin": "arcsin", "acos": "arccos", "atan": "arctan"}
_KNOWN = frozenset({"sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh", "ln",
                    "log", "exp", "det", "gcd", "min", "max", "arg", "deg", "dim"})
_BIN = {
    BinOperator.ADD: (11, "+"), BinOperator.SUB: (11, "-"), BinOperator.MUL: (12, r"\cdot"),
    BinOperator.DOT: (12, r"\cdot"), BinOperator.TIMES: (12, r"\times"),
    BinOperator.OTIMES: (12, r"\otimes"), BinOperator.UNION: (11, r"\cup"),
    BinOperator.INTERSECT: (12, r"\cap"), BinOperator.SETMINUS: (11, r"\setminus"),
    BinOperator.COMPOSE: (12, r"\circ"), BinOperator.MOD: (12, r"\bmod"),
    BinOperator.ANGLE: (10, r"\angle"), BinOperator.AND: (6, r"\land"),
    BinOperator.OR: (5, r"\lor"), BinOperator.IMPLIES: (4, r"\to"), BinOperator.IFF: (3, r"\iff"),
}
_CMP = {
    CompareOperator.LT: "<", CompareOperator.LE: r"\le", CompareOperator.GT: ">",
    CompareOperator.GE: r"\ge", CompareOperator.IN: r"\in", CompareOperator.SUBSETEQ: r"\subseteq",
    CompareOperator.NE: r"\neq", CompareOperator.APPROX: r"\approx",
    CompareOperator.NOTIN: r"\notin", CompareOperator.SUBSET: r"\subset",
    CompareOperator.SUPSETEQ: r"\supseteq", CompareOperator.SUPSET: r"\supset",
}
_PAIRS = {"abs": ("|", "|"), "norm": (r"\lVert", r"\rVert"), "floor": (r"\lfloor", r"\rfloor"),
          "ceil": (r"\lceil", r"\rceil")}
_ATOM, _UNARY, _POW, _LOOSE, _COMPARE = 16, 14, 15, 2, 9
_SCOPE = ContextVar("adhoc_tex_scope", default=(None, frozenset()))


def _text(s: str) -> str:
    out = s
    for raw, escaped in (("\\", r"\textbackslash{}"), ("{", r"\{"), ("}", r"\}"), ("_", r"\_"),
                         ("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("$", r"\$")):
        out = out.replace(raw, escaped)
    return rf"\text{{{out}}}"


def _name(ch: str) -> str:
    base, rest = ch[0], ch[1:]
    head = rf"\{_GREEK[base]}" if base in _GREEK else base
    if not rest:
        return head
    sub = "".join(SUBSCRIPTS.get(c, c) for c in rest.lstrip("_"))
    return f"{head}_{{{sub}}}"


def _long_name(name: str) -> str:
    if name in _GREEK_NAMES:
        return rf"\{name}"
    if name == "inf":
        return r"\infty"
    return rf"\mathrm{{{name.replace('_', r'\_')}}}"


def _wrap(text: str, prec: int, own: int) -> str:
    """Parenthesize `text`, an expression of binding strength `own`, inside `prec`."""
    return rf"\left({text}\right)" if prec > own else text


def _args(nodes) -> str:
    return ", ".join(node_tex(n) for n in nodes)


def _matrix(rows: list[list[str]]) -> str:
    body = r" \\ ".join(" & ".join(row) for row in rows)
    return rf"\begin{{pmatrix}} {body} \end{{pmatrix}}"


def _cases(clauses: list[tuple[str, str]], otherwise: str | None) -> str:
    rows = [rf"{value} & \text{{if }} {cond}" for cond, value in clauses]
    if otherwise is not None:
        rows.append(rf"{otherwise} & \text{{otherwise}}")
    return r"\begin{cases} " + r" \\ ".join(rows) + r" \end{cases}"


def _number(text: str) -> str:
    mantissa, _, exponent = text.lower().partition("e")
    return rf"{mantissa} \times 10^{{{exponent}}}" if exponent else text


def _bounds(node: Node) -> tuple[str, str] | None:
    """Lower and upper limit text of a finite or infinite plain range."""
    if isinstance(node, Range) and node.second is None:
        return node_tex(node.start), node_tex(node.end) if node.end is not None else r"\infty"
    return None


def _chain(node: IfExpr) -> tuple[list[tuple[str, str]], str | None]:
    clauses = []
    while isinstance(node, IfExpr):
        clauses.append((node_tex(node.condition), node_tex(node.then_branch)))
        if node.otherwise is None:
            return clauses, None
        node = node.otherwise
    return clauses, node_tex(node)


def _head(head: Node) -> str:
    if isinstance(head, BackslashRef) and (head.name in _KNOWN or head.name in _FUNCTIONS):
        return rf"\{_FUNCTIONS.get(head.name, head.name)}"
    if isinstance(head, BackslashRef) and head.name not in _GREEK_NAMES:
        return rf"\operatorname{{{head.name.replace('_', r'\_')}}}"
    return node_tex(head, _ATOM)


@contextmanager
def _scope(lookup, bound=frozenset()):
    token = _SCOPE.set((lookup, frozenset(bound)))
    try:
        yield
    finally:
        _SCOPE.reset(token)


def _bound_tex(node: Node, names, prec: int = 0) -> str:
    lookup, bound = _SCOPE.get()
    with _scope(lookup, bound | frozenset(names)):
        return node_tex(node, prec)


def _numeric_head(node: Node) -> bool:
    from .runtime import _NUMERIC_TYPES
    match node:
        case NumLit():
            return True
        case Var(ch=name) | BackslashRef(name=name):
            lookup, bound = _SCOPE.get()
            if lookup is None or name in bound:
                return False
            value = lookup(name)
            return isinstance(value, _NUMERIC_TYPES) and not isinstance(value, bool)
        case UnOp(op=UnaryOperator.NEG, operand=operand):
            return _numeric_head(operand)
        case BinOp(op=op, lhs=lhs, rhs=rhs) if op in (
                BinOperator.ADD, BinOperator.SUB, BinOperator.MUL, BinOperator.DIV, BinOperator.POW):
            return _numeric_head(lhs) and _numeric_head(rhs)
    return False


def node_tex(node: Node, prec: int = 0) -> str:
    """The LaTeX for an expression node, parenthesized where `prec` (the surrounding
    operator's binding strength) requires it."""
    match node:
        case NumLit(text=text):
            return _number(text)
        case StrLit(text=text):
            return _text(text)
        case Var(ch=ch):
            return _name(ch)
        case BackslashRef(name=name):
            return _long_name(name)
        case Hole():
            return r"\cdot"
        case OpRef(name=name):
            from .syntax import OP_SYMBOLS
            return rf"\left({_text(OP_SYMBOLS[name])}\right)"
        case Assign(name=name, value=value):
            label = _name(name) if is_short_name(name) else _long_name(name)
            return f"{label} = {node_tex(value)}"
        case UnOp(op=UnaryOperator.NEG, operand=operand):
            return _wrap("-" + node_tex(operand, _UNARY), prec, _UNARY)
        case UnOp(op=UnaryOperator.NOT, operand=operand):
            return _wrap(r"\lnot " + node_tex(operand, 7), prec, 7)
        case UnOp(op=op, operand=operand):
            mark = "!" if op is UnaryOperator.FACT else "!!"
            return node_tex(operand, _ATOM) + mark
        case BinOp(op=BinOperator.DIV, lhs=lhs, rhs=rhs):
            return rf"\frac{{{node_tex(lhs)}}}{{{node_tex(rhs)}}}"
        case BinOp(op=BinOperator.POW, lhs=lhs, rhs=rhs):
            return f"{node_tex(lhs, _ATOM)}^{{{node_tex(rhs)}}}"
        case BinOp(op=BinOperator.MUL, lhs=NumLit() as lhs, rhs=rhs) if not isinstance(rhs, NumLit):
            return _wrap(f"{node_tex(lhs)} {node_tex(rhs, 13)}", prec, 12)
        case BinOp(op=op, lhs=lhs, rhs=rhs):
            level, symbol = _BIN[op]
            right = level + 1 if op is not BinOperator.IMPLIES else level
            return _wrap(f"{node_tex(lhs, level)} {symbol} {node_tex(rhs, right)}", prec, level)
        case Congruence(lhs=lhs, rhs=rhs, modulus=modulus):
            text = (f"{node_tex(lhs, _COMPARE + 1)} \\equiv "
                    f"{node_tex(rhs, _COMPARE + 1)} \\pmod{{{node_tex(modulus)}}}")
            return _wrap(text, prec, _COMPARE)
        case Compare(op=op, lhs=lhs, rhs=rhs):
            text = f"{node_tex(lhs, _COMPARE + 1)} {_CMP[op]} {node_tex(rhs, _COMPARE + 1)}"
            return _wrap(text, prec, _COMPARE)
        case Equation(lhs=lhs, rhs=rhs):
            text = f"{node_tex(lhs, _COMPARE + 1)} = {node_tex(rhs, _COMPARE + 1)}"
            return _wrap(text, prec, _COMPARE)
        case Range(start=start, second=second, end=end):
            middle = [node_tex(start)] + ([node_tex(second)] if second is not None else [])
            tail = [node_tex(end)] if end is not None else []
            return r"\{" + ", ".join(middle + [r"\ldots"] + tail) + r"\}"
        case IfExpr():
            clauses, otherwise = _chain(node)
            return _wrap(_cases(clauses, otherwise), prec, _LOOSE)
        case Piecewise(conditions=conditions, values=values, otherwise=otherwise):
            clauses = [(node_tex(c), node_tex(v)) for c, v in zip(conditions, values)]
            return _cases(clauses, None if otherwise is None else node_tex(otherwise))
        case Call(head=BackslashRef(name="sqrt"), args=(arg,)):
            return rf"\sqrt{{{node_tex(arg)}}}"
        case Call(head=BackslashRef(name="root"), args=(arg, index)):
            return rf"\sqrt[{node_tex(index)}]{{{node_tex(arg)}}}"
        case Call(head=BackslashRef(name=name), args=(arg,)) if name in _PAIRS:
            left, right = _PAIRS[name]
            return rf"\left{left} {node_tex(arg)} \right{right}"
        case Call(head=BackslashRef(name=name), args=args, kwargs=kwargs) if (
                name in _KNOWN or name in _FUNCTIONS):
            values = [node_tex(a) for a in args] + [node_tex(k) for k in kwargs]
            return rf"\{_FUNCTIONS.get(name, name)}\left({', '.join(values)}\right)"
        case Graph(target=target, axis=axis, options=options, expression_mode=expression_mode):
            target_text = _bound_tex(target, (axis.name,)) if expression_mode else node_tex(target)
            return rf"\operatorname{{graph}}\left({target_text}, {_args((axis, *options))}\right)"
        case Call(head=head, args=args, kwargs=kwargs):
            values = [node_tex(a) for a in args] + [node_tex(k) for k in kwargs]
            return rf"{_head(head)}\left({', '.join(values)}\right)"
        case PowCall(head=head, exponent=exponent, args=args, kwargs=kwargs):
            if _numeric_head(head) and len(args) == 1 and not kwargs:
                text = rf"{node_tex(head, _ATOM)}^{{{node_tex(exponent)}}} \cdot {node_tex(args[0], 13)}"
                return _wrap(text, prec, 12)
            values = [node_tex(a) for a in args] + [node_tex(k) for k in kwargs]
            return rf"{_head(head)}^{{{node_tex(exponent)}}}\left({', '.join(values)}\right)"
        case KwArg(name=name, value=value):
            label = _name(name) if is_short_name(name) else _long_name(name)
            return f"{label} = {node_tex(value)}"
        case Eval(value=value, bindings=bindings):
            return rf"\operatorname{{eval}}\left({_args((value, *bindings))}\right)"
        case Quote(body=body):
            return rf"\operatorname{{expr}}\left({node_tex(body)}\right)"
        case Fold(op=op, var=var, bound=bound, body=body, member_binder=member):
            name = _name(var) if is_short_name(var) else _long_name(var)
            body_text = _bound_tex(body, (var,), 12)
            if op in (BinOperator.AND, BinOperator.OR):
                quantifier = r"\forall" if op is BinOperator.AND else r"\exists"
                return _wrap(rf"{quantifier} {name} \in {node_tex(bound)},\ {_bound_tex(body, (var,))}",
                             prec, _LOOSE)
            symbol = r"\sum" if op is BinOperator.ADD else r"\prod"
            limits = _bounds(bound)
            if limits is not None and not member:
                low, high = limits
                return _wrap(rf"{symbol}_{{{name}={low}}}^{{{high}}} {body_text}", prec, _LOOSE)
            return _wrap(rf"{symbol}_{{{name} \in {node_tex(bound)}}} {body_text}", prec, _LOOSE)
        case Limit(var=var, point=point, body=body):
            name = _name(var) if is_short_name(var) else _long_name(var)
            return _wrap(rf"\lim_{{{name} \to {node_tex(point)}}} {_bound_tex(body, (var,), 12)}",
                         prec, _LOOSE)
        case Diff(var=var, point=point, body=body, order=order):
            name = _name(var) if is_short_name(var) else _long_name(var)
            degree = "" if order is None else rf"^{{{node_tex(order)}}}"
            return _wrap(rf"\left.\frac{{d{degree}}}{{d{name}{degree}}}\left({_bound_tex(body, (var,))}\right)\right|_{{{name}={node_tex(point)}}}",
                         prec, _LOOSE)
        case Integral(var=var, bound=bound, body=body):
            name = _name(var) if is_short_name(var) else _long_name(var)
            limits = _bounds(bound)
            scope = f"_{{{limits[0]}}}^{{{limits[1]}}}" if limits else rf"_{{{node_tex(bound)}}}"
            return _wrap(rf"\int{scope} {_bound_tex(body, (var,))} \, d{name}", prec, _LOOSE)
        case Lambda(params=params, body=body):
            names = [_name(p) if is_short_name(p) else _long_name(p) for p in params]
            head = names[0] if len(names) == 1 else rf"\left({', '.join(names)}\right)"
            return _wrap(rf"{head} \mapsto {_bound_tex(body, params)}", prec, _LOOSE)
        case TensorLit(items=items, row_length=row_length):
            if row_length is None:
                return _matrix([[node_tex(i)] for i in items])
            return _matrix([[node_tex(i) for i in items[k:k + row_length]]
                            for k in range(0, len(items), row_length)])
        case ArrayLit(items=items):
            return rf"\langle {_args(items)} \rangle"
        case SetLit(items=items):
            return r"\{" + _args(items) + r"\}" if items else r"\emptyset"
        case SetBuilder(clauses=clauses, element=element):
            lookup, bound = _SCOPE.get()
            texts = []
            for clause in clauses:
                with _scope(lookup, bound):
                    if isinstance(clause, Generator):
                        name = _name(clause.var) if is_short_name(clause.var) else _long_name(clause.var)
                        texts.append(rf"{name} \in {node_tex(clause.domain)}")
                    else:
                        texts.append(node_tex(clause.test))
                if isinstance(clause, Generator):
                    bound = bound | {clause.var}
            if element is None:
                return rf"\{{ {texts[0]} \mid {', '.join(texts[1:])} \}}"
            with _scope(lookup, bound):
                head = node_tex(element)
            return rf"\{{ {head} \mid {', '.join(texts)} \}}"
        case WholeAxis():
            return r"\ldots"
        case Index(head=head, items=items):
            return f"{node_tex(head, _ATOM)}_{{{_args(items)}}}"
        case Transpose(operand=operand, glyph=glyph):
            mark = "'" if glyph == "'" else r"^{\mathsf{T}}"
            return node_tex(operand, _ATOM) + mark
    raise TexError(f"cannot render {type(node).__name__} as TeX")


def _scalar(value, show) -> str:
    if isinstance(value, bool):
        return _text("true" if value else "false")
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Fraction):
        sign = "-" if value < 0 else ""
        return rf"{sign}\frac{{{abs(value.numerator)}}}{{{value.denominator}}}"
    from .runtime import _NUMERIC_TYPES
    if not isinstance(value, _NUMERIC_TYPES):
        raise TexError(f"cannot render {show(value)} as TeX")
    text = show(value)
    if hasattr(value, "expr") and type(value).__name__ in ("Symbolic", "Algebraic"):
        return sympy.latex(value.expr)
    return text.replace("...", r"\ldots").replace("Inf", r"\infty").replace("NaN", r"\mathrm{NaN}")


def value_tex(value, show, *, lookup=None) -> str:
    with _scope(lookup):
        return _value_tex(value, show)


def _value_tex(value, show) -> str:
    """The LaTeX for an evaluated value; `show` is the runtime's display function."""
    from .expression import ExpressionValue
    from .solution_set import SymbolicSetValue
    from .runtime import AdFunction, IntervalValue, RangeValue
    from . import units
    if isinstance(value, units.UnitValue):
        return rf"\mathrm{{{value.name.replace('_', r'\_')}}}"
    if isinstance(value, units.Quantity):
        unit = value.display_unit
        magnitude = value.magnitude if unit is None else units.extract(value, unit)
        terms = []
        if unit is not None and unit.name:
            suffix = rf"\mathrm{{{unit.name.replace('_', r'\_')}}}"
        else:
            for name, exponent in zip(units.BASE_NAMES, value.dimensions):
                if exponent:
                    term = rf"\mathrm{{{name}}}"
                    if exponent != 1:
                        term += "^{" + str(exponent) + "}"
                    terms.append(term)
            suffix = r"\, ".join(terms)
            if unit is not None:
                suffix = rf"\left({_value_tex(unit.scale, show)}\, {suffix or '1'}\right)"
        return _value_tex(magnitude, show) + r"\, " + suffix
    if isinstance(value, SymbolicSetValue):
        return value.render(tex=True)
    if isinstance(value, ExpressionValue):
        return node_tex(value.node)
    if isinstance(value, AdFunction):
        params = [_name(p) if is_short_name(p) else _long_name(p) for p in value.params]
        with _scope(value.closure._lookup, value.params):
            body = node_tex(value.body.node)
        if not value.name:
            head = params[0] if len(params) == 1 else rf"\left({', '.join(params)}\right)"
            return rf"{head} \mapsto {body}"
        label = _name(value.name) if is_short_name(value.name) else _long_name(value.name)
        return rf"{label}\left({', '.join(params)}\right) = {body}"
    if isinstance(value, IntervalValue):
        start, end = _value_tex(value.start, show), _value_tex(value.end, show)
        left = "(" if isinstance(value.start, float) and math.isinf(value.start) else "["
        right = ")" if isinstance(value.end, float) and math.isinf(value.end) else "]"
        return rf"\left{left}{start}, {end}\right{right}"
    if isinstance(value, RangeValue):
        parts = [_value_tex(value.start, show)]
        if value.second is not None:
            parts.append(_value_tex(value.second, show))
        parts.append(r"\ldots")
        if value.end is not None:
            parts.append(_value_tex(value.end, show))
        return r"\{" + ", ".join(parts) + r"\}"
    if isinstance(value, tn.TensorValue):
        if value.order == 2:
            return _matrix([[_value_tex(x, show) for x in tn.slices(row)] for row in tn.slices(value)])
        return _matrix([[_value_tex(x, show)] for x in tn.slices(value)])
    if isinstance(value, tn.SetValue):
        return r"\{" + ", ".join(_value_tex(x, show) for x in value.items) + r"\}" \
            if value.items else r"\emptyset"
    if isinstance(value, tn.ArrayValue):
        return rf"\langle {', '.join(_value_tex(x, show) for x in value.items)} \rangle"
    return _scalar(value, show)
