# Function clauses

Named functions contain ordered clauses. A call runs the first clause whose
parameter patterns match its arguments.

```text
f(0) = 1
f(n) = n*f(n-1)
f(5)                 -> = 120
(f(0) = 1)           -> = true
```

Use newlines between definitions. A semicolon after a function body continues
that body. Parentheses around a call equality make it a comparison; at statement
start, `f(...) = body` declares a clause. See the [runnable demo](../demos/function-clauses.ad).

## Patterns

| Head | Meaning |
|---|---|
| `f(x)` | Bind any argument as `x` |
| `f(0)`, `f(-2)`, `f(+2)` | Match a numeric literal by value |
| `f(0.5)` | Match `1/2`, including equivalent float values |
| `f("yes")` | Match the string `"yes"` |
| `f(\true)`, `f(\false)` | Match a Boolean; numbers do not match these patterns |
| `f(0, x)` | Match the first argument and bind the second |
| `f()` | Match a zero-argument call |

A name binds locally even when the enclosing scope has that name. Binder names
within one head must be distinct after alias resolution; protected names cannot
be binders. `\true` and `\false` are literal patterns. Other constants such as
`\pi` are protected names, not value patterns.

Numeric literals use the ordinary numeric tiers. Literal matching follows value
equality, except that Booleans and numbers remain distinct. Expressions such as
`1/2`, `x+1`, and collection literals are not patterns; use a decimal literal for
a rational value.

## Order and calls

All clauses have the same argument count. Binder names may differ between clauses.
Arguments evaluate once, before matching. Only the selected body runs, in a fresh
local frame; reads fall through to its defining scope. Recursive calls dispatch
through the complete function.

Overlapping and duplicate clauses are accepted. A catch-all head masks every later
clause. A selected body's error propagates; it does not try the next clause. If no
clause matches, the call reports `no matching clause`.

## Additions and scope

Bare definitions add clauses through the original canonical name in its defining
frame, including across REPL submissions. A spelling alias names the same function.
A value alias such as `g = f` sees additions to `f`, but `g(...) = body` cannot extend it.
Partials and compositions also use the live function.

Additions through enclosing scopes, recursion frames, and imported bindings are
errors. Nested functions accept clauses in their own defining call frame.
`\let f(...) = body` creates a fresh function and fails on an existing name.
Explicit `\infix` declarations remain fresh-only and use name parameters.

## Display and consumers

A single clause with name parameters displays as `<fn f(x)>`. Patterned or
multi-clause functions display their arity and clause count, for example
`<fn f/1; 2 clauses>`. `\tex(f)` renders every clause in declaration order.
Statement quotes retain patterned definitions and round-trip through `\eval`.

Numeric consumers, including mapping, graph sampling and numerical calculus,
call ordinary dispatch. A single all-name clause retains its existing reflection
and symbolic support; other functions have the [limitations below](#limitations).[^caches]

## Limitations

| Limit | Ticket |
|---|---|
| Clauses have no guards | [#61](https://github.com/takeiteasy/adhoc/issues/61) |
| Arrays and tensors cannot be destructured in heads | [#62](https://github.com/takeiteasy/adhoc/issues/62) |
| `\body` and symbolic operations reject patterned or multi-clause functions, including nested symbolic calls | [#63](https://github.com/takeiteasy/adhoc/issues/63) |

[^caches]: Derivative and inverse callables invalidate cached symbolic forms after
    additions to their function or a referenced user function. Numerical fallback
    still follows ordered dispatch and its usual domain and convergence checks.
