"""Lowering: adhoc AST → Python AST → compiled bytecode.

One generated Python source *line* per top-level adhoc statement, with two tables riding
alongside the code object: `spans` (sid-indexed, every lowered operation's span) and
`line_spans` (generated line number → statement span). Every operation routes through an
`Engine` method call carrying its sid (`_e.add(lhs, rhs, 3)`), which is what keeps
runtime-error spans narrow — a sub-expression's failure points at the sub-expression.

Lowering rules:

- `NumLit` → a compile-time `Constant` for `int`/`float` tiers, `_e.lit(text, sid)`
  for exact decimals (no source-safe literal exists for a `Fraction`, and generated
  code never loads a bare name). `StrLit` →
  `Constant` likewise — a string is an ordinary atom, so this shape serves call
  arguments, operands, and everything else.
- A bare-string *statement* lowers to `pass`: one generated line per statement keeps the
  lineno ↔ span table aligned while producing no output.
- Variables are never bare Python name loads or stores — reads go through `_e.var`,
  every `x = e` write-or-compare through `_e.assign` (declare-once-then-check: binds a
  fresh name into the current frame, compares against one already bound there; `\\let`
  passes the fresh-only mode). The user env is
  a plain dict the engine holds; it never mixes with the exec globals.
- `\name` lowers to `_e.bref("name", sid, spelling)`; application lowers to
  `_e.app(head, args, kwargs, sid, spelling)` with the kwargs as a dict literal;
  `\\py(path)` is the one backslash name with semantics of its own and lowers to
  `_e.py(path, sid, spelling)`. `FuncDef` registers a separately compiled body and
  lowers to `_e.define(...)`; the ternary lowers to lazy thunk calls (`_e.if_expr`).
  `Import`/`PyImport` lower to `_e.import_(path, members, sid, member_spellings)`/
  `_e.pyimport(...)`; `Fold`/`Limit` likewise register their bodies via `_compile_body`
  and lower to `_e.fold(...)`/`_e.limit(...)`, which evaluate the body once per
  term/probe in a child engine frame. Canonical names drive lookup; optional spelling
  metadata is used only for diagnostics and declaration echoes.
- `Seq` flattens; each statement becomes one line, matching script mode's per-statement
  echo and the line-number gutter.
"""

import ast as pyast
from dataclasses import dataclass, field
from types import CodeType

from .runtime import parse_literal
from .expression import ExpressionValue
from .span import Span
from .syntax import (
    ArrayLit,
    Assign,
    BackslashRef,
    BinOp,
    BinOperator,
    Call,
    Compare,
    CompareOperator,
    Fold,
    FuncDef,
    Hole,
    IfExpr,
    Import,
    Index,
    Lambda,
    Limit,
    Node,
    NoOp,
    NumLit,
    OpRef,
    PyImport,
    Quote,
    Eval,
    Range,
    Seq,
    SetLit,
    StrLit,
    TensorLit,
    Transpose,
    PowCall,
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
    BinOperator.DOT: "dot",
    BinOperator.UNION: "union",
    BinOperator.INTERSECT: "intersect",
    BinOperator.SETMINUS: "setminus",
    BinOperator.COMPOSE: "compose",
    BinOperator.MOD: "mod",
}

# The fold operator each Fold node accumulates with; the runtime maps these back to
# nadd/nmul (the only arithmetic a fold is allowed to perform).
_FOLD_METHODS = {
    BinOperator.ADD: "add",
    BinOperator.MUL: "mul",
}

_UN_METHODS = {
    UnaryOperator.NEG: "neg", UnaryOperator.FACT: "fact", UnaryOperator.DFACT: "dfact",
}

