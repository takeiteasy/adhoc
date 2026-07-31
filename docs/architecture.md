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
repl (repl/repl.lisp)           -- read/print loop, per-statement error recovery
```

Errors at any stage carry a `[start, end)` character span (`ad-error-start`/`-end` on
lex/parse conditions, `ad-eval-error-start`/`-end` on eval conditions); `ad/diagnostic.lisp`'s
`render-diagnostic` turns a span plus the source text into a caret-pointing error block. It's
a sibling of the parser, not a pipeline stage, so any consumer (the REPL today, script mode in
phase 6) can call it directly.

Eval-error spans come from a side table, not a slot on the AST nodes: `ad/parser.lisp` builds
an `eq` hash-table `node -> (start . end)` alongside the AST as it parses (`*node-spans*`,
registered at each `make-*` call site) and returns it as `parse-program`'s second value. The
interpreter binds it around a call to `run!` and looks up the offending node when it signals
an `ad-eval-error`, so `1 + x` underlines just `x` and `2 + 1/0` just `1/0`, rather than the
whole line. This is what "spans live alongside the AST" (below) means in practice — the table
is disposable along with the tree-walker at phase 4, same as the interpreter that consults it.

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
| `adhoc/cli` | entry point, in-process line editing (cl-readline) | durable |
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

Input history and in-line editing come from an in-process `cl-readline` session
(`cli/lineedit.lisp`), confined to `adhoc/cli` so `adhoc/repl` — and `adhoc/tests`, which
depends on it — stays free of the libreadline dependency; `make test` never needs libreadline
installed. `cli/cli.lisp`'s `main` enables it when stdin is an interactive tty and
`ADHOC_NO_READLINE` isn't set; piped input (tests, scripts) never engages it. Readline reads
file descriptor 0 directly in C, bypassing the Lisp stream `%reopen-stdio-utf8` builds around
it, so a session picks exactly one reader for its whole run — `adhoc/repl:run-repl`'s
`read-line-fn` argument is the hook that lets `cli/lineedit.lisp` supply that reader without
`adhoc/repl` knowing cl-readline exists. `setlocale(LC_ALL, "")` runs before the first read so
multi-byte UTF-8 identifiers (`π`, ...) round-trip through in-line editing correctly. History
persists to `$ADHOC_HISTORY` (`~/.adhoc_history` by default — the same path `bin/adhoc` always
passed to `rlwrap -H`) across runs.

`adhoc/cli` has a hard `:depends-on` on `cl-readline`, so a machine without libreadline can't
produce a dumped image at all — `make build` fails there, same as it would for a missing
`fiveam` or `cffi`. `adhoc/repl` and `make test` have no such requirement (see the ASDF table
above). Given a build that *did* succeed, `bin/adhoc` still probes the dumped image with
`adhoc --has-readline` on an interactive tty to ask whether *this invocation* can use the
in-process path — `readline-available-p` can say no for reasons that only show up at runtime,
not build time: `ADHOC_NO_READLINE` set, stdin not a tty, or `init-readline` failing (an
unreadable history file, a locale that isn't installed). Only then does `bin/adhoc` fall back
to wrapping the image in `rlwrap` instead, the ticket 29 mechanism, exporting
`ADHOC_NO_READLINE=1` into the wrapped process so the two editors can never both try to read
fd 0 at once (`rlwrap` presents a pty, so `isatty(0)` would otherwise be true inside it and
in-process readline would try to engage too). `ADHOC_NO_RLWRAP=1` opts out of that fallback as
well — note that `ADHOC_NO_READLINE=1` alone still lands on `rlwrap` if it's on `PATH`; both
variables are needed to get no editing at all. Piped input skips the probe entirely and execs
the image directly, so it never pays for the extra process start.

## Numeric tower (target shape, phase 3+)

The design's exact-arithmetic tower — bignum integers, bignum rationals, symbolic closed
forms, algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback — is described in
full in the project's design notes. `docs/numerics.md` covers what phase 0 actually
implements (the bottom two tiers) and where the seam for the rest goes.
