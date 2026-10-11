# Symbolic solution sets

`\solve` returns a non-enumerating symbolic set for infinite scalar families and
scalar results restricted to a domain. Finite solutions remain ordinary sets.
See [solving](symbolic.md#solving) for inputs and domain selection.
All-preimage inverse calls, such as `\sin⁻¹(0, \all=\true)`, use the same
representations; see [all preimages](calculus.md#all-preimages).

## Use

```text
s = \solve(\expr(\sin(x) = 0))
\pi ∈ s                         -> = true
\pi/2 ∈ s                       -> = false

r = \solve(\expr(e^x = 5))
\ln(5) + 2*\pi*i ∈ r            -> = true
```

The default domain is complex. `\domain="real"` selects real solutions and also
applies to finite equation-system solves.

```text
\solve(\expr(x=x), \expr(x))                  -> = ℂ
\solve(\expr(x=x), \expr(x), \domain="real") -> = ℝ
```

## Operations

| Operation | Behavior |
|---|---|
| Binding, function arguments and nested collections | Preserve the symbolic set |
| Display and `\tex(s)` | Set-builder families, domain symbols and set combinations |
| `v ∈ s`, `v ∉ s` | Numeric membership; undecidable membership produces a typed error |
| Equality | Structural equality with bound names normalized[^equality] |
| Enumeration, indexing and `\len` | Typed error |
| Arithmetic, set algebra and subset comparisons | Typed error |

Dimensioned families retain the solved unknown’s dimension. Membership compares
canonical magnitudes only when dimensions match; other dimensions return false.
See [dimension annotations](symbolic.md#dimension-annotations).

Membership preserves exact numeric values. It runs under the
[symbolic timeout](symbolic.md#time-limit), including when called through a
function or used as a condition.

## Rendering and parameters

Families display as `{expression | n ∈ ℤ}`. A union retains each family, and
whole domains display as `ℝ` or `ℂ`. `\tex` uses the corresponding LaTeX forms.
Binder names avoid collisions with free parameters.

Free parameters remain symbolic. Binding a parameter later does not substitute
into an existing solution set. Symbolic-set display describes the value; it is
not a parseable constructor. Existing set-builder syntax still constructs finite
sets by iterating its domain.

## Limitations

| Limit | Ticket |
|---|---|
| Infinite equation-system families are errors | [#43](https://github.com/takeiteasy/adhoc/issues/43) |
| Unresolved `ConditionSet` results are closed-form errors; conditional real solutions are unsupported | [#44](https://github.com/takeiteasy/adhoc/issues/44) |
| Set algebra and subset comparisons involving symbolic sets are unsupported | [#45](https://github.com/takeiteasy/adhoc/issues/45) |

[^equality]: Equality compares backend set structures after normalizing bound
    variables. Equivalent sets with different structures can compare unequal;
    equality does not invoke a general mathematical equivalence solver.