_CMP_METHODS = {
    CompareOperator.LT: "lt", CompareOperator.LE: "le",
    CompareOperator.GT: "gt", CompareOperator.GE: "ge",
    CompareOperator.IN: "member", CompareOperator.SUBSETEQ: "subseteq",
    CompareOperator.NE: "ne", CompareOperator.APPROX: "approx",
    CompareOperator.NOTIN: "notmember", CompareOperator.SUBSET: "subset",
    CompareOperator.SUPSETEQ: "supseteq", CompareOperator.SUPSET: "supset",
}


@dataclass(frozen=True)
class Compiled:
    source: str
    code: CodeType
    spans: tuple[Span, ...]
    line_spans: dict[int, Span]
    definitions: dict[int, "CompiledBody"] = field(default_factory=dict)
    quotes: dict[int, ExpressionValue] = field(default_factory=dict)


@dataclass(frozen=True)
class CompiledBody:
    code: CodeType
    spans: tuple[Span, ...]
    definitions: dict[int, "CompiledBody"]
    quotes: dict[int, ExpressionValue]
    node: Node
    source: str


def _call(method: str, args: list[pyast.expr]) -> pyast.expr:
    return pyast.Call(
        func=pyast.Attribute(
            value=pyast.Name(id=ENGINE, ctx=pyast.Load()), attr=method, ctx=pyast.Load()
        ),
        args=args,
        keywords=[],
    )


def _call_spelling(head: Node) -> str | None:
    match head:
        case Var(spelling=spelling) | BackslashRef(spelling=spelling):
            return spelling
        case _:
            return None


