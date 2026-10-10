# Notation

Math glyphs have ASCII spellings and parse to ordinary operators or calls.
Quoted expressions display canonical syntax. See the [grammar](grammar.md)
for parsing rules and the [standard library](stdlib.md) for functions.

## Powers, names and roots

| Glyph | ASCII | Meaning | Level |
|---|---|---|---|
| `x²` `x⁻¹` `2¹⁰` | `x^2` | power[^superscript] | postfix |
| `xⁿ` `xⁿ⁻¹` `x⁽ⁿ⁺¹⁾` | `x^n` `x^(n-1)` | power with a letter or expression exponent | postfix |
| `Aᵀ` | `A'` | transpose | postfix |
| `\sin²(x)` `f²(x)` | `\sin(x)^2` | function power[^funcpow] | postfix |
| `\sin⁻¹(x)` `\cos⁻¹` `\tan⁻¹` | `\asin(x)` `\acos` `\atan` | inverse trig[^funcpow] | postfix |
| `x₁` `a₂₃` `xᵢⱼ` | `x_1` `a_23` `x_ij` | Distinct name[^subscript] | name |
| `n!` | — | factorial[^factorial] | postfix |
| `n‼` | `n!!` | double factorial | postfix |
| `∛x` `∜x` | `\root(x, 3)` `\root(x, 4)` | Cube and fourth root[^root] | prefix, like `√` |

## Comparisons, logic and calculus

