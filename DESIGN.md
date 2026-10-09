# Design

ADhoc Higher Order Calculator is a command-line calculator and math-notation
language. The language is `ad`; the executable is `adhoc`. This page summarizes
the language model and unscheduled directions. Use the
[language guide](docs/language.md) and [grammar](docs/grammar.md) for current
syntax and the [roadmap](ROADMAP.md) for planned work.

## Names and notation

Names are case-sensitive. Bare names are single ASCII or Unicode letters with
optional subscripts; longer names use a backslash. Whitespace separates tokens,
and newlines separate complete statements. `--` starts a line comment.

| Form | Meaning |
|---|---|
| `ab`, `2x` | Implicit multiplication |
| `x₁`, `x_1` | The same subscripted name, distinct from `x` |
| `\fact`, `\my_var` | Multi-character names |
| `π`, `\pi` | Two spellings of one constant |
| `Σ`, `\sum` | Two spellings of one binder |
| `√x`, `\sqrt(x)` | Operator and function spellings of a square root |

Unicode notation has ASCII alternatives. Backslash names follow LaTeX spellings
where available; `ad` has no TeX document or layout commands. Bracket forms,
such as `⟨…⟩`, have ASCII forms (`#[…]`, `\arr(...)`). Custom operator declarations
accept backslash names or unused mathematical glyphs.