class _Lowerer:
    def __init__(self, source: str = ""):
        self.source = source
        self.spans: list[Span] = []
        self.definitions: dict[int, CompiledBody] = {}
        self.quotes: dict[int, ExpressionValue] = {}

    def _push(self, span: Span) -> int:
        self.spans.append(span)
        return len(self.spans) - 1

    def statement(self, stmt: Node) -> str:
        match stmt:
            case FuncDef(name=name, params=params, body=body, spelling=spelling,
                         param_spellings=param_spellings, span=span):
                return pyast.unparse(self._definition(name, params, body, spelling,
                                                       param_spellings, span, True))
            case Import(path=path, members=members, member_spellings=member_spellings,
                        span=span):
                sid = self._push(span)
                return pyast.unparse(_call("import_",
                    [pyast.Constant(path), pyast.Constant(members), pyast.Constant(sid),
                     pyast.Constant(member_spellings)]))
            case PyImport(path=path, members=members, member_spellings=member_spellings,
                          span=span):
                sid = self._push(span)
                return pyast.unparse(_call("pyimport",
                    [pyast.Constant(path), pyast.Constant(members), pyast.Constant(sid),
                     pyast.Constant(member_spellings)]))
            case StrLit() | NoOp():
                # A lone string is a comment-like no-op; `pass` keeps the one-line-per-
                # statement invariant that the lineno ↔ span table depends on.
                return "pass"
            case Assign(name=name, value=value, fresh_only=fresh_only,
                        spelling=spelling, span=span):
                sid = self._push(span)
                inner = self.expr(value)
                # Statement level echoes: the binding rule reports the outcome
                # (the echo or the comparison result) into the transcript.
                return pyast.unparse(_call("assign",
                    [pyast.Constant(name), inner, pyast.Constant(sid),
                     pyast.Constant(True), pyast.Constant(spelling),
                     pyast.Constant(fresh_only)]))
            case _:
                sid = self._push(stmt.span)
                inner = self.expr(stmt)
                return pyast.unparse(_call("out", [inner, pyast.Constant(sid)]))

    def _thunk(self, node: Node) -> pyast.expr:
        return pyast.Lambda(args=pyast.arguments(posonlyargs=[], args=[],
            kwonlyargs=[], kw_defaults=[], defaults=[]), body=self.expr(node))

    def _definition(self, name, params, body, spelling, param_spellings, span,
                    echo: bool) -> pyast.expr:
        sid = self._push(span)
        self.definitions[sid] = _compile_body(body, self.source)
        return _call("define", [pyast.Constant(name), pyast.Constant(params),
                                pyast.Constant(sid), pyast.Constant(spelling),
                                pyast.Constant(param_spellings), pyast.Constant(echo)])

    def expr(self, node: Node) -> pyast.expr:
        match node:
            case FuncDef(name=name, params=params, body=body, spelling=spelling,
                         param_spellings=param_spellings, span=span):
                return self._definition(name, params, body, spelling,
                                        param_spellings, span, False)
            case Quote(body=body, source=source, statement_body=statement_body, span=span):
                sid = self._push(span)
                self.quotes[sid] = ExpressionValue(body, source, statement_body)
                return _call("quote", [pyast.Constant(sid)])
            case Eval(value=value, bindings=bindings, span=span):
                sid = self._push(span)
                names = pyast.Constant(tuple(kw.name for kw in bindings))
                spellings = pyast.Constant(tuple(kw.spelling for kw in bindings))
                values = pyast.Tuple(elts=[self.expr(kw.value) for kw in bindings], ctx=pyast.Load())
                return _call("eval_expr", [self.expr(value), names, values, spellings,
                                           pyast.Constant(sid)])
            case NumLit(text=text, span=span):
                value = parse_literal(text)
                if isinstance(value, int | float):
                    # `int`/`float` constants embed at compile time — their repr
                    # round-trips through unparse exactly. An exact decimal
                    # (`0.5` is the rational 1/2) has no source-safe literal,
                    # so it lowers through the seam instead of a bare name.
                    return pyast.Constant(value=value)
                sid = self._push(span)
                return _call("lit", [pyast.Constant(text), pyast.Constant(sid)])
            case StrLit(text=text):
                return pyast.Constant(value=text)
            case OpRef(name=name, span=span):
                return _call("op", [pyast.Constant(name), pyast.Constant(self._push(span))])
            case Var(ch=ch, spelling=spelling, span=span):
                sid = self._push(span)
                return _call("var", [pyast.Constant(ch), pyast.Constant(sid),
                    pyast.Constant(spelling)])
            case BackslashRef(name=name, spelling=spelling, span=span):
                sid = self._push(span)
                return _call("bref", [pyast.Constant(name), pyast.Constant(sid),
                    pyast.Constant(spelling)])
            case UnOp(op=op, operand=operand, span=span):
                inner = self.expr(operand)
                sid = self._push(span)
                return _call(_UN_METHODS[op], [inner, pyast.Constant(sid)])
            case BinOp(op=op, lhs=lhs, rhs=rhs, span=span):
                left = self.expr(lhs)
                right = self.expr(rhs)
                sid = self._push(span)
                return _call(_BIN_METHODS[op], [left, right, pyast.Constant(sid)])
            case Compare(op=op, lhs=lhs, rhs=rhs, span=span):
                sid = self._push(span)
                return _call(_CMP_METHODS[op], [self.expr(lhs), self.expr(rhs), pyast.Constant(sid)])
            case TensorLit(items=items, row_length=row_length, span=span):
                sid = self._push(span)
                return _call("tensor", [pyast.Tuple(elts=[self.expr(i) for i in items],
                                                    ctx=pyast.Load()),
                                        pyast.Constant(row_length), pyast.Constant(sid)])
            case ArrayLit(items=items, span=span):
                sid = self._push(span)
                return _call("array", [pyast.Tuple(elts=[self.expr(i) for i in items],
                                                   ctx=pyast.Load()),
                                       pyast.Constant(sid)])
            case SetLit(items=items, span=span):
                sid = self._push(span)
                return _call("set_", [pyast.Tuple(elts=[self.expr(i) for i in items],
                                                  ctx=pyast.Load()),
                                      pyast.Constant(sid)])
            case Index(head=head, items=items, span=span):
                head_expr = self.expr(head)
                sid = self._push(span)
                return _call("index", [head_expr,
                                       pyast.Tuple(elts=[self.expr(i) for i in items],
                                                   ctx=pyast.Load()),
                                       pyast.Constant(sid),
                                       pyast.Constant(_call_spelling(head))])
            case Transpose(operand=operand, span=span):
                inner = self.expr(operand)
                sid = self._push(span)
                return _call("transpose", [inner, pyast.Constant(sid)])
            case Range(start=start, second=second, end=end, span=span):
                sid = self._push(span)
                return _call("range", [self.expr(start),
                    self.expr(second) if second is not None else pyast.Constant(None),
                    self.expr(end) if end is not None else pyast.Constant(None),
                    pyast.Constant(sid)])
            case IfExpr(condition=condition, then_branch=then_branch, otherwise=otherwise, span=span):
                sid = self._push(span)
                return _call("if_expr", [self.expr(condition), self._thunk(then_branch),
                    self._thunk(otherwise) if otherwise is not None else pyast.Constant(None),
                    pyast.Constant(sid)])
            case Fold(op=op, var=var, bound=bound, body=body, spelling=spelling,
                      var_spelling=var_spelling, span=span):
                # Same shape as FuncDef: the folded body is compiled once into
                # `definitions[sid]`; the engine evaluates it per term in a child frame.
                sid = self._push(span)
                self.definitions[sid] = _compile_body(body, self.source)
                return _call("fold", [pyast.Constant(_FOLD_METHODS[op]),
                    pyast.Constant(var), self.expr(bound), pyast.Constant(sid),
                    pyast.Constant(spelling), pyast.Constant(var_spelling)])
            case Limit(var=var, point=point, body=body, spelling=spelling,
                      var_spelling=var_spelling, span=span):
                sid = self._push(span)
                self.definitions[sid] = _compile_body(body, self.source)
                return _call("limit", [pyast.Constant(var), self.expr(point),
                                       pyast.Constant(sid), pyast.Constant(spelling),
                                       pyast.Constant(var_spelling)])
            case Lambda(params=params, body=body, param_spellings=param_spellings,
                        span=span):
                # Same shape as FuncDef/Fold: the body compiles once into
                # `definitions[sid]`; the engine materializes an anonymous
                # AdFunction closed over the defining frame. The `_e.lambda_`
                # call carries the span id, so body errors stay narrow.
                sid = self._push(span)
                self.definitions[sid] = _compile_body(body, self.source)
                return _call("lambda_", [pyast.Constant(params), pyast.Constant(sid),
                                         pyast.Constant(param_spellings)])
            case Assign(name=name, value=value, fresh_only=fresh_only,
                        spelling=spelling, span=span):
                # Assign is legal in expression position (a parenthesized sequence's
                # statements compile through here); the engine's one binding rule
                # covers every context — frame-local fresh bind or compare.
                sid = self._push(span)
                return _call("assign", [pyast.Constant(name), self.expr(value),
                                        pyast.Constant(sid), pyast.Constant(False),
                                        pyast.Constant(spelling),
                                        pyast.Constant(fresh_only)])
            case Seq(statements=statements):
                return pyast.Subscript(
                    value=pyast.Tuple(elts=[self.expr(s) for s in statements], ctx=pyast.Load()),
                    slice=pyast.Constant(-1), ctx=pyast.Load())
            case Call(head=BackslashRef(name="py", spelling=spelling), args=args,
                      span=span):
                # `\py` is the one backslash name with its own semantics: resolve the
                # single string-literal argument to a Python callable. Parser enforces
                # arity; the engine rejects non-string arguments with the same span.
                sid = self._push(span)
                arg_exprs = [self.expr(a) for a in args]
                return _call("py", [*arg_exprs, pyast.Constant(sid),
                                     pyast.Constant(spelling)])
            case Call(head=head, args=args, kwargs=kwargs, span=span) \
                    if any(isinstance(a, Hole) for a in args):
                # A hole makes the call a partial application: holes travel as
                # `None` slots plus their positions.
                sid = self._push(span)
                slots = [pyast.Constant(None) if isinstance(a, Hole) else self.expr(a)
                         for a in args]
                holes = [pyast.Constant(i) for i, a in enumerate(args) if isinstance(a, Hole)]
                kw_dict = pyast.Dict(
                    keys=[pyast.Constant(kw.name) for kw in kwargs],
                    values=[self.expr(kw.value) for kw in kwargs],
                )
                return _call(
                    "partial",
                    [self.expr(head), pyast.Tuple(elts=slots, ctx=pyast.Load()),
                     pyast.Tuple(elts=holes, ctx=pyast.Load()), kw_dict,
                     pyast.Constant(sid), pyast.Constant(_call_spelling(head))],
                )
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
                     pyast.Constant(sid), pyast.Constant(_call_spelling(head))],
                )
            case PowCall(head=head, exponent=exponent, args=args, kwargs=kwargs, span=span):
                head_expr = self.expr(head)
                exponent_expr = self.expr(exponent)
                arg_exprs = [self.expr(a) for a in args]
                kw_dict = pyast.Dict(
                    keys=[pyast.Constant(kw.name) for kw in kwargs],
                    values=[self.expr(kw.value) for kw in kwargs],
                )
                sid = self._push(span)
                return _call(
                    "pow_app",
                    [head_expr, exponent_expr, pyast.Tuple(elts=arg_exprs, ctx=pyast.Load()),
                     kw_dict, pyast.Constant(sid), pyast.Constant(_call_spelling(head))],
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


def compile_program(node: Node, original_source: str = "") -> Compiled:
    lowerer = _Lowerer(original_source)
    stmts = _flatten(node)
    lines = [lowerer.statement(s) for s in stmts]
    source = "\n".join(lines)
    code = compile(source, "<adhoc>", "exec")
    line_spans = {i + 1: s.span for i, s in enumerate(stmts)}
    return Compiled(source=source, code=code, spans=tuple(lowerer.spans), line_spans=line_spans,
                    definitions=lowerer.definitions, quotes=lowerer.quotes)


def _compile_body(node: Node, source: str = "") -> CompiledBody:
    lowerer = _Lowerer(source)
    statements = _flatten(node)
    lines = ["_result = None"]
    for stmt in statements:
        if isinstance(stmt, StrLit):
            expr = pyast.Constant(None)
        elif isinstance(stmt, Import | PyImport):
            # One line, no `_result` — an import binds names and produces no output.
            sid = lowerer._push(stmt.span)
            method = "import_" if isinstance(stmt, Import) else "pyimport"
            lines.append(pyast.unparse(_call(method, [pyast.Constant(stmt.path),
                pyast.Constant(stmt.members), pyast.Constant(sid),
                pyast.Constant(stmt.member_spellings)])))
            continue
        else:
            expr = lowerer.expr(stmt)
        assignment = pyast.Assign(
            targets=[pyast.Name(id="_result", ctx=pyast.Store())], value=expr)
        lines.append(pyast.unparse(pyast.fix_missing_locations(assignment)))
    tree = pyast.parse("\n".join(lines))
    tree = pyast.fix_missing_locations(tree)
    return CompiledBody(compile(tree, "<adhoc>", "exec"), tuple(lowerer.spans),
                        lowerer.definitions, lowerer.quotes, node, source)


def compile_expression(node: Node, source: str = "") -> CompiledBody:
    lowerer = _Lowerer(source)
    assignment = pyast.Assign(
        targets=[pyast.Name(id="_result", ctx=pyast.Store())], value=lowerer.expr(node))
    tree = pyast.Module(body=[assignment], type_ignores=[])
    code = compile(pyast.fix_missing_locations(tree), "<adhoc>", "exec")
    return CompiledBody(code, tuple(lowerer.spans), lowerer.definitions, lowerer.quotes,
                        node, source)