| Glyph | ASCII | Meaning | Level |
|---|---|---|---|
| `≤` `≥` | `<=` `>=` | ordering | comparison |
| `≠` | `\neq` | Not equal; uses numeric-tier equality | comparison |
| `≈` | `\approx` | approximately equal[^approx] | comparison |
| `∉` | `\notin` | not a member | comparison |
| `⊂` `⊇` `⊃` | `\subset` `\supseteq` `\supset` | proper subset, superset, proper superset | comparison |
| `∅` | `\emptyset` | the empty set (prelude constant) | name |
| `∧` `∨` `→` `↔` | `\and` `\or` `\implies` `\iff` | connectives[^logic] | see [Logic](#logic) |
| `¬` | `\not` | negation | prefix |
| `∀` `∃` | `\forall` `\exists` | quantifiers over a range or collection | special form |
| `r∠θ` | `\angle` `\polar(r, θ)` | polar form: modulus and angle | looser than `+`, tighter than comparison |
| `∫(x=a..b)` `∂(x=a)` | `\int` `\diff` | numeric integral and derivative ([calculus](calculus.md)) | special form |
| `f'` `f''` | — | derivative of a function (exact where symbolic); `'` on a tensor stays the transpose | postfix |
| `x ↦ body` | `x -> body` `x \mapsto body` | lambda; `(x, y) ↦ body` for several parameters | loosest, greedy body |

## Delimiters and products

| Glyph | ASCII | Meaning | Level |
|---|---|---|---|
| `⌊x⌋` `⌈x⌉` | `\floor(x)` `\ceil(x)` | floor and ceiling | atom |
| `\|x\|` | `\abs(x)` | absolute value, complex modulus | atom |
| `‖v‖` `∥v∥` | `\norm(v)` | 2-norm of a vector, Frobenius norm of a matrix | atom |
| `%` | `\mod` | floored modulo | with `*` |
| `×` | `\times` `\cross(a, b)` | cross product of 3-vectors; scalar multiple with a scalar operand | with `*` |
| `⊗` | `\otimes` `\outer(a, b)` | tensor product; scalar multiple with a scalar operand | with `*` |

```
2x²            ->  2 * (x^2)
2^3!           ->  2^(3!) = 64
-3!            ->  -(3!)  = -6
∛-8            ->  = -2
1 ≤ 2 ≠ 3     -- comparisons do not chain: parenthesize
{1} ⊂ {1, 2}   ->  = true
3 ∉ ∅          ->  = true
n = 3; 2ⁿ⁻¹    ->  = 4
f(x) = x + 1
f²(2)          ->  = 9
x_1 = 2; x₁    ->  = 2
3 ∈ 1..5        ->  = true
\sin⁻¹(1/2)    ->  = 0.523598775598299...
```

## Precedence

Superscripts and `!` are postfix trailers: they bind tighter than `^`, juxtaposition,
and unary minus, and chain with `(…)`, `[…]` and `'`.

| Source | Reads as |
|---|---|
| `2x²` | `2 * (x²)` |
| `-x²` | `-(x²)` |
| `2^3²` | `2^(3²)` |
| `3!^2` | `(3!)^2` |
| `√x²` | `√(x²)` |
| `(1+2)!` | `3!` |
| `f(x)²` | `(f(x))²` |
| `\sin²(x)` | `(\sin(x))²` |
| `2ⁿᵏ` | `2^(n·k)` |

## Logic

Connectives take booleans only; a number is never a condition (`1 ∧ \true` is a typed error).
Loosest to tightest: `↔`, `→`, `∨`, `∧`, `¬`, then ranges and comparisons, so
`x > 0 ∧ x < 5 → y ≠ 0` needs no parentheses.

```
1 < 2 ∧ 2 < 3          ->  = true
x = 0; x ≠ 0 ∧ 1/x > 2  ->  = false      -- the right side never runs
\true → \false          ->  = false
¬(1 < 2)               ->  = false
\false → \false → \false  ->  = true       -- → nests to the right
∀(x=1..5) x > 0        ->  = true
∃(x={1, 2}) x > 4      ->  = false
∃(x∈{1, 2}) x > 1      ->  = true         -- `∈` binds like `=`
∀(x=1..3) ∃(y=1..3) x + y > 3  ->  = true
```

`(∧)` and the other connectives are function values that evaluate both operands
(`\fold(∧, ⟨\true, \false⟩)` is `false`). `↔` does not chain: parenthesize one side.

## Membership

`∈` and `∉` take a set, an array, or a range on the right. Array membership uses the
binding rule's equality; range membership asks whether the value is a term of the
progression. The right operand reads a range without parentheses; other comparisons
keep `..` looser, so `3 < 1..5` is `(3 < 1)..5`:

```
2 ∈ ⟨1, 2, 3⟩       ->  = true
5 ∈ 1,3..9           ->  = true
4 ∈ 1,3..9           ->  = false
1000000 ∈ 1..        ->  = true
```

## Operator values

Parentheses turn operators into function values:

| Group | Examples |
|---|---|
| Factorials and roots | `(!)`, `(‼)`, `(∛)`, `(∜)` |
| Comparisons and sets | `(≠)`, `(≈)`, `(∉)`, `(⊂)`, `(⊇)`, `(⊃)` |
| Modulo and polar form | `(%)`, `(∠)` |
| Logic | `(∧)`, `(∨)`, `(→)`, `(↔)`, `(¬)` |

Postfix operators and radicals have no sections. `(∛)` is `\root(·, 3)`.
See [operator values](grammar.md#operator-values) for application rules.

## Limitations

- `|A|` on a square matrix is an error, not the determinant — [#7](https://github.com/takeiteasy/adhoc/issues/7).
- Set-builder separators and absolute-value bars share `|`. Write `{a*|b|}`
  for a product; `{a |b|}` is read as a set-builder:
  #79 (old, not migrated).
- `f⁻¹` gives one branch — [#17](https://github.com/takeiteasy/adhoc/issues/17).
- `\tex` of function powers: `\sin²(x)` and non-callable heads render as a power of the call — [#16](https://github.com/takeiteasy/adhoc/issues/16).

[^superscript]: A run of digits, letters, `⁺ ⁻ ⁽ ⁾` is one exponent, read as its ASCII
    spelling: `x⁻¹⁰` is `x^-10`, `2ⁿᵏ` is `2^(n k)`. Glyphs exist for every letter but `q`
    (plus capitals `ABDEGHIJKLMNOPRUVW`, Greek `αβγδεθφχ`); spell the rest with `^`
    (`x^q`). A run of only `⁺⁻⁽⁾` is a lex
    error, and `1¹ᵉ³` reads `e3` as a float exponent (`1^1000.0`).
[^subscript]: A letter followed by subscript digits `₀…₉` or letters `ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ`
    lexes as one identifier. `x₁` is unrelated to `x`, aliases and parameters accept it, and
    `\`-names take no subscript. It is a name, not indexing: write `x[i]`. `x_1` after a
    letter is the same name and echoes as typed; a bare subscript glyph is a lex error.
    Unicode has no subscript for `b c d f g q w y z` or capitals, so `x_b`, `x_A` and `x_ib`
    are names in their ASCII form (`x_ij` is still `xᵢⱼ`); `\x_b` names the same variable.
[^funcpow]: After a name or a parenthesised head: a lambda, `f ∘ g` or `f⁻¹` (`(x ↦ 2x)⁻¹(6)`,
    `(f⁻¹)(6)`). A callable head gives `f(x)^n`; any other head gives
    `(f^n)(x)`, so `x²(2)` on a number is `18` when `x = 3`. A negative exponent on a
    callable must be exactly `⁻¹`. On `\sin \cos \tan \exp \sinh \cosh \tanh` or
    their inverses, this gives the inverse pair (`\sin⁻¹` is `\asin`, also without a call). Any other
    function gives its numeric inverse ([calculus](calculus.md)), and `\sin⁻²(x)` is an error.
[^logic]: `∧` `∨` and `→` skip their right operand once the left decides (`false ∧ …`,
    `true ∨ …`, `false → …`); a non-boolean operand is a typed error at that operand. `∀` and
    `∃` are special forms like `\sum` ([special forms](grammar.md#special-forms-folds-and-limits)) and use the same
    `(x=domain) body` or `(x∈domain) body` binder.
[^factorial]: An exact non-negative integer up to 100,000 gives the exact product. Any other
    real is `\gamma(x + 1)` (`(1/2)!` is `√π/2`); negative integers and complex values are
    typed errors. `‼` takes exact non-negative integers only. `3!!` is the double factorial `3‼ = 3`, not `(3!)!`. `!=` is a lex error that
    points at `≠`.
[^root]: `∛x` is the call `\root(x, 3)`. `\root(x, n)` takes an exact positive integer `n`
    and evaluates `x^(1/n)` on the numeric seam, so `∛-8` is `-2`.
[^approx]: Numbers only. Floats compare with relative tolerance `1e-9` and absolute `1e-12`
    (Python's `math.isclose`); complex values compare by component. `NaN` is never
    approximately equal to anything.
