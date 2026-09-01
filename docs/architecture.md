# Architecture

## Layout

`adhoc` is one Python package. The library modules *are* the language; `__main__` and `repl`
are thin drivers over it, depending on it the way any other consumer would.

```
adhoc/
├── span        — byte-offset spans (start, end)
├── lexer       — tokens: numbers, strings, identifiers, \-names, operators, the √ radical
├── syntax      — frozen AST dataclasses, each node carries its own Span
├── parser      — precedence climbing over docs/grammar.md
├── runtime     — the numeric seam + lazy ranges + Engine (everything lowered code calls into),
│                 plus the \py boundary and its conversion matrix
├── symbolic    — the symbolic closed-form tier behind the seam (coefficient × atom,
│                 backed by sympy; only runtime.py dispatches into it)
├── compiler    — lowering: adhoc AST → Python source, one line per statement
├── driver      — compile/exec pairing, error mapping back through spans
├── diagnostic  — caret-pointing renderer
├── output      — shared error printing for both drivers
└── repl        — prompt loop, continuation, history (__main__ dispatches argv)
```

## Pipeline

```
source text
    │
    ▼
lexer (lexer.py)       -- tokens with byte-offset spans
    │
    ▼
parser (parser.py)     -- precedence climbing → syntax.py dataclasses, spans tagged at construction
    │
    ▼
compiler (compiler.py) -- lowering to Python source: one line per statement,
    │                    every operation an Engine call carrying a span id
    ▼
driver (driver.py)     -- compile() + exec() against an Engine; user env is a plain dict
    │                    the engine holds; EvalError carries narrow spans
    ▼
repl / __main__        -- read/print loop or script-file driver via output.py rendering
```

The evaluation engine is CPython itself: generated code runs through `compile()`/`exec`, so
the language's arithmetic semantics live entirely in `runtime.py`'s helpers (`nadd`/.../
`nshow` plus the `Engine` methods), never in operators applied directly to user values. See
`docs/numerics.md` for the seam and its pinned float semantics.

## Spans and diagnostics

Every token and every AST node carries a `Span` — byte offsets, 0-based, half-open — tagged
at construction time by the parser (at construction, not on unwind, so `(expr)` returns the
inner node's own narrower span rather than a paren-inclusive one). The compiler allocates a
span id per lowered operation and emits it as an argument; `runtime.Engine` raises
`EvalError(msg, span)` from that id when an operation fails. This preserves per-node span
narrowing end-to-end: in `1 + x`, an unbound-`x` failure points at `x`, not at the statement;
in `2 + 1/0`, the division-by-zero points at `1/0`.

`diagnostic.render(source, label, message, span)` takes a span and a message rather than an
error value, which is what lets the REPL and script mode share it unchanged — the one
difference between them is *when* each calls it, not how the output looks.

## Engine notes

- One generated Python line per top-level statement, with a `lineno → span` table riding on
  the compiled unit; anything unexpected escaping the engine maps back through it. A bare
  string statement lowers to `pass` — it produces no output but keeps the one-line-per-
  statement invariant the table depends on.
- Variables never become Python name loads or stores — reads go through `_e.var`, writes
  through `_e.assign` (bind-or-compare; globals are single-assignment). Function calls create a
  local frame with global read-through; body writes use `_e.set` and never escape. The user
  environment is a plain dict kept separate from exec globals. Callables bind like any
  value; strings never enter it.
- Application lowers to `_e.app(head, args, kwargs, sid)` with dynamic juxtaposition:
  callable heads apply (kwargs pass through as native Python keyword arguments); a
  non-callable head with one positional argument and no kwargs falls back to
  multiplication; anything else fails at the call's span. Definitions lower to callable
  `AdFunction` values;
  each body has its own compiled code and span table, and recursion pre-binds the function
  name in the call frame. The ternary `? :` is a lazy compiler special form (not an
  eager ordinary call).
  `\py(path)` has its own seam method
  resolving the dotted path and converting results back through the matrix
  (docs/numerics.md). Imports lower to `_e.import_(path, members, sid)` and
  `_e.pyimport(...)`: the session's module registry (absolute path → module
  environment), the import base directory, and the in-progress import chain ride on
  the root engine and are inherited by every child frame and imported module engine,
  which is what makes re-imports cached, cycles typed errors, and nested resolution
  relative to the importing file.
- Range construction lowers to `_e.range(start, second, end, sid)`. `RangeValue` stores
  numeric endpoints and step without materializing values; iteration computes each next
  value through the numeric seam.
- Folds and limits lower like definitions: `Fold`/`Limit` compile their bodies via
  `_compile_body` into the unit's `definitions` table and emit one engine call —
  `_e.fold(op, "i", <range>, sid)` / `_e.limit("x", <point>, sid)`. The engine evaluates
  the body once per term or probe in a fresh child frame (the `AdFunction.__call__`
  scoping pattern: parent read-through, local writes); all accumulation arithmetic runs
  through the numeric seam inside `runtime.py`, never in generated code. The convergence
  knobs and their shared plateau test also live there (docs/numerics.md).
- Statement outputs accumulate in order; the REPL prints only the last, script mode echoes
  every statement and stops at the first failure.

## The lowering is the engine

There is no bootstrap-then-replace split here: the compiler + CPython execution is the
durable implementation, not a stand-in for something else. The interaction-net direction in
`DESIGN.md` remains a recorded future direction, not scheduled work — nothing here expects to
be replaced by it.
