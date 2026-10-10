# Architecture

`adhoc` parses math notation into a frozen syntax tree, lowers it to Python AST
and executes it on CPython. Runtime helpers implement language semantics and
attach errors to source spans. The REPL and script runner use the same library.

## Pipeline

| Stage | Module | Output |
|---|---|---|
| Tokenize | `lexer.py` | Tokens with byte-offset spans |
| Parse | `parser.py` | Frozen `syntax.py` nodes with canonical names and source spellings |
| Lower | `compiler.py` | Python AST and compiled code; operations call `Engine` with span IDs |
| Execute | `driver.py` | Run code against an `Engine` holding the user environment |
| Display | `repl.py`, `__main__.py`, `output.py` | Results and shared caret diagnostics |

Arithmetic on user values goes through the
[numeric operations](numerics.md), including tensor operations. Generated code
uses runtime calls rather than direct Python arithmetic or variable access.
See [runtime lowering](lowering.md) for the operation mapping.

## Package layout

| Module | Responsibility |
|---|---|
| `span` | Zero-based, half-open byte spans |
| `lexer` | Literals, names, operators and punctuation |
| `syntax` | Frozen AST dataclasses |
| `parser` | Precedence climbing, aliases and custom operator declarations |
| `expression` | Frozen expression values and parseable display |
| `reduction` | Beta reduction of quoted expressions |
| `rewrite` | Bridge between quotes or function bodies and SymPy |
| `tex` | LaTeX rendering of syntax and values |
| `tensor` | Tensors, arrays and sets; indexing, slicing and tensor operations |
| `linalg` | Matrix elimination, constructors and tensor products |
| `eigen` | SymPy exact eigensystems and NumPy numerical eigenpairs on backend scalars |
| `runtime` | Numeric dispatch, `Engine`, lazy ranges, interval bounds, Python interop and numeric calculus |
| `gauss` | Gaussian rationals using exact component arithmetic |
| `symbolic` | Rational coefficient times one recognized SymPy atom |
| `algebraic` | Exact algebraic SymPy values |
| `rra` | Other finite exact values and tolerance-based approximation |
| `compiler` | Lower language AST into Python AST and bytecode |
| `driver` | Compile/execute pairing and unexpected-error mapping |
| `diagnostic` | Caret renderer |
| `output` | Error printing shared by both drivers |
| `repl` | Prompts, continuation and history |
| `__main__` | Command-line dispatch and script running |

## Spans and diagnostics

Tokens and syntax nodes carry byte spans. The compiler assigns each lowered
operation a span ID; runtime failures produce `EvalError(message, span)`.
Errors therefore point to the failing subexpression:

| Source | Error points to |
|---|---|
| `1 + x` with unbound `x` | `x` |
| `2 + 1/0` | `1/0` |

`diagnostic.render` converts byte offsets to character columns and accepts a
message and span. Both drivers share this renderer.[^spans]

Names also retain their written spelling for diagnostics and fresh declaration
echoes. Canonical names determine lookup, protection, recursion and identity.[^spelling]

## Quotes and function bodies

Quoted values retain frozen syntax and original source. `\eval` compiles the
stored syntax through the same lowering path and runs it in a child frame.
Binding values evaluate in the caller first. Errors retain the quote's source,
including across REPL submissions.

Function bodies retain their AST and defining source. `\body` wraps a body as
a statement-sequence expression value. Evaluation keeps its bindings local and
returns the last statement's value. Nested definitions use the compiled-body
table and return their callable without adding an output line.

`\reduce` preserves free names and original spans while beta-reducing quotes.[^reduction]

## Execution model

The user environment is separate from Python execution globals. Reads walk
parent frames; bindings and checks stay local. Functions, binders and probes use
child frames. See [runtime lowering](lowering.md) for scope and dispatch details.

CPython lowering is the evaluation engine. The interaction-net design in
[DESIGN.md](../DESIGN.md#interaction-combinators) is an unscheduled alternative.

[^spans]: Spans use `[start, end)` byte offsets. Never apply them directly to a
    Python string slice, which uses character offsets. The parser tags spans at
    construction; `(expr)` retains the inner node's narrower span.

[^spelling]: Written spelling is optional, non-semantic metadata with
    `compare=False` on name-bearing AST nodes. It travels through compilation to
    the engine without participating in identity.

[^reduction]: Reduction substitutes through De Bruijn indices, then restores
    parseable names in the returned expression.
