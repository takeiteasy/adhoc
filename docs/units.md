# Units

Quantities combine an existing numeric value with physical dimensions. Unit
scales stay exact, arithmetic checks dimensions, and ordinary results display
in SI base units. Long commands leave bare variables such as `m` and `s` free.

```text
9.8\metre \per \second^2        -> = 49/5*\metre*\second^(-2)
2\metre + 30\centimetre         -> = 23/10*\metre
\sqrt(4\metre^2)                -> = 2*\metre
2\metre / \metre               -> = 2
```

`\per` has the same precedence and associativity as `/`. Unit commands are
protected; use ordinary bindings for quantities and custom units.

## Conversion

| Form | Result |
|---|---|
| `\convert(1000\metre, \kilometre)` | Quantity displayed as `1*\kilometre` |
| `\magnitude(1000\metre, \kilometre)` | Number `1` |
| `\convert(q, \metre/\second)` | Quantity displayed in the compound target |

Targets must have matching dimensions. Arithmetic on converted quantities
returns canonical SI output; conversion only changes the display preference.
Magnitude extraction also works on tensors.

Python calls require explicit extraction:

```text
\py("float")(\magnitude(2\metre, \metre)) -> = 2.0
```

## Dimension rules

| Operation | Rule |
|---|---|
| Addition, subtraction, remainder, ordering | Matching dimensions |
| Equality | Different dimensions compare unequal |
| Multiplication and division | Add or subtract dimension exponents |
| Powers and roots | Dimensioned bases require exact rational exponents |
| Trigonometric, exponential and logarithmic functions | Dimensionless inputs |
| Absolute value, real/imaginary parts, conjugation | Preserve dimensions |
| Sign, argument and finite-state predicates | Inspect the magnitude |
| Rounding | Round the canonical SI magnitude and preserve dimensions |

Plain zero is dimensionless. Write `0\metre`, rather than `0`, when adding to
lengths or constructing a dimensioned tensor. Cancellation keeps dimensioned
zero; dimensionless arithmetic results collapse to ordinary numbers.
Radians and steradians are dimensionless. Exact and float magnitudes follow the
existing [numeric-tier rules](numerics.md).[^dimensions]

## Unit catalogue

Unit dimensions follow the SI base-unit relationships.[^si]

| Group | Commands |
|---|---|
| Base | `\metre`, `\kilogram`, `\second`, `\ampere`, `\kelvin`, `\mole`, `\candela` |
| Mass scaling | `\gram` |
| Dimensionless | `\radian`, `\steradian` |
| Frequency and mechanics | `\hertz`, `\newton`, `\pascal`, `\joule`, `\watt` |
| Electrical | `\coulomb`, `\volt`, `\farad`, `\ohm`, `\siemens`, `\weber`, `\tesla`, `\henry` |
| Photometric | `\lumen`, `\lux` |
| Activity and dose | `\becquerel`, `\gray`, `\sievert` |
| Catalytic activity | `\katal` |

Full-name prefixes `kilo`, `mega`, `giga`, `centi`, `milli`, `micro` and `nano`
apply to metre, gram, second, ampere, mole, candela and every named derived unit.
For example, `\millisecond` is exactly `\second/1000`.
Mass prefixes use gram: `\kilogram` is the mass base unit.

## Custom units

`\unit(name, scale)` constructs a unit value without installing a binding.
The name must be a fresh command name; the scale must be a positive, finite,
exact real quantity, dimensionless number or existing unit. Floats and offset conversions are rejected.

```text
\furlong = \unit("furlong", 201.168\metre)
\convert(201.168\metre, \furlong) -> = 1*\furlong
```

## Calculus, symbolic work and tensors

[Derivatives and integrals](calculus.md#dimensioned-calculus) preserve physical
dimensions while numeric algorithms operate on canonical magnitudes.
[Symbolic operations](symbolic.md#dimension-annotations) accept local variable
annotations and return dimensioned expressions or solutions.

Every tensor has one shared dimension. Indexing, slicing, transpose and reshape
preserve it. Broadcasting, elementwise arithmetic, contraction and tensor
products use the scalar dimension rules.

| Matrix operation on dimension `D` | Result dimension |
|---|---|
| Trace, norm | `D` |
| Determinant of an `n×n` matrix | `D^n` |
| Inverse | `D^-1` |
| Rank, reduced row echelon form | Dimensionless |
| `\linsolve(A, b)` | `dimension(b)/dimension(A)` |

```text
A = [2, 0; 0, 4]*\second
\linsolve(A, [6, 8]*\metre)
    -> = [3*\metre*\second^(-1), 2*\metre*\second^(-1)]
```

## Limitations

| Unsupported capability | Ticket |
|---|---|
| Celsius/Fahrenheit absolute temperatures and differences | [#46](https://github.com/takeiteasy/adhoc/issues/46) |
| Mixed-dimension tensors | [#47](https://github.com/takeiteasy/adhoc/issues/47) |
| Dimensioned limits | [#48](https://github.com/takeiteasy/adhoc/issues/48) |
| Dimensioned inverse functions | [#49](https://github.com/takeiteasy/adhoc/issues/49) |
| Dimensioned eigensystems | [#50](https://github.com/takeiteasy/adhoc/issues/50) |
| Dimensioned infinite folds | [#51](https://github.com/takeiteasy/adhoc/issues/51) |

Dimensioned ranges are integration intervals, not enumerable progressions;
stepped dimensioned ranges are rejected. Finite folds over collections preserve
quantity arithmetic, including the first sum term's dimension.

[^dimensions]: A quantity stores a canonical magnitude and seven exact rational
    dimension exponents. Numeric tiers operate on the magnitude. Matrix backends
    factor out the shared dimension before computation and reattach it afterward.

[^si]: [NIST’s SI unit tables](https://www.nist.gov/pml/special-publication-330/sp-330-section-2) give the base-dimension relationships.
