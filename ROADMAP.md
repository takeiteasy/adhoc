# Roadmap

[GitHub issues](https://github.com/takeiteasy/adhoc/issues) record ticket status. This page groups the implementation by phase
and lists planned or unscheduled work. See the [language guide](docs/language.md)
for supported features and [design](DESIGN.md) for the language model.

## Implementation phases

| Phase | Scope | Current reference |
|---|---|---|
| 0: Foundations | Python package, lexer, parser, spans, diagnostics, REPL and script runner | [Architecture](docs/architecture.md) |
| 1: Language semantics | Functions, recursion, immutable bindings, booleans, conditionals, ranges, folds and limits | [Language guide](docs/language.md) |
| 2: Exact arithmetic | Rational, Gaussian, symbolic, algebraic and RRA tiers; precision and equality | [Numerics](docs/numerics.md) |
| 3: Collections | Tensors, arrays and sets | [Collection syntax](docs/grammar.md#tensors) |
| 4: Symbolic and higher-order operations | Quotes, evaluation, reflection, beta reduction, rewriting, composition and custom operators | [Symbolic rewriting](docs/symbolic.md), [operators](docs/operators.md) |
| 5: Graphing | Sampling, terminal rendering and export | [Planned graphing](#graphing) |

### Foundations and semantics

The durable engine lowers frozen language AST nodes to Python AST and executes
on CPython. Later phases extend the language and runtime operations.

Functions and binders use local frames. Bindings are immutable; `=` binds or
checks, and `\let` requires a fresh name. Prelude names are protected except `i`.
The ternary is lazy; parenthesized statement groups provide multi-statement
bodies. Numeric convergence errors at its budget instead of returning an
unconfirmed partial result.

### Exact arithmetic

Exact decimals, complex arithmetic, symbolic closed forms, algebraic values and
RRA approximation are implemented. Results simplify into lower tiers when
possible. RRA equality uses the Richardson–Fitch heuristic; see
[numeric limitations](docs/numerics.md#limitations).

`\prec` sets RRA display precision from 1 to 1000 significant digits. Explicit
float spellings and float operands select real or complex float arithmetic.

### Collections and symbolic operations

Tensors use 1-based indexing, scalar broadcasting, elementwise algebra,
`@` contraction and transpose. Arrays hold heterogeneous ordered values;
sets deduplicate and provide set operations.

Expression quotes support `\eval`, `\body` and `\reduce`. Symbolic operations
rewrite supported quotes and functions with a time limit. Composition, partial
application, higher-order collection functions and custom infix declarations
use first-class functions.

## Graphing

Graphing depends on numeric evaluation and is not implemented.

| Area | Proposed behavior | Open decision |
|---|---|---|
| Domain | `\graph(f, x=a..b)` samples a function over a range | Fixed resolution or adaptive sampling |
| Terminal output | Sixel or Kitty graphics, with Unicode braille fallback | Protocol detection and rendering details |
| Export | Python calls with ordinary strings, such as `\py("matplotlib.pyplot.savefig")("plot.svg")` | Integration with generated plots |
| Overlays | Several functions on shared axes | Syntax |

## Future directions

These ideas are unscheduled. Their syntax and semantics require design decisions
before implementation.

| Direction | Scope or open question |
|---|---|
| Literate script mode | Markdown or LaTeX transcripts with results beside source; bare string notes already work |
| Congruence notation | Possible `a ≡ b (mod n)` form; `≡` is reserved |
| Exactness introspection | Query a value's numeric tier, with proposed `\exact(v)` |
| Multi-clause definitions | First matching clause; distinguish clauses from repeated binding checks |
| Recurrence-defined lazy sequences | Memoized recurrence values that ranges and folds can consume |
| Units and dimensional analysis | Unit notation and dimension checks at numeric operations |
| Arbitrary-precision float tier | MPFR or gmpy2 behind numeric operations; precision API remains open |
| Module system | Module namespaces, Python attribute access and protection of imported bindings |
| Interaction-net backend | Native numeric agents and local graph reduction; separate from the CPython engine |

Number-theory functions and postfix factorials are in the
[standard library](docs/stdlib.md#number-theory). RRA display precision uses
`\prec`; it is separate from the proposed arbitrary-precision float tier.
