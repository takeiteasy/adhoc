# Notation

Paper-math glyphs and their ASCII spellings. Every glyph parses to an ordinary operator or
call, so quotes print the canonical form and every glyph has an ASCII spelling.

| Glyph | ASCII | Meaning | Level |
|---|---|---|---|
| `x²` `x⁻¹` `2¹⁰` | `x^2` | power[^superscript] | postfix |
| `xⁿ` `xⁿ⁻¹` `x⁽ⁿ⁺¹⁾` | `x^n` `x^(n-1)` | power with a letter or expression exponent | postfix |
| `Aᵀ` | `A'` | transpose | postfix |
| `\sin²(x)` `f²(x)` | `\sin(x)^2` | function power[^funcpow] | postfix |
| `\sin⁻¹(x)` `\cos⁻¹` `\tan⁻¹` | `\asin(x)` `\acos` `\atan` | inverse trig[^funcpow] | postfix |
| `x₁` `a₂₃` `xᵢⱼ` | `x_1` `a_23` `x_ij` `x_b` `x_A` | a distinct name[^subscript] | name |
| `n!` | — | factorial[^factorial] | postfix |
| `n‼` | `n!!` | double factorial | postfix |
| `∛x` `∜x` | `\root(x, 3)` | cube and fourth root[^root] | prefix, like `√` |
| `≤` `≥` | `<=` `>=` | ordering | comparison |
| `≠` | `\neq` | not equal (negated `=` check) | comparison |
| `≈` | `\approx` | approximately equal[^approx] | comparison |
| `∉` | `\notin` | not a member | comparison |
| `⊂` `⊇` `⊃` | `\subset` `\supseteq` `\supset` | proper subset, superset, proper superset | comparison |
| `∅` | `\emptyset` | the empty set (prelude constant) | name |
| `∧` `∨` `→` `↔` | `\and` `\or` `\implies` `\iff` | connectives[^logic] | see `## Logic` |
| `¬` | `\not` | negation | prefix |
| `∀` `∃` | `\forall` `\exists` | quantifiers over a range or collection | special form |
| `r∠θ` | `\angle` `\polar(r, θ)` | polar form: modulus and angle | above `+`, below comparison |
| `%` | `\mod` | floored modulo | with `*` |

```
2x²            ->  2 * (x^2)
2^3!           ->  2^(3!) = 64
-3!            ->  -(3!)  = -6
∛-8            ->  = -2
1 ≤ 2 ≠ 3     -- comparisons do not chain: parenthesize
{1} ⊂ {1, 2}   ->  = true
3 ∉ ∅          ->  = true
n = 3; 2ⁿ⁻¹    ->  = 4
f(x) = x + 1; f²(2)  ->  = 9
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

`(!)`, `(‼)`, `(∛)`, `(∜)`, `(≠)`, `(≈)`, `(∉)`, `(⊂)`, `(⊇)`, `(⊃)`, `(%)`, `(∠)`, `(∧)`, `(∨)`, `(→)`, `(↔)`, `(¬)` are function values
like the other operators (`docs/grammar.md`, `## Operator values`). Postfix operators and
radicals have no sections. `(∛)` is the partial `\root(·, 3)`.

## Limitations

- `f⁻¹` on a user function is a typed error — [#87](https://todo.sr.ht/~takeiteasy/adhoc/87).

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
[^funcpow]: Only after a name. A callable head gives `f(x)^n`; any other head gives
    `(f^n)(x)`, so `x²(2)` on a number is `18` when `x = 3`. A negative exponent on a
    callable is a typed error unless it is exactly `⁻¹` on `\sin \cos \tan \exp \sinh \cosh \tanh` or
    their inverses, which give the inverse pair (`\sin⁻¹` is `\asin`, also without a call). Any other
    function has no inverse, and `\sin⁻²(x)` is an error.
[^logic]: `∧` `∨` and `→` skip their right operand once the left decides (`false ∧ …`,
    `true ∨ …`, `false → …`); a non-boolean operand is a typed error at that operand. `∀` and
    `∃` are special forms like `\sum` (docs/grammar.md, `## Special forms`) and use the same
    `(x=domain) body` binder.
[^factorial]: An exact non-negative integer up to 100,000 gives the exact product. Any other
    real is `\gamma(x + 1)` (`(1/2)!` is `√π/2`); negative integers and complex values are
    typed errors. `‼` takes exact non-negative integers only. `3!!` is the double factorial `3‼ = 3`, not `(3!)!`. `!=` is a lex error that
    points at `≠`.
[^root]: `∛x` is the call `\root(x, 3)`. `\root(x, n)` takes an exact positive integer `n`
    and evaluates `x^(1/n)` on the numeric seam, so `∛-8` is `-2`.
[^approx]: Numbers only. Floats compare with relative tolerance `1e-9` and absolute `1e-12`
    (Python's `math.isclose`); complex values compare by component. `NaN` is never
    approximately equal to anything.
