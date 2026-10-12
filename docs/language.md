# Language guide

`ad` evaluates math notation with exact arithmetic, immutable bindings and
first-class functions. This guide covers supported features. See the
[grammar](grammar.md) for precise syntax.

## Running programs

Run `adhoc` for the REPL or `adhoc run script.ad` for a script. Both use the same
grammar. Statements end at `;` or a newline; a line ending mid-expression
continues onto the next line. See [demos](../demos/) for complete programs.

| REPL input or output | Meaning |
|---|---|
| `> ` | Ready for a statement |
| `... ` | Incomplete input: continue an open string, group or expression |
| `< ` | Output |
| Blank line during continuation | Cancel pending input |
| Ctrl-D | Exit |

Errors point to the source span:

```text
< ERROR! division by zero
    1/0
    ^~~
```

| Setting | Default | Purpose |
|---|---|---|
| `$ADHOC_HISTORY` | `~/.adhoc_history` | Persistent REPL history |
| `$ADHOC_SYMBOLIC_TIMEOUT` | `5` seconds | [Symbolic rewrite](symbolic.md) timeout; `0` disables it |

## Graph sampling

`\graph(f, x=a..b)` samples a callable; `\graph(x^2, x=a..b)` binds `x`
locally in an expression. Both return immutable graph data with gaps and a
completion status. Several targets, such as `\graph(\sin, \cos, x=0..2π)`, return
an immutable bundle. `\tol` and `\maxpoints` control detail and cost per curve.
`\plot` draws several graphs or styled `\series` values on shared axes, with
line, scatter, step, bar and histogram types. See [plotting](plotting.md).
See [graph sampling](graph-sampling.md) for examples and limits.

## Physical quantities

[Units](units.md) attach dimensions to numeric values. `2\metre +
30\centimetre` is exactly `23/10*\metre`; `\convert` selects a display unit
and `\magnitude` explicitly extracts a number. Long unit commands leave
variables such as `m` and `s` available.

## Names and notation

A bare identifier is one ASCII or Unicode letter, optionally subscripted:
`x`, `x₁`, `xᵢ`. ASCII subscripts such as `x_1` also work. Longer names use a
backslash: `\fact`, `\bar`, `\my_var`. Juxtaposition multiplies: `ab` means
`a * b`, and `2x` means `2 * x`.

Names follow LaTeX spellings where available. `ad` supports math notation;
it has no TeX layout or document commands. See [notation](notation.md) for
superscripts, radicals, factorials, comparisons and their ASCII spellings.

```text
\bar = 100
\foo = 200
\foobar = \foo\bar
```

Aliases give one name several spellings. `Σ` and `\sum` refer to the same name.
`\alias \sum, σ` adds a session spelling; `\dual \alpha, α = 3.14` defines a
name and its alias together. Declare aliases before use, at top level.
Diagnostics and fresh binding echoes retain the spelling you write.[^names]

## Bindings and scope

