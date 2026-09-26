# Standard library

Prelude functions. Exact arguments stay exact where a tier can hold them; floats stay on
the float tier. Every name is protected: it cannot be rebound or shadowed.

## Rounding

| Function | Result | Example |
|---|---|---|
| `\floor(x)` | greatest integer ≤ x | `\floor(-5/2)` → `-3` |
| `\ceil(x)` | least integer ≥ x | `\ceil(\pi)` → `4` |
| `\trunc(x)` | toward zero | `\trunc(-5/2)` → `-2` |
| `\round(x)` | nearest integer, ties away from zero | `\round(-5/2)` → `-3` |
| `\round(x, n)` | round to `n` decimal digits (`n` may be negative) | `\round(22/7, 2)` → `157/50` |
| `\abs(x)` | magnitude; on a complex value, the modulus | `\abs(3+4i)` → `5` |
| `\sign(x)` | `-1`, `0` or `1` | `\sign(-\pi)` → `-1` |

Exact and symbolic arguments give exact integers; non-finite floats pass through.
Complex arguments are a typed error, except for `\abs`.
