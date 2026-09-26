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

## What renders

| Input | Output |
|---|---|
| Quote | the expression, with parentheses only where precedence needs them |
| User function or lambda | `f(x) = body` or `x \mapsto body` |
| Number | `\frac{a}{b}` for a rational; `sympy.latex` for symbolic and algebraic values; digits followed by `\ldots` for the rest |
| Tensor, array, set, range | `pmatrix`, `\langle … \rangle`, `\{ … \}` |
| Boolean, string | `\text{…}` |

| Syntax | LaTeX |
|---|---|
| `a/b`, `a^b`, `√x` | `\frac{a}{b}`, `a^{b}`, `\sqrt{x}` |
| `\|x\|`, `‖x‖`, `⌊x⌋` | `\left\| x \right\|`, `\lVert`, `\lfloor` |
| `Σ`, `Π`, `\lim` | `\sum_{i=1}^{n}`, `\prod`, `\lim_{x \to a}` |
| `∫`, `∂` | `\int_a^b … \, dx`, `\left.\frac{d}{dx}(…)\right\|_{x=a}` |
| ternary, piecewise | `cases` |
| set-builder | `\{ x \in S \mid p \}` |
| `↦` | `\mapsto` |
| `f⁻¹(y)`, `\sin⁻¹(y)` | `f^{-1}\left(y\right)`, `\sin^{-1}\left(y\right)` |
| `Aᵀ`, `A'` | `A^{\mathsf{T}}`, `A'` |

Names map to their LaTeX spelling: Greek letters (`α` is `\alpha`), subscripts (`x₁` is
`x_{1}`), known functions (`\sin`, `\asin` is `\arcsin`) and `\operatorname{name}` for the rest.
A builtin, a Python callable or another value with no LaTeX form is a typed error.
