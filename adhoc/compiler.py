"""Lowering: adhoc AST → Python AST → compiled bytecode.

One generated Python source *line* per top-level adhoc statement, with two tables riding
alongside the code object: `spans` (sid-indexed, every lowered operation's span) and
`line_spans` (generated line number → statement span). Every operation routes through an
`Engine` method call carrying its sid (`_e.add(lhs, rhs, 3)`), which is what keeps
runtime-error spans narrow — a sub-expression's failure points at the sub-expression.

Lowering rules:

- `NumLit` → `Constant` via `parse_literal` (int without `.`, float with).
- Variables are never bare Python name loads or stores — reads go through `_e.var`,
  writes through `_e.assign`/`_e.reassign` implementing bind-or-compare. The user env is
  a plain dict the engine holds; it never mixes with the exec globals.
- `\name` lowers to `_e.bref("name", sid)`, which always fails in phase 0 but keeps the
  sigil-inclusive span for the diagnostic.
- `Seq` flattens; each statement becomes one line, matching script mode's per-statement
  echo and the line-number gutter.
"""

import ast as pyast
from dataclasses import dataclass
from types import CodeType

from .runtime import parse_literal
from .span import Span
from .syntax import (
    Assign,
    BackslashRef,
    BinOp,
    BinOperator,
    Node,
    NumLit,
    Seq,
    UnOp,
    UnaryOperator,
    Var,
)

ENGINE = "_e"

_BIN_METHODS = {
    BinOperator.ADD: "add",
    BinOperator.SUB: "sub",
    BinOperator.MUL: "mul",
    BinOperator.DIV: "div",
    BinOperator.POW: "pow",
}


@dataclass(frozen=True)
class Compiled:
    source: str
    code: CodeType
    spans: tuple[Span, ...]
    line_spans: dict[int, Span]


def _call(method: str, args: list[pyast.expr]) -> pyast.expr:
    return pyast.Call(
        func=pyast.Attribute(
            value=pyast.Name(id=ENGINE, ctx=pyast.Load()), attr=method, ctx=pyast.Load()
        ),
        args=args,
        keywords=[],
    )


class _Lowerer:
    def __init__(self):
        self.spans: list[Span] = []

    def _push(self, span: Span) -> int:
        self.spans.append(span)
        return len(self.spans) - 1

    def statement(self, stmt: Node) -> str:
        match stmt:
            case Assign(name=name, force=force, value=value, span=span):
                sid = self._push(span)
                inner = self.expr(value)
                method = "reassign" if force else "assign"
                return pyast.unparse(_call(method, [pyast.Constant(name), inner, pyast.Constant(sid)]))
            case _:
                sid = self._push(stmt.span)
                inner = self.expr(stmt)
                return pyast.unparse(_call("out", [inner, pyast.Constant(sid)]))

    def expr(self, node: Node) -> pyast.expr:
        match node:
            case NumLit(text=text):
                return pyast.Constant(value=parse_literal(text))
            case Var(ch=ch, span=span):
                sid = self._push(span)
                return _call("var", [pyast.Constant(ch), pyast.Constant(sid)])
            case BackslashRef(name=name, span=span):
                sid = self._push(span)
                return _call("bref", [pyast.Constant(name), pyast.Constant(sid)])
            case UnOp(op=UnaryOperator.NEG, operand=operand, span=span):
                inner = self.expr(operand)
                sid = self._push(span)
                return _call("neg", [inner, pyast.Constant(sid)])
            case BinOp(op=op, lhs=lhs, rhs=rhs, span=span):
                left = self.expr(lhs)
                right = self.expr(rhs)
                sid = self._push(span)
                return _call(_BIN_METHODS[op], [left, right, pyast.Constant(sid)])
            case _:
                raise TypeError(f"no lowering for {node!r}")


def _flatten(node: Node) -> list[Node]:
    """Top-level statements; Seqs flatten so each statement gets its own line."""
    if isinstance(node, Seq):
        out: list[Node] = []
        for s in node.statements:
            out.extend(_flatten(s))
        return out
    return [node]


def compile_program(node: Node) -> Compiled:
    lowerer = _Lowerer()
    stmts = _flatten(node)
    lines = [lowerer.statement(s) for s in stmts]
    source = "\n".join(lines)
    code = compile(source, "<adhoc>", "exec")
    line_spans = {i + 1: s.span for i, s in enumerate(stmts)}
    return Compiled(source=source, code=code, spans=tuple(lowerer.spans), line_spans=line_spans)
