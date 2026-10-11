# LaTeX output

`\tex(e)` returns LaTeX source for an expression quote, a function, or a value, as an
ordinary string.

```
\tex(\expr(x^2/2 + 1))          ->  = "\\frac{x^{2}}{2} + 1"
\tex(\expr(∫(x=0..) e^(-x)))    ->  = "\\int_{0}^{\\infty} e^{-x} \\, dx"
\tex(1/2)                       ->  = "\\frac{1}{2}"
\tex([1, 2; 3, 4])              ->  = "\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}"
```

The REPL shows the string escaped; the string itself holds single backslashes, so it
composes (`"$" + \tex(e) + "$"`) and passes to `\py` for writing to a file.

## Supported inputs

| Input | Output |
|---|---|
| Quote | the expression, with parentheses only where precedence needs them |
| User function or lambda | `f(x) = body` or `x \mapsto body` |
| Number | `\frac{a}{b}` for a rational; `sympy.latex` for symbolic and algebraic values; digits followed by `\ldots` for the rest |
| Tensor | `pmatrix` |
| Array | `\langle … \rangle` |
| [Symbolic solution set](solution-sets.md) | Set-builders, domain symbols and unions/intersections |
| Set or range | `\{ … \}`; ranges use an ellipsis |
| [Interval](intervals.md) | Interval notation; infinite endpoints are open, finite endpoints closed; endpoint order is preserved |
| Boolean, string | `\text{…}` |

## Syntax rendering

| Syntax | LaTeX |
|---|---|
| `a/b`, `a^b`, `√x` | `\frac{a}{b}`, `a^{b}`, `\sqrt{x}` |
| Equation quote `\expr(x^2=4)` | `x^{2} = 4` |
| `\|x\|`, `‖x‖`, `⌊x⌋` | `\left\| x \right\|`, `\lVert`, `\lfloor` |
| `Σ`, `Π`, `\lim` | `\sum_{i=1}^{n}`, `\prod`, `\lim_{x \to a}` |
| `∫`, `∂` | `\int_a^b … \, dx`, `\left.\frac{d}{dx}(…)\right\|_{x=a}` |
| ternary, piecewise | `cases` |
| set-builder | `\{ x \in S \mid p \}` |
| `↦` | `\mapsto` |
| `f²(y)`, `\sin²(y)` | `f^{2}\left(y\right)`, `\sin^{2}\left(y\right)` |
| Numeric `x²(3)` with `x=2` | `x^{2} \cdot 3` |
| `f⁻¹(y)`, `\sin⁻¹(y)` | `f^{-1}\left(y\right)`, `\sin^{-1}\left(y\right)` |
| `Aᵀ`, `A'` | `A^{\mathsf{T}}`, `A'` |

## Function powers

A quote uses the scope of the `\tex` call to distinguish numeric heads from
function heads. A function value uses its defining scope. Parameters and local
binders mask outer bindings; unbound names and unresolved composite heads use
function notation. Rendering does not execute heads, arguments or exponents.

```text
x = 2
\tex(\expr(x²(3)))     -> = "x^{2} \\cdot 3"
\tex(\expr(\sin²(x))) -> = "\\sin^{2}\\left(x\\right)"
```

Explicit powers such as `\sin(x)^2` retain ordinary call-power notation.

## Names and errors

Names use their LaTeX spelling: Greek letters (`α` is `\alpha`), subscripts (`x₁` is
`x_{1}`), known functions (`\sin`, `\asin` is `\arcsin`) and `\operatorname{name}` for the rest.
Built-in functions, Python callables and other values without a LaTeX form
produce typed errors.