`x = 1` binds a fresh name. Repeating `x = 1` compares with its existing value
and prints `true` or `false`. Bindings are immutable. `\let x = 1` requires a
fresh name; `\let f(x) = body` is the top-level fresh-only function form.
See [assignment semantics](grammar.md#assignment-semantics).

The prelude supplies protected constants and functions, including `π`/`\pi`,
`e`, `i`/`\i`, `\true`, `\false`, `\inf` and `\nan`. Prelude names cannot be
rebound or shadowed, except `i`, which also serves as a parameter or loop name.
Unicode and ASCII aliases share protection and identity.

## Numbers and display

Arithmetic supports `+ - * / ^`, unary minus, parentheses and implicit
multiplication. Exact values stay exact; float operands select inexact arithmetic.

| Kind | Example | Result or behavior |
|---|---|---|
| Integer and rational | `1/3 + 1/3 + 1/3` | Exactly `1` |
| Decimal | `0.1 + 0.2` | Exactly `3/10` |
| Float spelling | `1.`, `5e-1` | Explicitly inexact |
| Symbolic closed form | `√2 * √2` | Exactly `2` |
| Algebraic | `2^(1/3)` | Exact; displays `1.25992104989487...` |
| Recursive Real Arithmetic (RRA) | `π + 1` | Exact; displays `4.14159265358979...` |
| Exact complex | `(2+3i)(2-3i)` | Exactly `13` |
| Complex float | `1. + i` | `1.0+1.0i` |

Negative bases use the real odd-root branch for exact odd-denominator exponents:
`(-8)^(1/3)` is `-2`. Other fractional powers use the complex principal value:
`(-2)^(1/2)` is `√2·i`. Complex values are not ordered.

`\complex(re, im)` builds a complex value; `\re` and `\im` project its components.
`\sqrt(-2)`, `\ln(-1)` and `\sin(1+i)` stay exact. See
[numerics](numerics.md) for the numeric tiers and [standard library](stdlib.md)
for rounding, number theory, elementary and special functions.

Rationals print as fractions: `1/2` displays `1/2`. Symbolic and algebraic values
print 15 significant digits followed by an ellipsis. RRA display uses the session
precision: `\prec(5)` shows `π + 1` as `4.1416...`. `\prec` accepts an integer
from 1 to 1000 and returns it. The ellipsis marks approximate displayed digits;
the stored value remains exact.[^display]

`\isnan`, `\isinf` and `\isfinite` inspect numeric values. Exact values are finite;
non-numeric arguments produce typed errors.

`\exact(v)` tests a numeric scalar's stored exactness: `\exact(π+1)` is `true`,
while `\exact(1.)` is `false`. `\tier(v)` returns its
[numeric tier string](numerics.md#numeric-introspection), such as `"rational"`
for `0.5`. Both reject quantities; extract their magnitude explicitly.

## Functions and application

Define functions with `f(x) = x^2` or `\fact(n) = body`. Functions are first-class,
support recursion, and accept positional parameters. Every call has local
parameters and bindings; reads fall through to enclosing scopes. A nested
function definition binds locally and returns its callable when it ends the body.

| Form | Meaning |
|---|---|
| `f(x)` | Apply a callable |
| `x(y+1)` with numeric `x` | Multiply `x * (y+1)` |
| `2(x+1)` | Implicit multiplication |
| `f()` | Zero-argument call |
| `\fn(x) x + 1`, `\λ(x) x + 1` | Anonymous function |
| `x ↦ x^2`, `x -> x^2`, `x \mapsto x^2` | Arrow lambda |
| `(x, y) ↦ x + y` | Several lambda parameters |

Lambdas are eager, have fixed arity and capture their defining scope. Their bodies
extend greedily unless bounded by parentheses. A parenthesized lambda can be
applied directly: `(\fn(x) x)(5)` returns `5`.

Parenthesized statement groups give functions, lambdas and conditional branches
multi-line bodies. A group uses the current scope and returns its last statement.
At top level, its statements each produce their own output.

```text
f(x) = (
y = x^2
y + 1
)
f(3)
```

See [functions](grammar.md#functions-and-conditionals),
[groups](grammar.md#groups-parenthesized-statement-sequences) and
[application](grammar.md#application-dynamic-name-headed-parens).

## Booleans and conditionals

Comparisons return booleans. Arithmetic rejects booleans, and conditions require
them: `0 ? 1 : 2` is a typed error. The ternary `c ? a : b` evaluates only the
selected branch, associates right and has the loosest expression precedence.
A parenthesized group supplies a branch with several statements.

| Form | Purpose |
|---|---|
| `(x^2=9) ? 10 : 20` | Equality condition; compare values without binding |
| `∧ ∨ ¬ → ↔` | Boolean logic, with short-circuit evaluation |
| `\and \or \not \implies \iff` | ASCII logic spellings |
| `∀(x∈s) body`, `∃(x∈s) body` | Quantification over ranges or collections; `x=s` also works |
| `{x < 0: -x; x}` | Piecewise expression |

See [logic](notation.md#logic) and [conditionals](grammar.md#conditionals-the-ternary).

`a ≡ b (mod n)` compares exact integers modulo a nonzero integer.
`\congruent(a,b,n)` is the callable form; see [integer congruence](congruence.md).

Equality has comparison precedence and does not chain. `(x=3)` compares an
existing value; `(x=3;)` binds or checks in a statement group. At statement
start, `x=3` remains a binding/check and `f(x)=body` remains a definition.
`p=x=3` binds a boolean. In calls, `g(x=3)` passes a named value and
`g((x=3))` passes a positional boolean. See
[equality expressions](grammar.md#equality-expressions) and the
[equality demo](../demos/equality.ad).

## Collections and higher-order functions

| Collection | Example | Operations |
|---|---|---|
| Tensor | `[1, 2; 3, 4]` | Uniform numeric entries; 1-based indexing, transpose, scalar broadcast and elementwise arithmetic |
| Array | `⟨1, [1, 2], "a"⟩` | Ordered values of any kind; ragged nesting, indexing and length |
| Set | `{3, 1, 3, 2}` | Deduplication; equality ignores order; `∪ ∩ ∖ ∈ ⊆` |
| [Symbolic solution set](solution-sets.md) | `\solve(\expr(\sin(x)))` | Non-enumerating; numeric membership, display and TeX |
| Range | `1..10`, `1,3..10`, `1..` | Lazy progression; inclusive endpoint when reached; inferred step or infinite extent |

Tensors nest to higher orders. `m[2, 1]` indexes a matrix; `m'` transposes it.
`@`/`\contract` contracts, `×` crosses 3-vectors, and `⊗` forms a tensor product.
The prelude provides `\len`, `\shape`, `\transpose`, `\det`, `\inv` and `\linsolve`.

Tensors and arrays support [range slicing](slicing.md): `v[2..3]`, `a[2..]`,
and `m[..,2]`. Integer selectors remove tensor axes; ranges retain them.

Arrays also use `#[...]` or `\arr(...)`. They support chained indexing (`a[i][j]`)
and have no elementwise algebra. Sets accept any values and support
[set-builders](grammar.md#set-builder), such as `{x ∈ 1..10 | x^2 < 50}`.

`(f ∘ g)(2)` composes functions. `f(10, ·)` fixes an argument; `⋅` and `_` are
also placeholders. Operator sections `(+ 1)` and `(2 ^)` fix one operand.
Declared custom operators support `(⊕ 2)` and `(2 ⊕)` too; see
[custom operator sections](operators.md#sections).
`\map`, `\filter`, `\fold` and `\scan` work over ranges and collections,
preserving collection kind where applicable. See
[higher-order functions](grammar.md#higher-order-functions).

## Folds, limits and calculus

| Form | Behavior |
|---|---|
| `\sum(i=1..10) i^2` | Exact finite sum: `385`; `Σ` is an alias |
| `\prod(j=1..5) j` | Exact finite product: `120`; `Π` is an alias |
| `\sum(i=1..) 1/i^2` | Approximate limit of partial sums |
| `\lim(x=0) x/x` | Numeric limit: `1.0`; never evaluates at the anchor |
| `\diff(x=a) body`, `∂(x=a) body` | Derivative |
| `\int(x=a..b) body`, `∫(x=a..b) body` | Integral |
| `∫(x=-\inf..b) body`, `∫(x=-\inf..\inf) body` | Lower-infinite and whole-line integrals |
| `f'`, `f''` | Derivative functions |
| `f⁻¹(y)` | Scalar inverse; exact or numeric |
| `f⁻¹(y, \all=\true)` | [All preimages](calculus.md#all-preimages); complex domain by default |

Binders keep their variable local; other reads use the enclosing scope. Folds
also iterate collections, including a tensor's outer slices. Infinite folds use
float arithmetic, tolerance checks and an iteration cap; infinite sums may stop
on a confirmed tail estimate. Failure to converge is a typed error.

Limits probe shrinking steps on both sides. Disagreeing sides report
`limit does not exist`. Complex bodies and anchors work; complex anchors use
eight rays at golden-angle spacing. See [convergence](numerics.md#convergence)
and [calculus](calculus.md) for methods and limitations.

Explicit infinite endpoints create reusable [interval bounds](intervals.md).
`r = -\inf..\inf` can be passed to `∫(x=r) body`; `x ∈ r` tests finite real
membership. Whole-line integration requires both tails to converge independently.

## Quotes and symbolic operations

| Form | Result |
|---|---|
| `q = \expr(x^2 - 4)` or ``q = `(x^2 - 4)`` | Store syntax without evaluating it |
| `\eval(q, x=3)` | Evaluate the quote: `5` |
| `\body(f)` | Reflect a user function or lambda body |
| `\reduce(\expr((\fn(x) x + 1)(2)))` | Beta-reduce to `\expr((2 + 1))` |
| `\solve(\expr(x^2 - 4))` | Solve symbolically: `{-2, 2}` |
| `\solve(\expr(x^2 = 4))` | Solve an equation quote: `{-2, 2}` |
| `\solve(\expr(x^2+1), \domain="real")` | Select real solutions: `{}` |
| `\eval(\expr(x^2 = 4), x=2)` | Compare both sides without binding: `true` |
| `\simplify(\expr(x+x = y+y))` | Rewrite both sides: `\expr(((2 * x) = (2 * y)))` |
| ``\solve(⟨`(x+y=3), `(x-y=1)⟩, ⟨`(x), `(y)⟩)`` | Solve a system: `{⟨2, 1⟩}` |
| `\tex(q)` | Return LaTeX text |

Evaluation bindings use the caller's scope and remain local; other names resolve
where `\eval` runs. Errors retain the quoted source span. Multi-statement bodies
print as `\expr((...))` and return their last statement.

Reduction leaves arithmetic unevaluated, named functions unexpanded and free
names free. It rejects statement quotes. [Symbolic rewriting](symbolic.md)
provides `\simplify`, `\expand`, `\factor`, `\solve`, `\deriv` and `\grad` for
quotes and functions. See [symbolic calculus arrays](symbolic-calculus.md) for `\jacobian`, `\hessian`,
recursive `\eval` and explicit `\tensor` conversion.
See [LaTeX output](tex.md) for rendering.

## Strings, imports and Python

Strings bind and concatenate with `+`: `"data" + ".csv"`. Other arithmetic
operators reject them. `--` starts a line comment; a bare string statement serves
as a note and produces no output.

| Form | Purpose |
|---|---|
| `\import("lib")` | Import top-level names from `lib.ad` |
| `\import("lib": f, \fact)` | Select ad module members |
| `\pyimport("math": \hypot, \tau)` | Select Python module members |
| `\py("math.sqrt")(2)` | Call a Python function: `1.4142135623730951` |
| `\py("int")("ff", \base=16)` | Pass Python keyword arguments: `255` |

Imports are silent statements. Each ad file evaluates once per session in its
own root environment; imported functions retain that environment as their
closure. Resolution searches the importing file's directory, then the working
directory. Cycles are typed errors. Python imports require selected members;
there are no module values or dotted attribute access.

`\py` resolves dotted callable paths with the same power as Python itself.
Strings can compose paths: `\py(n + ".sqrt")`. Python keyword arguments use
ordinary single-letter or backslash names; user functions accept positional
arguments only. Lists, sets and NumPy arrays convert to arrays, sets and tensors;
ad collections convert to Python lists or frozensets. See
[imports](grammar.md#modules-and-imports) and the
[conversion matrix](numerics.md#the-python-boundary-conversion-matrix).

## Custom operators

`\infix(11) \blend, ⊕(a,b) = a+b` declares a function as an infix operator with
an optional glyph or punctuation spelling. For example,
`\infix(11) \blend, <+>(a,b) = a+b` gives `2<+>3` infix syntax. Declarations
persist in the REPL and stay local to each script or module. See [custom operators](operators.md) for precedence, sections and examples.

## Limitations

- Graphing covers sampled real curves and file/window rendering; see
  [sampling limitations](graph-sampling.md#limitations) and
  [plotting limitations](plotting.md#limitations).
- Set construction and membership compare elements pairwise; construction is
  quadratic in set size: [#4](https://github.com/takeiteasy/adhoc/issues/4).
- Numeric derivatives use [order-dependent tolerances and resource budgets](calculus.md#derivatives).
  Function inversion returns one branch; see
  [calculus limitations](calculus.md#limitations).
- Tensor `/` is elementwise. Use `\inv` or `\linsolve` for matrix division.
- Exact irrational values display approximate digits; see
  [display](numerics.md#display). Decimal literals are exact; use `1.` or `5e-1`
  to request floats.
- Caret columns count characters rather than terminal display width. Full-width
  or combining characters can offset a caret; ordinary letters such as `π` work.

[^names]: The lexer accepts backslash names without a name table. Meaning comes
    from parser special forms, the session alias map, custom operator declarations
    and prelude bindings. Other names fail at evaluation when unbound. See
    [name aliases](grammar.md#name-aliases).

[^display]: RRA display compares successive approximations. If they do not agree
    at the requested precision, it prints their longest agreed prefix. Complex
    values use the same policy for each component.
