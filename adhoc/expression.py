"""Unevaluated expression values and their parseable display."""

from dataclasses import dataclass, fields

from .syntax import (
    BackslashRef, BinOp, BinOperator, Call, Compare, CompareOperator, Eval,
    Fold, IfExpr, KwArg, Lambda, Limit, Node, NumLit, Quote, Range, StrLit,
    UnOp, Var,
)


@dataclass(frozen=True, eq=False)
class ExpressionValue:
    node: Node
    source: str
    __hash__ = None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ExpressionValue) and _shape(self.node) == _shape(other.node)


def _shape(value):
    if isinstance(value, Node):
        return (type(value), tuple(_shape(getattr(value, f.name)) for f in fields(value)
                                   if f.name != "span" and f.compare))
    if isinstance(value, tuple):
        return tuple(_shape(item) for item in value)
    return value


_BIN = {
    BinOperator.ADD: "+", BinOperator.SUB: "-", BinOperator.MUL: "*",
    BinOperator.DIV: "/", BinOperator.POW: "^",
}
_CMP = {
    CompareOperator.LT: "<", CompareOperator.LE: "<=",
    CompareOperator.GT: ">", CompareOperator.GE: ">=",
}


def show(node: Node) -> str:
    match node:
        case NumLit(text=text):
            return text
        case StrLit(text=text):
            return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'
        case Var(ch=name, spelling=spelling) | BackslashRef(name=name, spelling=spelling):
            return spelling or (name if len(name) == 1 else f"\\{name}")
        case UnOp(operand=operand):
            return f"(-{show(operand)})"
        case BinOp(op=op, lhs=left, rhs=right):
            return f"({show(left)} {_BIN[op]} {show(right)})"
        case Compare(op=op, lhs=left, rhs=right):
            return f"({show(left)} {_CMP[op]} {show(right)})"
        case Range(start=start, second=second, end=end):
            middle = f",{show(second)}" if second is not None else ""
            return f"({show(start)}{middle}..{show(end) if end is not None else ''})"
        case IfExpr(condition=condition, then_branch=yes, otherwise=no):
            return f"({show(condition)} ? {show(yes)} : {show(no)})"
        case Call(head=head, args=args, kwargs=kwargs):
            values = [show(arg) for arg in args]
            values += [f"{show(kw_name(kw))}={show(kw.value)}" for kw in kwargs]
            return f"{show(head)}({', '.join(values)})"
        case Fold(op=op, var=var, rng=rng, body=body, spelling=spelling,
                  var_spelling=var_spelling):
            head = spelling or ("\\sum" if op is BinOperator.ADD else "\\prod")
            return f"({head}({var_spelling or var}={show(rng)}) {show(body)})"
        case Limit(var=var, point=point, body=body, spelling=spelling,
                   var_spelling=var_spelling):
            head = spelling or "\\lim"
            return f"({head}({var_spelling or var}={show(point)}) {show(body)})"
        case Lambda(params=params, body=body, param_spellings=spellings):
            names = [spellings[i] if i < len(spellings) else name for i, name in enumerate(params)]
            return f"(\\fn({', '.join(names)}) {show(body)})"
        case Quote(body=body):
            return f"\\expr({show(body)})"
        case Eval(value=value, bindings=bindings):
            values = [show(value)] + [f"{show(kw_name(kw))}={show(kw.value)}" for kw in bindings]
            return f"\\eval({', '.join(values)})"
        case _:
            raise TypeError(f"cannot display expression node {type(node).__name__}")


def kw_name(kw: KwArg) -> Node:
    return BackslashRef(name=kw.name, span=kw.span, spelling=kw.spelling) if len(kw.name) > 1 else Var(ch=kw.name, span=kw.span, spelling=kw.spelling)
