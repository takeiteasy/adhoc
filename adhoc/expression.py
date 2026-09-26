"""Unevaluated expression values and their parseable display."""

from dataclasses import dataclass, fields

from .lexer import SUPERSCRIPTS
from .syntax import (
    is_short_name,
    BackslashRef, BinOp, BinOperator, Call, Compare, CompareOperator, Eval,
    Assign, ArrayLit, Fold, FuncDef, Hole, IfExpr, Import, Index, KwArg, Lambda, Limit, Node, NumLit, OP_SYMBOLS, OpRef, PowCall,
    PyImport, Quote, Range, Seq, SetLit, StrLit, TensorLit, Transpose, UnaryOperator, UnOp, Var,
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
    BinOperator.DIV: "/", BinOperator.POW: "^", BinOperator.DOT: "@",
    BinOperator.UNION: "∪", BinOperator.INTERSECT: "∩", BinOperator.SETMINUS: "∖",
    BinOperator.COMPOSE: "∘", BinOperator.MOD: "%", BinOperator.ANGLE: "∠",
}
_POSTFIX = {UnaryOperator.FACT: "!", UnaryOperator.DFACT: "‼"}
_CMP = {
    CompareOperator.LT: "<", CompareOperator.LE: "<=",
    CompareOperator.GT: ">", CompareOperator.GE: ">=",
    CompareOperator.IN: "∈", CompareOperator.SUBSETEQ: "⊆",
    CompareOperator.NE: "≠", CompareOperator.APPROX: "≈",
    CompareOperator.NOTIN: "∉", CompareOperator.SUBSET: "⊂",
    CompareOperator.SUPSETEQ: "⊇", CompareOperator.SUPSET: "⊃",
}


def show(node: Node) -> str:
    match node:
        case Seq(statements=statements):
            return "".join(show(stmt) + ("\n" if isinstance(stmt, FuncDef) else "; ")
                           for stmt in statements[:-1]) + show(statements[-1])
        case Assign(name=name, value=value, spelling=spelling, fresh_only=fresh):
            prefix = "\\let " if fresh else ""
            label = spelling or (name if is_short_name(name) else f"\\{name}")
            return f"{prefix}{label} = {show(value)}"
        case FuncDef(name=name, params=params, body=body, spelling=spelling,
                     param_spellings=spellings):
            label = spelling or (name if is_short_name(name) else f"\\{name}")
            names = [spellings[i] if i < len(spellings) else param
                     for i, param in enumerate(params)]
            text = f"({show(body)})" if isinstance(body, Seq) else show(body)
            return f"{label}({', '.join(names)}) = {text}"
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
        case Hole():
            return "·"
        case OpRef(name=name):
            return f"({OP_SYMBOLS[name]})"
        case StrLit(text=text):
            return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'
        case Var(ch=name, spelling=spelling) | BackslashRef(name=name, spelling=spelling):
            return spelling or (name if is_short_name(name) else f"\\{name}")
        case UnOp(op=UnaryOperator.NEG, operand=operand):
            return f"(-{show(operand)})"
        case UnOp(op=op, operand=operand):
            return f"({show(operand)}{_POSTFIX[op]})"
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
        case PowCall(head=head, exponent=exponent, args=args, kwargs=kwargs):
            values = [show(arg) for arg in args]
            values += [f"{show(kw_name(kw))}={show(kw.value)}" for kw in kwargs]
            script = _superscript(exponent)
            if script is None:
                # An exponent rewritten by `\expr` may leave the superscript alphabet; a
                # callable head still reads the same as `f(x) ^ n`.
                return f"({show(head)}({', '.join(values)}) ^ {show(exponent)})"
            return f"{show(head)}{script}({', '.join(values)})"
        case Fold(op=op, var=var, bound=bound, body=body, spelling=spelling,
                  var_spelling=var_spelling):
            head = spelling or ("\\sum" if op is BinOperator.ADD else "\\prod")
            return f"({head}({var_spelling or var}={show(bound)}) {show(body)})"
        case Limit(var=var, point=point, body=body, spelling=spelling,
                   var_spelling=var_spelling):
            head = spelling or "\\lim"
            return f"({head}({var_spelling or var}={show(point)}) {show(body)})"
        case Lambda(params=params, body=body, param_spellings=spellings):
            names = [spellings[i] if i < len(spellings) else name for i, name in enumerate(params)]
            return f"(\\fn({', '.join(names)}) {show(body)})"
        case TensorLit(items=items, row_length=row_length):
            if row_length is None:
                return f"[{', '.join(show(item) for item in items)}]"
            rows = [", ".join(show(item) for item in items[i:i + row_length])
                    for i in range(0, len(items), row_length)]
            return f"[{'; '.join(rows)};]" if len(rows) == 1 else f"[{'; '.join(rows)}]"
        case ArrayLit(items=items):
            return f"⟨{', '.join(show(item) for item in items)}⟩"
        case SetLit(items=items):
            return f"{{{', '.join(show(item) for item in items)}}}"
        case Index(head=head, items=items):
            return f"{show(head)}[{', '.join(show(item) for item in items)}]"
        case Transpose(operand=operand):
            return f"{show(operand)}'"
        case Quote(body=body, statement_body=statement_body):
            return show_quote(body, statement_body)
        case Eval(value=value, bindings=bindings):
            values = [show(value)] + [f"{show(kw_name(kw))}={show(kw.value)}" for kw in bindings]
            return f"\\eval({', '.join(values)})"
        case _:
            raise TypeError(f"cannot display expression node {type(node).__name__}")


