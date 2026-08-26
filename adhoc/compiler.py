"""Lowering: adhoc AST → Python AST → compiled bytecode.

One generated Python source *line* per top-level adhoc statement, with two tables riding
alongside the code object: `spans` (sid-indexed, every lowered operation's span) and
`line_spans` (generated line number → statement span). Every operation routes through an
`Engine` method call carrying its sid (`_e.add(lhs, rhs, 3)`), which is what keeps
runtime-error spans narrow — a sub-expression's failure points at the sub-expression.

Lowering rules:

- `NumLit` → `Constant` via `parse_literal` (int without `.`, float with). `StrLit` →
  `Constant` likewise — but only ever as a call argument or a whole statement; a string
  is never an operand (the parser rejects that before lowering sees it).
- A bare-string *statement* lowers to `pass`: one generated line per statement keeps the
  lineno ↔ span table aligned while producing no output.
- Variables are never bare Python name loads or stores — reads go through `_e.var`,
  writes through `_e.assign`/`_e.reassign` implementing bind-or-compare. The user env is
  a plain dict the engine holds; it never mixes with the exec globals.
- `\name` lowers to `_e.bref("name", sid)`; application lowers to `_e.app(head, args,
  sid)`; `\\py(path)` is the one backslash name with semantics of its own and lowers to
  `_e.py(path, sid)`. `FuncDef` registers a separately compiled body and lowers to
  `_e.define(...)`; `\\if` lowers to lazy thunk calls.
- `Seq` flattens; each statement becomes one line, matching script mode's per-statement
  echo and the line-number gutter.
"""

import ast as pyast
from dataclasses import dataclass, field
from types import CodeType

from .runtime import parse_literal
from .span import Span
from .syntax import (
    Assign,
    BackslashRef,
    BinOp,
    BinOperator,
    Call,
    Compare,
    CompareOperator,
    FuncDef,
    IfExpr,
    Node,
    NumLit,
    Seq,
    StrLit,
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

_CMP_METHODS = {
    CompareOperator.LT: "lt", CompareOperator.LE: "le",
    CompareOperator.GT: "gt", CompareOperator.GE: "ge",
}


@dataclass(frozen=True)
class Compiled:
    source: str
    code: CodeType
    spans: tuple[Span, ...]
    line_spans: dict[int, Span]
    definitions: dict[int, "CompiledBody"] = field(default_factory=dict)


@dataclass(frozen=True)
class CompiledBody:
    code: CodeType
    spans: tuple[Span, ...]
    definitions: dict[int, "CompiledBody"]


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
        self.definitions: dict[int, CompiledBody] = {}

    def _push(self, span: Span) -> int:
        self.spans.append(span)
        return len(self.spans) - 1

    def statement(self, stmt: Node) -> str:
        match stmt:
            case FuncDef(span=span):
                sid = self._push(span)
                self.definitions[sid] = _compile_body(stmt.body)
                return pyast.unparse(_call("define", [pyast.Constant(stmt.name),
                    pyast.Constant(stmt.params), pyast.Constant(stmt.force), pyast.Constant(sid)]))
            case StrLit():
                # A lone string is a comment-like no-op; `pass` keeps the one-line-per-
                # statement invariant that the lineno ↔ span table depends on.
                return "pass"
            case IfExpr(condition=condition, then_branch=then_branch, otherwise=None, span=span):
                sid = self._push(span)
                thunk = pyast.Lambda(args=pyast.arguments(posonlyargs=[], args=[],
                    kwonlyargs=[], kw_defaults=[], defaults=[]), body=self.expr(then_branch))
                return pyast.unparse(_call("if_stmt", [self.expr(condition), thunk,
                    pyast.Constant(sid)]))
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
            case StrLit(text=text):
                return pyast.Constant(value=text)
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
            case Compare(op=op, lhs=lhs, rhs=rhs, span=span):
                sid = self._push(span)
                return _call(_CMP_METHODS[op], [self.expr(lhs), self.expr(rhs), pyast.Constant(sid)])
            case IfExpr(condition=condition, then_branch=then_branch, otherwise=otherwise, span=span):
                sid = self._push(span)
                thunk = lambda n: pyast.Lambda(args=pyast.arguments(posonlyargs=[], args=[],
                    kwonlyargs=[], kw_defaults=[], defaults=[]), body=self.expr(n))
                return _call("if_expr", [self.expr(condition), thunk(then_branch),
                    thunk(otherwise) if otherwise is not None else pyast.Constant(None),
                    pyast.Constant(sid)])
            case Assign(name=name, value=value, span=span):
                sid = self._push(span)
                return _call("set", [pyast.Constant(name), self.expr(value), pyast.Constant(sid)])
            case Seq(statements=statements):
                return pyast.Subscript(
                    value=pyast.Tuple(elts=[self.expr(s) for s in statements], ctx=pyast.Load()),
                    slice=pyast.Constant(-1), ctx=pyast.Load())
            case Call(head=BackslashRef(name="py"), args=args, span=span):
                # `\py` is the one backslash name with its own semantics: resolve the
                # single string-literal argument to a Python callable. Parser enforces
                # arity; the engine rejects non-string arguments with the same span.
                sid = self._push(span)
                arg_exprs = [self.expr(a) for a in args]
                return _call("py", [*arg_exprs, pyast.Constant(sid)])
            case Call(head=head, args=args, span=span):
                head_expr = self.expr(head)
                arg_exprs = [self.expr(a) for a in args]
                sid = self._push(span)
                return _call(
                    "app",
                    [head_expr, pyast.Tuple(elts=arg_exprs, ctx=pyast.Load()), pyast.Constant(sid)],
                )
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
    return Compiled(source=source, code=code, spans=tuple(lowerer.spans), line_spans=line_spans,
                    definitions=lowerer.definitions)


def _compile_body(node: Node) -> CompiledBody:
    lowerer = _Lowerer()
    statements = _flatten(node)
    lines = ["_result = None"]
    for stmt in statements:
        sid = lowerer._push(stmt.span)
        if isinstance(stmt, Assign):
            value = lowerer.expr(stmt.value)
            expr = _call("set", [pyast.Constant(stmt.name), value, pyast.Constant(sid)])
        elif isinstance(stmt, StrLit):
            expr = pyast.Constant(None)
        elif isinstance(stmt, IfExpr) and stmt.otherwise is None:
            thunk = pyast.Lambda(args=pyast.arguments(posonlyargs=[], args=[],
                kwonlyargs=[], kw_defaults=[], defaults=[]), body=lowerer.expr(stmt.then_branch))
            lines.append(pyast.unparse(_call("if_stmt", [lowerer.expr(stmt.condition), thunk,
                pyast.Constant(sid)])))
            continue
        else:
            expr = lowerer.expr(stmt)
        assignment = pyast.Assign(
            targets=[pyast.Name(id="_result", ctx=pyast.Store())], value=expr)
        lines.append(pyast.unparse(pyast.fix_missing_locations(assignment)))
    tree = pyast.parse("\n".join(lines))
    tree = pyast.fix_missing_locations(tree)
    return CompiledBody(compile(tree, "<adhoc>", "exec"), tuple(lowerer.spans), lowerer.definitions)
