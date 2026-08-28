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
  writes through `_e.assign` (bind-or-compare; there is no force-reassignment spelling —
  an unconditional rebind goes through a sequence group's `_e.set`), and constant
  declarations (`x ≡ e` / `\\const x = e`) through `_e.const_assign`. The user env is
  a plain dict the engine holds; it never mixes with the exec globals.
- `\name` lowers to `_e.bref("name", sid)`; application lowers to `_e.app(head, args,
  kwargs, sid)` with the kwargs as a dict literal; `\\py(path)` is the one backslash name
  with semantics of its own and lowers to `_e.py(path, sid)`. `FuncDef` registers a
  separately compiled body and lowers to `_e.define(...)`; `\\if` lowers to lazy thunk
  calls. `Import`/`PyImport` lower to `_e.import_(path, members, sid)`/`_e.pyimport(...)`
  — one line, no output, legal wherever statements are (top level, function bodies).
  `Fold`/`Limit` likewise register their bodies via `_compile_body` and lower to
  `_e.fold(...)`/`_e.limit(...)`, which evaluate the body once per term/probe in a child
  engine frame.
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
    ConstAssign,
    Fold,
    FuncDef,
    IfExpr,
    Import,
    Limit,
    Node,
    NoOp,
    NumLit,
    PyImport,
    Range,
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

# The fold operator each Fold node accumulates with; the runtime maps these back to
# nadd/nmul (the only arithmetic a fold is allowed to perform).
_FOLD_METHODS = {
    BinOperator.ADD: "add",
    BinOperator.MUL: "mul",
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
                    pyast.Constant(stmt.params), pyast.Constant(stmt.const),
                    pyast.Constant(sid)]))
            case ConstAssign(name=name, value=value, span=span):
                sid = self._push(span)
                return pyast.unparse(_call("const_assign",
                    [pyast.Constant(name), self.expr(value), pyast.Constant(sid)]))
            case Import(path=path, members=members, span=span):
                sid = self._push(span)
                return pyast.unparse(_call("import_",
                    [pyast.Constant(path), pyast.Constant(members), pyast.Constant(sid)]))
            case PyImport(path=path, members=members, span=span):
                sid = self._push(span)
                return pyast.unparse(_call("pyimport",
                    [pyast.Constant(path), pyast.Constant(members), pyast.Constant(sid)]))
            case StrLit() | NoOp():
                # A lone string is a comment-like no-op; `pass` keeps the one-line-per-
                # statement invariant that the lineno ↔ span table depends on.
                return "pass"
            case IfExpr(condition=condition, then_branch=then_branch, otherwise=None, span=span):
                sid = self._push(span)
                thunk = pyast.Lambda(args=pyast.arguments(posonlyargs=[], args=[],
                    kwonlyargs=[], kw_defaults=[], defaults=[]), body=self.expr(then_branch))
                return pyast.unparse(_call("if_stmt", [self.expr(condition), thunk,
                    pyast.Constant(sid)]))
            case Assign(name=name, value=value, span=span):
                sid = self._push(span)
                inner = self.expr(value)
                return pyast.unparse(_call("assign",
                    [pyast.Constant(name), inner, pyast.Constant(sid)]))
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
            case Range(start=start, second=second, end=end, span=span):
                sid = self._push(span)
                return _call("range", [self.expr(start),
                    self.expr(second) if second is not None else pyast.Constant(None),
                    self.expr(end) if end is not None else pyast.Constant(None),
                    pyast.Constant(sid)])
            case IfExpr(condition=condition, then_branch=then_branch, otherwise=otherwise, span=span):
                sid = self._push(span)
                thunk = lambda n: pyast.Lambda(args=pyast.arguments(posonlyargs=[], args=[],
                    kwonlyargs=[], kw_defaults=[], defaults=[]), body=self.expr(n))
                return _call("if_expr", [self.expr(condition), thunk(then_branch),
                    thunk(otherwise) if otherwise is not None else pyast.Constant(None),
                    pyast.Constant(sid)])
            case Fold(op=op, var=var, rng=rng, body=body, span=span):
                # Same shape as FuncDef: the folded body is compiled once into
                # `definitions[sid]`; the engine evaluates it per term in a child frame.
                sid = self._push(span)
                self.definitions[sid] = _compile_body(body)
                return _call("fold", [pyast.Constant(_FOLD_METHODS[op]),
                    pyast.Constant(var), self.expr(rng), pyast.Constant(sid)])
            case Limit(var=var, point=point, body=body, span=span):
                sid = self._push(span)
                self.definitions[sid] = _compile_body(body)
                return _call("limit", [pyast.Constant(var), self.expr(point),
                    pyast.Constant(sid)])
            case Assign(name=name, value=value, span=span):
                sid = self._push(span)
                return _call("set", [pyast.Constant(name), self.expr(value), pyast.Constant(sid)])
            case ConstAssign(name=name, value=value, span=span):
                # Inside a parenthesized sequence; the engine rejects constant
                # declarations off the top level with the node's span.
                sid = self._push(span)
                return _call("const_assign", [pyast.Constant(name), self.expr(value),
                                              pyast.Constant(sid)])
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
            case Call(head=head, args=args, kwargs=kwargs, span=span):
                head_expr = self.expr(head)
                arg_exprs = [self.expr(a) for a in args]
                # Kwargs lower to a dict literal: Python keyword arguments on the far
                # side of `app`, keyed by the source-level names, always present so
                # every application has the same generated shape.
                kw_dict = pyast.Dict(
                    keys=[pyast.Constant(kw.name) for kw in kwargs],
                    values=[self.expr(kw.value) for kw in kwargs],
                )
                sid = self._push(span)
                return _call(
                    "app",
                    [head_expr, pyast.Tuple(elts=arg_exprs, ctx=pyast.Load()), kw_dict,
                     pyast.Constant(sid)],
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
        elif isinstance(stmt, Import | PyImport):
            # One line, no `_result` — an import binds names and produces no output.
            method = "import_" if isinstance(stmt, Import) else "pyimport"
            lines.append(pyast.unparse(_call(method, [pyast.Constant(stmt.path),
                pyast.Constant(stmt.members), pyast.Constant(sid)])))
            continue
        else:
            expr = lowerer.expr(stmt)
        assignment = pyast.Assign(
            targets=[pyast.Name(id="_result", ctx=pyast.Store())], value=expr)
        lines.append(pyast.unparse(pyast.fix_missing_locations(assignment)))
    tree = pyast.parse("\n".join(lines))
    tree = pyast.fix_missing_locations(tree)
    return CompiledBody(compile(tree, "<adhoc>", "exec"), tuple(lowerer.spans), lowerer.definitions)
