# Symbolic rewriting

`\simplify`, `\expand`, `\factor`, `\solve` and `\deriv` rewrite an expression quote or a user function and
answer with an expression quote (or, for `\solve`, a set of solutions). They run on sympy;
free names stay symbols.

| Form | Result |
|---|---|
| `\simplify(e)` | the simplified expression |
| `\expand(e)` | products and powers multiplied out |
| `\factor(e)` | the factored expression (`\factor(12)` on a number is prime factors, docs/stdlib.md) |
| `\solve(e)` | the set of `x` with `e = 0`, over the complex numbers |
| `\solve(e, `(y))` | the same, solving for `y` |
| `\deriv(e)` | the exact derivative with respect to the one free name |
| `\deriv(e, `(y))` | the same, with respect to `y` |
| `\deriv(e, `(y), n)` | the `n`th derivative, `n` a positive integer |

```
\simplify(\expr((x^2 - 1)/(x - 1)))   ->  = \expr((x + 1))
\expand(\expr((x + 1)^2))            ->  = \expr((((x ^ 2) + (2 * x)) + 1))
\factor(\expr(x^2 - 1))              ->  = \expr(((x + 1) * (x - 1)))
\solve(\expr(x^2 - 4))               ->  = {-2, 2}
\solve(\expr(x^2 + 1))               ->  = {-i, i}
\solve(\expr(a x - b), `(x))         ->  = {\expr((b / a))}
f(x) = x^2 - 9
\solve(f)                            ->  = {-3, 3}
\deriv(\expr(x^3))                    ->  = \expr((3 * (x ^ 2)))
\deriv(\expr(a x^2), `(a))           ->  = \expr((x ^ 2))
```

`\deriv` names its unknown the way `\solve` does. Numeric derivatives at a point are `f'` and
`\diff` (docs/calculus.md); `f'` uses the exact derivative when the body bridges.

## Inputs

- An **expression quote** (`\expr(...)`). Every name is free, except `\pi`, `e`, `i` and `\inf`,
  which are the constants.
- A **user function or lambda** with a single-expression body. Its parameters are the symbols;
  other names take their numeric values from where the function was defined
  (`a = 3; f(x) = a x + x` simplifies to `4 x`). A parameter named `e` or `i` shadows the
  constant.

Supported: numbers, names, `+ - * / ^`, unary minus, `\sin` and the other elementary
functions, `\sqrt`, `\root`, `\ln`, `\log`, `\abs`, and calls to other names (kept as
undefined functions: `g(x) + g(x)` simplifies to `2 g(x)`). Anything else, such as sets,
comparisons, folds, lambdas or statement quotes, is an error naming the construct.

## Solving

`\solve` finds the unknown itself when there is exactly one free name (or, for a function, one
parameter). With several, name it with a quote: `\solve(e, `(x))`. The result is a set:

| Solution | Shown as |
|---|---|
| exact or closed-form | a value (`2`, `i`, `1.41421356237309...`) |
| depends on other names | an expression quote |
| none | `{}` |

An equation with infinitely many solutions (`\sin(x) = 0`) or none sympy can express is an
error.

## Inverses

`f⁻¹(y)` on a user function solves `f(x) = y` this way once per function, then substitutes
`y`, so the result is exact and `y` may be complex (docs/calculus.md, `## Inverses`).

## Time limit

Each rewrite stops after 5 seconds with `took longer than 5s`. `ADHOC_SYMBOLIC_TIMEOUT` sets
the seconds; `0` removes the limit. `f⁻¹` and `f'` treat a timeout as "no exact form" and use
their numeric path.[^timer]

## Limitations

| Limit | Ticket |
|---|---|
| One unknown; no systems | [#112](https://todo.sr.ht/~takeiteasy/adhoc/112) |
| `\solve(e)` solves `e = 0`; `lhs = rhs` is not read as an equation | [#113](https://todo.sr.ht/~takeiteasy/adhoc/113) |
| Infinite solution families are an error; no real-domain option | [#114](https://todo.sr.ht/~takeiteasy/adhoc/114) |
| The time limit needs SIGALRM on the main thread | [#119](https://todo.sr.ht/~takeiteasy/adhoc/119) |
| Numeric third and higher derivatives (float points, non-symbolic bodies) are an error | [#102](https://todo.sr.ht/~takeiteasy/adhoc/102) |

[^timer]: A `setitimer(ITIMER_REAL)` interrupt. Off the main thread, without SIGALRM, or while
    another interval timer runs, the rewrite is unlimited.
