# Grammar (phase 0)

The phase-0 subset of `ad`: arithmetic, assignment, and nothing else yet. This is the file
the parser (`ad/parser.lisp`) is written against — it should stay in lockstep with the code.

## Lexical rules

- Whitespace is insignificant, except as a token separator.
- `--` starts a line comment, running to end of line.
- A **number literal** is a decimal integer or float: `3`, `0.5`, `12.34`.
- An **identifier** is exactly one character, ASCII or unicode letter (`x`, `π`, `α`, ...).
  This is what makes `ab` unambiguous as `a * b` — see below.
- A **name** longer than one character is written `\`-prefixed (`\pi`, `\sin`, ...). Phase 0
  has no bound names of its own, but the lexer recognizes the full known table (see
  `docs/language.md`) so that a `\`-token always lexes cleanly, and an unbound one fails at
  evaluation (unbound name) rather than at the lexer (unknown token) — the two failure modes
  are intentionally distinct.
- Operators: `+ - * / ^ = := ( )`. Statement separator: `;`.

## Grammar (EBNF)

```
program    ::= statement (";" statement)* ;
statement  ::= identifier ("=" | ":=") expr
             | expr ;

expr       ::= additive ;
additive   ::= multiplicative (("+" | "-") multiplicative)* ;
multiplicative
           ::= juxtaposed (("*" | "/") juxtaposed)* ;
juxtaposed ::= unary unary* ;              (* implicit multiplication *)
unary      ::= "-" unary | power ;
power      ::= atom ("^" unary)? ;         (* right-associative *)
atom       ::= number | identifier | "(" expr ")" ;
```

## Precedence table

Loosest to tightest:

| Level | Operators | Associativity |
|---|---|---|
| 1 | `=` `:=` | statement level only, non-associative |
| 2 | `..` (range) | non-associative — *reserved, phase 1* |
| 3 | `+` `-` (binary) | left |
| 4 | `*` `/` | left |
| 5 | juxtaposition (implicit `*`) | left |
| 6 | unary `-` | prefix |
| 7 | `^` | right |
| 8 | postfix `'`, `[…]`, `(…)` | — *reserved, phases 1-2* |

Juxtaposition binds tighter than `*`/`/` but looser than `^`, matching how the expression
reads on paper:

```
1/2x     ->  1 / (2*x)      -- not (1/2)*x
2x^2     ->  2 * (x^2)      -- ^ still tightest
-2^2     ->  -(2^2) = -4    -- unary minus is looser than ^
2^-1     ->  1/2            -- exact rational, displays as a fraction (docs/numerics.md)
2^3^2    ->  2^(3^2) = 512  -- right-associative
1 + 2*3  ->  7
(1+2)*3  ->  9
```

## The `\` sigil

An identifier is exactly one character. Any language-defined name longer than one character
is `\`-prefixed, regardless of script — `\pi`, `\sum`, `\sin`, `\solve`, `\map`, `\graph`. Where
a `\`-name has a single-character unicode form, they are the same name (`\pi` ≡ `π`); where
there is no unicode form, the `\` spelling is the only one (`\sin`, `\lim`, `\solve`, ...).

The names are chosen to match their LaTeX command where one exists, so `ad` source reads like
the ASCII you'd already type to write the same expression in LaTeX — this is a naming
convention, not a claim that `ad` parses TeX. See `docs/language.md` for the full table and
`README.md` for the framing.

## Assignment semantics

- `x = e`, `x` unbound → bind `x`, prints `x = v`
- `x = e`, `x` bound → **compare** current value to `v`, prints `true` / `false`
  (a printed form only — there is no boolean type until phase 1's comparison operators land)
- `x := e`, `x` bound → rebind, prints `x = v`
- `x := e`, `x` unbound → error: `` `x` does not exist! ``
- bare expression → prints `= v`

## Incomplete input

A statement that runs out of tokens mid-expression — an unclosed `(`, a trailing binary
operator, `x =` with nothing after it — is a distinct condition (`ad-incomplete-input`, a
subclass of the ordinary parse error) rather than a plain parse error. The REPL uses this to
offer a `. ` continuation prompt and read another line instead of reporting a diagnostic; a
genuine syntax error like `1 + * 2` still reports immediately. This is a REPL-level behavior,
not a grammar change — `program` is still a single line (or, once continued, a small number of
joined lines) parsed by the same grammar above.

## Deferred out of phase 0

`..` ranges, `Σ`/`Π`/`\lim`, comparison/logical operators, functions, piecewise conditionals,
collections, the exact-arithmetic tower beyond int/rational/float, symbolic algebra, script
mode, graphing. See the tracker for the phase these land in.
