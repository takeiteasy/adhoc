# Notation

Paper-math glyphs and their ASCII spellings. Every glyph parses to an ordinary operator or
call, so quotes print the canonical form and every glyph has an ASCII spelling.

| Glyph | ASCII | Meaning | Level |
|---|---|---|---|
| `x²` `x⁻¹` `2¹⁰` | `x^2` | power[^superscript] | postfix |
| `x₁` `a₂₃` | — | a distinct name[^subscript] | name |
| `n!` | — | factorial[^factorial] | postfix |
| `n‼` | `n!!` | double factorial | postfix |
| `∛x` `∜x` | `\root(x, 3)` | cube and fourth root[^root] | prefix, like `√` |
| `≤` `≥` | `<=` `>=` | ordering | comparison |
| `≠` | `\neq` | not equal (negated `=` check) | comparison |
| `≈` | `\approx` | approximately equal[^approx] | comparison |
| `∉` | `\notin` | not a member | comparison |
| `⊂` `⊇` `⊃` | `\subset` `\supseteq` `\supset` | proper subset, superset, proper superset | comparison |
| `∅` | `\emptyset` | the empty set (prelude constant) | name |

```
2x²            ->  2 * (x^2)
2^3!           ->  2^(3!) = 64
-3!            ->  -(3!)  = -6
∛-8            ->  = -2
1 ≤ 2 ≠ 3     -- comparisons do not chain: parenthesize
{1} ⊂ {1, 2}   ->  = true
3 ∉ ∅          ->  = true
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

## Membership

`∈` and `∉` take a set, an array, or a range on the right. Array membership uses the
binding rule's equality; range membership asks whether the value is a term of the
progression. `..` binds looser than comparison, so a range operand takes parentheses
([#84](https://todo.sr.ht/~takeiteasy/adhoc/84)):

```
2 ∈ ⟨1, 2, 3⟩       ->  = true
5 ∈ (1,3..9)         ->  = true
4 ∈ (1,3..9)         ->  = false
1000000 ∈ (1..)      ->  = true
```

## Operator values

`(!)`, `(‼)`, `(∛)`, `(∜)`, `(≠)`, `(≈)`, `(∉)`, `(⊂)`, `(⊇)`, `(⊃)` are function values
like the other operators (`docs/grammar.md`, `## Operator values`). Postfix operators and
radicals have no sections. `(∛)` is the partial `\root(·, 3)`.

## Limitations

- Superscript and subscript letters (`xⁿ`, `xᵢ`, `Aᵀ`) are not notation —
  [#81](https://todo.sr.ht/~takeiteasy/adhoc/81).
- Subscripted names have no ASCII spelling —
  [#82](https://todo.sr.ht/~takeiteasy/adhoc/82).
- `\sin²(x)` is not function-power notation —
  [#83](https://todo.sr.ht/~takeiteasy/adhoc/83).
- `!` takes non-negative integers only; non-integers wait for `\gamma` —
  [#77](https://todo.sr.ht/~takeiteasy/adhoc/77).
- Logical operators `∧ ∨ ¬ → ↔ ∀ ∃` are not built —
  [#80](https://todo.sr.ht/~takeiteasy/adhoc/80).

[^superscript]: A run is an optional `⁻` then digits `⁰¹²³⁴⁵⁶⁷⁸⁹`, one exponent: `x⁻¹⁰` is
    `x^-10`. A lone `⁻` is a lex error.
[^subscript]: A letter followed by subscript digits `₀…₉` lexes as one identifier. `x₁` is
    unrelated to `x`, aliases and parameters accept it, and `\`-names take no subscript.
[^factorial]: Exact non-negative integers only, up to 100,000; anything else is a typed
    error. `3!!` is the double factorial `3‼ = 3`, not `(3!)!`. `!=` is a lex error that
    points at `≠`.
[^root]: `∛x` is the call `\root(x, 3)`. `\root(x, n)` takes an exact positive integer `n`
    and evaluates `x^(1/n)` on the numeric seam, so `∛-8` is `-2`.
[^approx]: Numbers only. Floats compare with relative tolerance `1e-9` and absolute `1e-12`
    (Python's `math.isclose`); complex values compare by component. `NaN` is never
    approximately equal to anything.
