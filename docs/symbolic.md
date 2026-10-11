# Symbolic rewriting

`\simplify`, `\expand`, `\factor`, `\solve`, `\deriv` and `\grad` rewrite an
expression quote or a user function using SymPy. Results are expression quotes,
finite or symbolic solution sets, or arrays of derivative quotes. Free names remain symbols.

| Function | Result |
|---|---|
| `\simplify(e)` | Simplified expression quote |
| `\expand(e)` | Quote with products and powers expanded |
| `\factor(e)` | Factored quote; numeric arguments use [prime factoring](stdlib.md#factoring) |
| `\solve(e)` | Complex solution set for an equation quote, or for `e = 0` |
| `\solve(e, \domain="real")` | Real solution set |
| `\solve(⟨e₁, e₂⟩, ⟨\expr(x), \expr(y)⟩)` | Set of solution arrays for simultaneous equations |
| `\deriv(e)` | Derivative quote; several free names give a gradient |
| `\grad(e)` | Array of first partial-derivative quotes |

```text
\simplify(\expr((x^2 - 1)/(x - 1)))   ->  = \expr((x + 1))
\expand(\expr((x + 1)^2))            ->  = \expr((((x ^ 2) + (2 * x)) + 1))
\factor(\expr(x^2 - 1))              ->  = \expr(((x + 1) * (x - 1)))
\solve(\expr(x^2 - 4))               ->  = {-2, 2}
\solve(\expr(x^2 = 4))               ->  = {-2, 2}
\solve(\expr(x^2 + 1))               ->  = {-i, i}
\deriv(\expr(x^3))                   ->  = \expr((3 * (x ^ 2)))
```

## Inputs

| Input | Names used as symbols | Other names |
|---|---|---|
| Expression quote, `\expr(...)` | Free names | `\pi`, `e`, `i` and `\inf` retain their constant meaning |
| User function or lambda with one expression as its body | Parameters | Numeric values from the defining scope |

For `a = 3` and `f(x) = a x + x`, `\simplify(f)` returns `\expr((4 * x))`.
A parameter named `i` shadows the imaginary unit; other prelude constants remain
protected.

| Supported syntax | Examples |
|---|---|
| Numbers and names | `2`, `1/3`, `x` |
| Arithmetic and unary minus | `+ - * / ^`, `-x` |
| Elementary functions | `\sin`, `\sqrt`, `\root`, `\ln`, `\log`, `\abs` |
| Calls to other names | Undefined symbolic functions: `g(x) + g(x)` simplifies to `2 g(x)` |
| Equation quotes, for `\simplify`, `\expand`, `\factor` and `\solve` | `\expr(x^2 = 4)` |

Sets, other comparisons, folds, lambda syntax and statement quotes produce an error
naming the unsupported construct. A lambda passed as a function input is supported;
a lambda expression inside a quote is not.

## Selecting names and orders

Use a quoted name to select an unknown or differentiation variable. Both
`\expr(y)` and backtick quotes work.

| Form | Meaning |
|---|---|
| `\solve(e, \expr(y))` | Solve for `y` |
| `\deriv(e, \expr(y))` | Differentiate with respect to `y` |
| `\deriv(e, \expr(y), n)` | Positive integer derivative order `n` |
| `\deriv(e, ⟨\expr(x), \expr(y)⟩)` | Mixed partial: differentiate by each listed name in turn |
| `\grad(e, ⟨\expr(x), \expr(y)⟩)` | First partial for each listed name |

An order argument requires a single variable. Repeat names in a mixed-partial
list for higher orders.

```text
\solve(\expr(a x - b), `(x))         ->  = {\expr((b / a))}
\deriv(\expr(a x^2), `(a))           ->  = \expr((x ^ 2))
\deriv(\expr(x^3 y), ⟨`(x), `(x), `(y)⟩) ->  = \expr((6 * x))
```

## Partial derivatives

With several candidate names and no selected variable, `\deriv` and `\grad`
return one partial quote per name. Quotes use free-name order; functions use
parameter order.

```text
\deriv(\expr(x^2 y))     ->  = ⟨\expr(((2 * x) * y)), \expr((x ^ 2))⟩
f(x, y) = x y^2
\grad(f)                 ->  = ⟨\expr((y ^ 2)), \expr(((2 * x) * y))⟩
```

Gradients are arrays because tensors hold numbers only. They support indexing
and mapping, with no vector algebra; see [limitations](#limitations).
Numeric derivatives at a point use `f'` or `\diff`; see [calculus](calculus.md).

