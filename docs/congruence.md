# Integer congruence

`a ≡ b (mod n)` returns `true` when `a-b` is divisible by `n`.
All three values are exact integers, and `n` is nonzero. Negative moduli are valid.

## Spellings and examples

| Form | Result |
|---|---|
| `17 ≡ 2 (mod 5)` | `true` |
| `17 \equiv 3 (\mod 5)` | `false` |
| `-7 ≡ 2 (mod -3)` | `true` |
| `17.0 ≡ 2 (mod 2^2+1)` | `true` |
| `\congruent(17, 2, 5)` | `true` |

Both `≡` and `\equiv` accept `(mod n)` and `(\mod n)`.
The modulus accepts a full expression, including arithmetic and calls.
Operands evaluate once, left to right: `a`, `b`, then `n`.

## Parsing

Congruence has comparison precedence and does not chain. Arithmetic binds tighter;
logic and ternaries bind looser. Parenthesize comparisons when nesting them.

```text
f(x)=x+1
g(x)=x-1
f(16) ≡ g(3) (mod 5)             -> = true
x=1
12 ≡ 2(x+1) (mod 4)              -> = true
17 ≡ 2 (mod 5) ∧ 2<3             -> = true
```

The first suffix at the right operand's nesting level terminates that operand,
including a name or call result. Calls and implicit multiplication before the suffix
keep their usual meaning. The suffix is required. Bare `mod` is a contiguous keyword
with whitespace before its operand, only in this suffix; elsewhere `mod` means
`m*o*d`. Ordinary `%` and `\mod` remain remainder operators.

## Reusable predicates and quotes

`\congruent(a,b,n)` takes three positional arguments. It supports partial application
and higher-order functions:

```text
\filter(\congruent(·,2,5), ⟨1,2,7,8,17⟩)  -> = ⟨2, 7, 17⟩
q=\expr(x ≡ 2 (mod 5))
\eval(q,x=17)                              -> = true
```

Quoted congruences display as parseable expressions. `\tex` renders them using
`\equiv` and `\pmod{…}`. Symbolic rewriting rejects congruence as an unsupported
comparison, like other non-equality comparisons.

## Invalid values

Floats (including `2e0`), non-integer rationals, complex numbers, booleans,
collections, strings and units produce typed errors. Exact decimals such as `2.0`
are integer values and are accepted. A zero modulus produces a typed error.
