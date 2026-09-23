"""Unevaluated expression values and their parseable display."""

from dataclasses import dataclass, fields

from .syntax import (
    BackslashRef, BinOp, BinOperator, Call, Compare, CompareOperator, Eval,
    Assign, Fold, FuncDef, IfExpr, Import, KwArg, Lambda, Limit, Node, NumLit,
    PyImport, Quote, Range, Seq, StrLit, UnOp, Var,
)


@dataclass(frozen=True, eq=False)
class ExpressionValue:
    node: Node
    source: str
    statement_body: bool = False
    __hash__ = None

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, ExpressionValue)
                and self.statement_body == other.statement_body
                and _shape(self.node) == _shape(other.node))


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
        case Seq(statements=statements):
            return "; ".join(show(stmt) for stmt in statements)
        case Assign(name=name, value=value, spelling=spelling, fresh_only=fresh):
            prefix = "\\let " if fresh else ""
            label = spelling or (name if len(name) == 1 else f"\\{name}")
            return f"{prefix}{label} = {show(value)}"
        case FuncDef(name=name, params=params, body=body, spelling=spelling,
                     param_spellings=spellings):
            label = spelling or (name if len(name) == 1 else f"\\{name}")
            names = [spellings[i] if i < len(spellings) else param
                     for i, param in enumerate(params)]
            return f"{label}({', '.join(names)}) = {show(body)}"
        case Import(path=path, members=members, member_spellings=spellings):
            names = [spellings[i] if i < len(spellings) else name
                     for i, name in enumerate(members)]
            suffix = f": {', '.join(names)}" if names else ""
            return f"\\import({show(StrLit(text=path, span=node.span))}{suffix})"
        case PyImport(path=path, members=members, member_spellings=spellings):
            names = [spellings[i] if i < len(spellings) else name
                     for i, name in enumerate(members)]
            return f"\\pyimport({show(StrLit(text=path, span=node.span))}: {', '.join(names)})"
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
        case Quote(body=body, statement_body=statement_body):
            return show_quote(body, statement_body)
        case Eval(value=value, bindings=bindings):
            values = [show(value)] + [f"{show(kw_name(kw))}={show(kw.value)}" for kw in bindings]
            return f"\\eval({', '.join(values)})"
        case _:
            raise TypeError(f"cannot display expression node {type(node).__name__}")


def kw_name(kw: KwArg) -> Node:
    return BackslashRef(name=kw.name, span=kw.span, spelling=kw.spelling) if len(kw.name) > 1 else Var(ch=kw.name, span=kw.span, spelling=kw.spelling)


def show_quote(node: Node, statement_body: bool) -> str:
    text = show(node)
    if statement_body and isinstance(node, Seq) and len(node.statements) == 1:
        text += ";"
    return f"\\expr(({text}))" if statement_body else f"\\expr({text})"