## Solving

`\solve` infers the unknown when there is one free name or one function parameter.
With several names, select one explicitly. The default domain is complex; pass
`\domain="real"` to select real solutions. The keyword applies to scalar
solves and systems. It returns a set:

| Solution | Representation |
|---|---|
| Exact number or closed form | Numeric value, such as `2`, `i` or exact `√2` |
| Depends on other names | Expression quote |
| No solutions | `{}` |
| Infinite scalar family or domain-restricted scalar result | Non-enumerating [symbolic set](solution-sets.md) |

```text
f(x) = x^2 - 9
\solve(f)              ->  = {-3, 3}
```

```text
\solve(\expr(x^2 + 1), \domain="real") -> = {}
\solve(\expr(e^x = 5), \domain="real") -> = {1.6094379124341...}
s = \solve(\expr(\sin(x) = 0))
\pi ∈ s                              -> = true
```

Scalar infinite families remain symbolic rather than being enumerated. An identity
such as `\solve(\expr(x=x), \expr(x))` returns the whole selected domain.
Unresolved equations produce closed-form errors; see
[solution-set limitations](solution-sets.md#limitations).

## Equation quotes

Write `lhs = rhs` inside `\expr(...)` or a backtick quote. Both sides stay
unevaluated until passed to a symbolic operation or `\eval`.

```text
q = \expr(x^2 = 4)
\solve(q)              ->  = {-2, 2}
\eval(q, x=2)          ->  = true
\eval(q, x=3)          ->  = false
\tex(q)               ->  = "x^{2} = 4"
\solve(`(a x = b), `(x)) -> = {\expr((b / a))}
```

`\eval` evaluates both sides once and compares their values without binding
names. Equation quotes use the same local bindings and source diagnostics as
other quotes. `\solve` treats an equation as `lhs - rhs = 0`.

`\simplify`, `\expand` and `\factor` rewrite each side separately and return
an equation quote preserving `=`, including when both sides are constants or
identical expressions.

```text
\expand(\expr((x+1)^2 = y)) -> = \expr(((((x ^ 2) + (2 * x)) + 1) = y))
\simplify(\expr(x+x = y+y)) -> = \expr(((2 * x) = (2 * y)))
\factor(\expr(x^2-1 = y))   -> = \expr((((x + 1) * (x - 1)) = y))
```

The returned quotes support display round trips, `\tex` and boolean evaluation
with `\eval`. `\deriv` and `\grad` reject equation quotes.

An equation occupies the whole quote body; chained equations are rejected.
Statement-sequence quotes such as `\expr((x=1; x+1))` contain assignments.
Outside quotes, `=` retains its bind-or-check and function-definition meanings;
in expression positions it compares values. See
[equality expressions](grammar.md#equality-expressions). The outer `=` of an
equation quote separates full expressions; nested equality uses ordinary
comparison precedence.

## Systems of equations

Pass an array of expression quotes or single-expression functions and an ordered
array of quoted unknowns. Equation quotes, plain expression quotes and functions
can mix in the input array. Plain expressions and function bodies equal zero.
Other free names remain symbolic parameters, and functions use numeric values
from their defining scope.

```text
\solve(⟨`(x+y=3), `(x-y=1)⟩, ⟨`(x), `(y)⟩) -> = {⟨2, 1⟩}
\solve(⟨`(x^2=1), `(y=x)⟩, ⟨`(x), `(y)⟩)   -> = {⟨-1, -1⟩, ⟨1, 1⟩}
\solve(⟨`(x=a), `(y=2*x)⟩, ⟨`(x), `(y)⟩)   -> = {⟨\expr(a), \expr((2 * a))⟩}
```

Each solution array follows the unknown order. Reversing ``⟨`(x), `(y)⟩`` to
``⟨`(y), `(x)⟩`` reverses its coordinates. Numeric coordinates retain their exact
value; parameter-dependent coordinates are quotes that support `\eval`.

| Call | Result shape |
|---|---|
| `\solve(e, \expr(x))` | Set of scalar solutions |
| `\solve(e, ⟨\expr(x)⟩)` | Set of one-coordinate arrays |
| `\solve(e, ⟨\expr(x), \expr(y)⟩)` | Set of two-coordinate arrays |
| `\solve(⟨e₁, e₂⟩, ⟨\expr(x)⟩)` | Common scalar roots wrapped in one-coordinate arrays |

An equation array requires an unknown array. Both arrays must be nonempty, and
unknowns must be distinct quoted names. A single quote or function also accepts
an unknown array. Equation and unknown counts need not match: inconsistent
systems return `{}`, while redundant equations can still give isolated solutions.

Systems return only finite, isolated solution sets. An unconstrained unknown or a
family such as `x + y = 1` produces an infinite-solutions error. Unresolved
solutions produce a closed-form error; see [limitations](#limitations).[^systems]

With `\domain="real"`, a solution row is returned only when every coordinate is
provably real. Rows containing a provably non-real coordinate are discarded. An
undecidable coordinate, such as a free parameter `a`, produces a typed realness
error. Parameters do not acquire real assumptions automatically.

```text
\solve(⟨`(x^2+1), `(y=x)⟩, ⟨`(x), `(y)⟩, \domain="real") -> = {}
```

## Inverses

For supported user functions, `f⁻¹(y)` solves `f(x) = y` once per function and
substitutes the argument into that exact form. Exact complex arguments are
supported. See [inverse behavior](calculus.md#inverses) for branch selection and
numeric fallback.

## Time limit

Rewrites stop after 5 seconds by default. `ADHOC_SYMBOLIC_TIMEOUT` sets the limit
in seconds; `0` disables it. A timeout reports `took longer than 5s` at the default
setting. Both sides of an equation share one time limit. `f⁻¹` and `f'` treat a
timeout as no exact form and use their numeric path.[^worker]

## Dimension annotations

Unit-aware `\simplify`, `\expand`, `\factor`, `\deriv`, `\grad` and
`\solve` accept local `\dimensions` annotations. Every unresolved free name
needs a quoted-name/unit pair; use `1` for a dimensionless variable.

```text
\solve(`(x=2\metre), `(x), \dimensions=⟨⟨`(x), \metre⟩⟩)
    -> = {2*\metre}
\eval(\deriv(`(x^2), `(x), \dimensions=⟨⟨`(x), \metre⟩⟩), x=3\metre)
    -> = 6*\metre
```

Dimension checks occur before simplification. Equations require matching sides;
functions such as sine and logarithm require dimensionless arguments. The
backend receives canonical magnitudes; results restore unit factors.

Returned expression values retain annotations. `\eval` checks supplied or
visible bindings against them. Duplicate annotation names and conflicting
dimensions are errors. Annotations do not change the session's bindings.
Finite solutions and symbolic solution families carry the unknown's dimension;
membership in a family with different dimensions is false.

## Limitations

| Limit | Ticket |
|---|---|
| Infinite system families are errors | [#43](https://github.com/takeiteasy/adhoc/issues/43) |
| Conditional real solutions are unsupported; undecidable system realness is an error | [#44](https://github.com/takeiteasy/adhoc/issues/44) |
| No time limit on Windows | [#19](https://github.com/takeiteasy/adhoc/issues/19) |
| Gradients are arrays of quotes without vector algebra | [#18](https://github.com/takeiteasy/adhoc/issues/18) |

[^worker]: Each rewrite runs in a forked child that is killed at the limit.
    This also enforces the timeout off the main thread. Forking adds per-call
    overhead; the child's SymPy caches are discarded. On systems without `fork`,
    such as Windows, rewriting runs without a time limit.

[^systems]: Linear systems use SymPy's `linsolve`; other systems use
    `nonlinsolve`. Candidate solutions are substituted into every input expression
    and their residuals simplified under the same time limit. A candidate with an
    undecidable residual is rejected with a closed-form error. Parameter-dependent
    answers follow SymPy's generic parameter conventions, without separate branches
    for exceptional parameter values.