See [notation](docs/notation.md) for glyphs and
[precedence](docs/grammar.md#precedence-table) for grouping.

## Equality and bindings

`=` is a statement-level bind-or-check operator. Bindings are immutable.

| Current-frame name | Effect of `name = expr` |
|---|---|
| Fresh | Bind and echo the value |
| Already bound | Compare and echo `true` or `false` |
| Protected prelude name | Redefinition error |

`\let name = expr` requires a fresh binding. Function definitions and top-level
`\let f(x) = body` also require fresh names. A call's keyword arguments and a
binder's `name=value` syntax are separate from assignment.

Prelude names cannot be rebound or shadowed, except `i`, which can serve as a
local parameter or loop variable. `i` and `\i` share a binding; inside a shadowing
scope, `\complex(0, 1)` still supplies the imaginary unit.

```text
x = 3
x = 4                 -> false
f(a, b) = c = ab; cc
f(3, 4)               -> = 144
```

Function calls create local frames. Reads search enclosing scopes; bindings and
checks stay local. See [assignment semantics](docs/grammar.md#assignment-semantics).

## Conditionals and functions

Functions are first-class, support recursion and capture their defining scope.
Lambdas use `\fn`, `\λ` or an arrow, such as `x ↦ x^2`.

The ternary `condition ? then : otherwise` evaluates only its selected branch.
Conditions require booleans; numbers have no truthiness. Comparisons return
booleans, and `∧ ∨ ¬ → ↔` supply logic. Parenthesized statement groups supply
multi-statement bodies and branches without creating a scope.

```text
f(x) = x >= 0 ? x : -x
f(-3)                    -> = 3
1 < 2 ? (x = 4; x + 1) : 0
```

## Ranges and binders

| Range | Meaning |
|---|---|
| `a..b` | Step 1, including the endpoint when reached |
| `a..` | Infinite lazy range |
| `a,c..b` | Finite range with step `c-a` |
| `a,c..` | Infinite range with inferred step |

Folds bind a local variable over a range or collection. Finite sums and products
preserve exact arithmetic; infinite folds approximate partial results with
convergence checks and a term cap. Numeric limits probe around an anchor without
evaluating at it. Failure to converge is a typed error.

```text
Σ(i=1..10) i^2          -> = 385
Π(i=1..5) i            -> = 120
\lim(x=0) \sin(x)/x    -> = 1.0
```

See [convergence](docs/numerics.md#convergence) and [calculus](docs/calculus.md)
for numeric derivatives, integrals and function inverses.

## Collections

| Kind | Syntax | Contract |
|---|---|---|
| Tensor | `[1, 2; 3, 4]` | Uniform numeric shape; elementwise algebra and contraction |
| Array | `⟨1, [2, 3], "a"⟩`, `#[…]`, `\arr(...)` | Ordered, heterogeneous and possibly ragged; indexing and iteration |
| Set | `{1, 2, 3}` | Unordered and deduplicated; set operations and membership |

Indexing is 1-based. Vectors and matrices are order-1 and order-2 tensors;
higher orders nest tensor literals. `'` transposes tensors; `@` contracts.
Set operators have infix ASCII equivalents such as `\cup`, `\cap`, `\in`,
`\setminus` and `\subseteq`.

Strings are values. They bind, concatenate with `+` and compose Python paths.
A bare string statement is a silent note. Strings have no indexing, ordering
or equality expression; repeated bindings check equality by content.

## Symbolic algebra and metaprogramming

Expression values store frozen syntax without evaluating it.

| Operation | Form |
|---|---|
| Quote | `\expr(x^2 - 4)` or backtick quote |
| Evaluate with local bindings | `\eval(q, x=3)` |
| Reflect a function body | `\body(f)` |
| Beta-reduce a quote | `\reduce(q)` |
| Rewrite or solve | `\simplify`, `\expand`, `\factor`, `\solve`, `\deriv`, `\grad` |
| Compose | `f ∘ g`, `f \circ g` |
| Partially apply | `f(a, ·)`, `f(a, _)` |
| Transform collections | `\map`, `\filter`, `\fold`, `\scan` |
| Declare an infix operator | `\infix(11) ⊕(a,b) = a+b` |

```text
q = \expr(x^2 - 4)
\solve(q)                  -> = {-2, 2}
\eval(q, x=3)              -> = 5
\simplify(\expr((x+1)^2 - x^2 - 2x))
                           -> = \expr(1)
```

See [symbolic rewriting](docs/symbolic.md), [custom operators](docs/operators.md)
and [quotes](docs/grammar.md#quotes-and-evaluation) for supported syntax.

## Exact arithmetic (internals)

The numeric runtime chooses the lowest tier that can hold an exact result.
Integers and rationals use arbitrary precision; Gaussian rationals extend them
to complex values. Symbolic closed forms, algebraic numbers and RRA use SymPy.

| Exact tier | Values |
|---|---|
| Integer and rational | `3`, `1/3`; decimal `0.5` is exactly `1/2` |
| Gaussian rational | `2+3i` |
| Symbolic | Rational coefficient times one recognized atom, such as `π` or `√2` |
| Algebraic | Roots and algebraic combinations beyond symbolic closed forms |
| RRA | Other finite exact values, approximated on demand from a tolerance |

Results collapse to lower tiers when possible: `√2 * √2` is `2` and
`(π + 1) - π` is `1`. Negative bases with exact odd-denominator exponents take
the real root branch; other fractional powers use the complex principal value.

Floats use explicit spellings (`1.`, `5e-1`). A float operand selects float or
complex float arithmetic. Complex values are not ordered.

Exact rationals display as fractions. Exact irrational values display approximate
digits with an ellipsis; `\prec` controls RRA display precision. Equality is exact
for rational, symbolic and algebraic tiers, and heuristic for RRA. See
[numeric limitations](docs/numerics.md#limitations).

## Execution modes

`adhoc` runs a REPL; `adhoc run script.ad` runs a file using the same grammar.
Both share caret diagnostics. The REPL prints the last output; script mode echoes
statements in order and stops at the first failure. Evaluation lowers to Python
AST and runs on CPython. See [architecture](docs/architecture.md).

## Graphing

Graphing is planned, with proposed syntax `\graph(f, x=a..b)`. The proposed
terminal output detects sixel or Kitty graphics support and falls back to Unicode
braille plots. File export uses ordinary strings at the Python boundary.

Sampling strategy and multi-function overlay syntax remain open. See the
[roadmap](ROADMAP.md#graphing).

## Interaction combinators

An interaction-net backend is an unscheduled alternative to CPython lowering.
The proposed model connects agents through principal and auxiliary ports;
connected principal ports form active pairs that reduce by local rules.

| Agent or rule | Role |
|---|---|
| Constructor γ, duplicator δ, eraser ε | Base interaction combinators |
| Annihilation | Matching agent types cancel and reconnect their remaining wires |
| Commutation | Different agent types duplicate past one another |
| Native numeric agents | Perform operations on the exact numeric tower |

The proposal represents quoted expressions as subnets and higher-order operations
through graph duplication and erasure. A sequential reference reducer precedes
any parallel active-pair reduction. Internal agent names do not appear in `ad`
source. The [roadmap](ROADMAP.md#future-directions) does not schedule this backend.
