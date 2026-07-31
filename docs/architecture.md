# Architecture

## Pipeline (phase 0)

```
source text
    │
    ▼
lexer (ad/lexer.lisp)           -- tokens: numbers, identifiers, \-names, operators
    │
    ▼
parser (ad/parser.lisp)         -- precedence-climbing over docs/grammar.md, produces an AST
    │
    ▼
ast (ad/ast.lisp)               -- s-expression nodes: :num-lit :var :bin-op :un-op :assign :seq
    │
    ▼
interpreter (interpreter/interpreter.lisp) -- tree-walking evaluator, environment = hash-table char->Num
    │                                          all arithmetic goes through num/num.lisp
    ▼
repl (repl/repl.lisp)           -- read/print loop, per-line error recovery
```

Errors at any stage carry a `[start, end)` character span (`ad-error-start`/`-end` on
lex/parse conditions); `ad/diagnostic.lisp`'s `render-diagnostic` turns a span plus the
source text into a caret-pointing error block. It's a sibling of the parser, not a pipeline
stage, so any consumer (the REPL today, script mode in phase 6) can call it directly.

`num/num.lisp` is a seam, not a pass in the pipeline — every stage that touches a number value
calls into it rather than using CL's arithmetic operators directly. See `docs/numerics.md`.

## ASDF subsystems

Each pipeline stage is its own top-level directory (`num/`, `ad/`, `interpreter/`, `repl/`,
`cli/`), a `package.lisp` plus its implementation file(s); the `.asd` groups each directory
into one system, so a later phase can swap one subsystem without touching the others:

| System | Role | Durability |
|---|---|---|
| `adhoc/num` | the numeric seam | durable |
| `adhoc/ad` | lexer, AST, parser, diagnostic rendering | durable |
| `adhoc/interpreter` | tree-walking evaluator | disposable (phase 4) |
| `adhoc/repl` | REPL glue | disposable |
| `adhoc/cli` | entry point | durable |
| `adhoc` | umbrella system | — |
| `adhoc/tests` | FiveAM suites | — |

## What's durable vs. disposable

The roadmap's phase 4 replaces the evaluator with an interaction-net engine (Lafont
combinators, graph rewriting to normal form) — a from-scratch design, not a port of an
existing engine. That phase only replaces `adhoc/interpreter`'s *reduction strategy*:

- **Durable** — `adhoc/ad` (lexer, AST shape, parser, diagnostic rendering) and `adhoc/num`.
  Phase 1-3 language features add AST tags and grow `adhoc/num`, but don't change this
  structure. The AST is s-expression data (`(:bin-op :+ lhs rhs)`, not typed structs)
  specifically so phase 5's `\expr`/`\eval`/`\body` can quote and rewrite it with ordinary
  list operations rather than a hand-built AST-as-data layer — this is also why token/error
  spans live alongside the AST rather than on it: appending a span slot to every node would
  break `equal` on two structurally identical expressions.
- **Disposable** — `adhoc/interpreter`'s tree-walk and `adhoc/repl`'s glue. These exist to
  validate language semantics before the interaction-net engine exists to test them against;
  they're expected to be deleted, not evolved, when phase 4 lands.

This is why phase 0 keeps the tree-walker deliberately simple: effort spent hardening it
beyond "correct enough to validate phase 1-3 semantics" doesn't carry forward.

## Launcher (`bin/adhoc`)

`bin/adhoc` execs a Roswell-built image (`adhoc` at the repo root, produced by `make build` /
`ros build adhoc.ros`), not `ros run` or `sbcl --script`. The difference is what happens at
launch: a dumped executable already has the whole system compiled and loaded into its image,
so starting it is just process startup — no ASDF resolution, no Quicklisp, no compilation.
Measured cold-start against a piped empty-input invocation, this is roughly an order of
magnitude faster than booting SBCL and quickloading the system fresh on every call.

`cli/cli.lisp`'s `main` handles three things a dumped image needs that an interactive REPL
session gets for free: `*read-default-float-format*` bound to `double-float` (CL's default is
`single-float`), stdin/stdout reopened with an explicit UTF-8 external format, and an
`*invoke-debugger-hook*` so an unhandled condition prints a message and exits instead of
dropping into SBCL's low-level debugger with no controlling terminal.

`bin/adhoc` also wraps the image in `rlwrap` when stdin is a tty and `rlwrap` is on `PATH`
(`ADHOC_NO_RLWRAP=1` to opt out), giving input history and line editing without touching the
dumped image or its Lisp dependencies. This is a launcher-level concern rather than an
in-process library (linedit, cl-readline) for two reasons: both in-process options are FFI
(linedit pulls in `osicat`/`cffi-grovel`, so it isn't the "no FFI" option it looks like), and
linedit's own docs say behaviour is unspecified once `*standard-input*` has been rebound,
which `cli/cli.lisp` does above for UTF-8. Piped input (tests, scripts) never goes through
`rlwrap`, since it only wraps on an interactive tty.

## Numeric tower (target shape, phase 3+)

The design's exact-arithmetic tower — bignum integers, bignum rationals, symbolic closed
forms, algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback — is described in
full in the project's design notes. `docs/numerics.md` covers what phase 0 actually
implements (the bottom two tiers) and where the seam for the rest goes.