_SUPERSCRIPT_GLYPHS = {ascii_: glyph for glyph, ascii_ in SUPERSCRIPTS.items()}


def _superscript(node: Node) -> str | None:
    """`node` as superscript glyphs the lexer reads back to the same expression, or None."""
    def wrap(inner: str | None) -> str | None:
        return None if inner is None else f"⁽{inner}⁾"

    def atom(n: Node) -> str | None:
        inner = _superscript(n)
        needs_parens = isinstance(n, BinOp) or (isinstance(n, UnOp) and n.op is UnaryOperator.NEG)
        return wrap(inner) if needs_parens else inner

    match node:
        case NumLit(text=text) if text.isascii() and text.isdigit():
            return "".join(_SUPERSCRIPT_GLYPHS[c] for c in text)
        case Var(ch=ch) if len(ch) == 1 and ch in _SUPERSCRIPT_GLYPHS:
            return _SUPERSCRIPT_GLYPHS[ch]
        case UnOp(op=UnaryOperator.NEG, operand=operand):
            inner = atom(operand)
            return None if inner is None else f"⁻{inner}"
        case BinOp(op=BinOperator.ADD | BinOperator.SUB as op, lhs=lhs, rhs=rhs):
            left = _superscript(lhs)
            right = atom(rhs) if isinstance(rhs, BinOp) and rhs.op in (
                BinOperator.ADD, BinOperator.SUB) else _superscript(rhs)
            if left is None or right is None:
                return None
            return f"{left}{'⁺' if op is BinOperator.ADD else '⁻'}{right}"
        case BinOp(op=BinOperator.MUL, lhs=lhs, rhs=Var() as rhs) if isinstance(lhs, (NumLit, Var)):
            left, right = _superscript(lhs), _superscript(rhs)
            return None if left is None or right is None else left + right
    return None


def kw_name(kw: KwArg) -> Node:
    return BackslashRef(name=kw.name, span=kw.span, spelling=kw.spelling) if not is_short_name(kw.name) else Var(ch=kw.name, span=kw.span, spelling=kw.spelling)


def show_quote(node: Node, statement_body: bool) -> str:
    text = show(node)
    if statement_body and isinstance(node, Seq) and len(node.statements) == 1:
        text += "\n" if isinstance(node.statements[0], FuncDef) else ";"
    return f"\\expr(({text}))" if statement_body else f"\\expr({text})"
