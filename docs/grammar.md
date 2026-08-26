# Grammar

The `ad` subset implemented today. This is the file the parser (`adhoc/parser.py`) is
written against — it should stay in lockstep with the code.

## Lexical rules

- Whitespace is insignificant, except as a token separator.
- `--` starts a line comment, running to end of line.
- A **number literal** is a decimal integer or float: `3`, `0.5`, `12.34`. A `.` is only
  consumed as part of a number when a digit follows it — `1.` lexes as `1`, then fails on the
  lone `.`.
- A **string literal** is `"…"`: raw characters up to the next `"`, escape-free (there are no
  backslash escapes — a string may even span lines). Strings are *literals, not values*: see
  `## String literals` for where they may appear.
- An **identifier** is exactly one character, ASCII or unicode letter (`x`, `π`, `α`, ...).
  This is what makes `ab` unambiguous as `a * b` — see below.
- A **name** longer than one character is written `\`-prefixed (`\pi`, `\sin`, ...). The lexer
  recognizes the full known table (see `docs/language.md`) so that a `\`-token always lexes
  cleanly, and an unbound one fails at evaluation (unbound name) rather than at the lexer
  (unknown token) — the two failure modes are intentionally distinct. `\py` is bound today;
  everything else still errors as unbound until its phase lands.
- Operators: `+ - * / ^ < > <= >= = := ( ) ,`. Statement separator: `;`.

## Grammar (EBNF)

```
program    ::= statement (";" statement)* ";"? ;
statement  ::= func-def
              | string
              | identifier ("=" | ":=") expr
              | expr ;

expr       ::= comparison ;
comparison ::= additive (("<" | ">" | "<=" | ">=") additive)? ;
additive   ::= multiplicative (("+" | "-") multiplicative)* ;
multiplicative
           ::= juxtaposed (("*" | "/") juxtaposed)* ;
juxtaposed ::= unary unary* ;              (* implicit multiplication *)
unary      ::= "-" unary | power ;
power      ::= postfix ("^" unary)? ;      (* right-associative *)
postfix    ::= atom trailer* ;             (* application — see below *)
trailer    ::= "(" args? ")" ;
args       ::= arg ("," arg)* ;
arg        ::= expr | string ;
func-def   ::= identifier "(" params? ")" ("=" | ":=") statement (";" statement)* ;
params     ::= identifier ("," identifier)* ;
atom       ::= number | identifier | "\"-name | "(" sequence ")" ;
sequence   ::= statement (";" statement)* ;
```

A trailing `;` after the last statement is tolerated (`1;` and `2;` both parse as a single
statement, not as a statement followed by an empty one).

## Precedence table

Loosest to tightest:

| Level | Operators | Associativity |
|---|---|---|
| 1 | `=` `:=` | statement level only, non-associative |
| 2 | `..` (range) | non-associative — *reserved, phase 1* |
| 3 | `<` `>` `<=` `>=` | non-associative |
| 4 | `+` `-` (binary) | left |
| 5 | `*` `/` | left |
| 6 | juxtaposition (implicit `*`) | left |
| 7 | unary `-` | prefix |
| 8 | `^` | right |
| 9 | postfix `(…)` application | left |

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
f(x)^2   ->  (f(x))^2       -- application binds tightest
-f(x)    ->  -(f(x))
```

`ATOM_STARTERS` (the set of tokens `juxtaposed` treats as "another factor follows") is
`number`, `identifier`, `\`-name, and `(` — deliberately **not** `-`, so `a - b` always parses
as subtraction, never as `a * (-b)` — and **not** `"`, so a stray string in an expression is
an error at the quote rather than an invisible factor.

## Application: dynamic name-headed parens

A `(…)` trailer attaches **only** to name-ish heads — a single-character identifier, a
`\`-name, or another call. Number-headed parens never even parse as a call (`2(x+1)` is
juxtaposition, always). What a call *does* is decided at evaluation by what the head holds:

```
\py("math.sqrt")(2)   ->  head is callable — apply it
s = \py("math.sqrt")  ->  s is bound to the callable
s(4)                  ->  = 2.0
f()                   ->  zero-argument call (legal)
x = 3; x(1+2)         ->  = 9    -- not callable, one argument: paper product x*(1+2)
x(2, 3), x()          ->  ERROR  -- non-callable with ≠1 arguments can't be a product
```

The fallback rule: **callable → apply; non-callable with exactly one argument → multiply;
anything else → `` `…` is not a function `` at the call's span.** This keeps the paper
reading `x(y+1) = x·(y+1)` alive while letting bound functions apply — at the price that
identical source text reads differently depending on what its head is bound to. Accepted
deliberately: the alternative (static application) made every arithmetic `x(...)` an error,
and multiplication-by-juxtaposition is the reading a calculator's users expect first.
Rebinding a name from number to function flips old lines' meaning — visible in source, and
the failure mode when it surprises you is a typed error, not a silent wrong value.

Errors inside either reading point at the whole call node's span (wider than a bare binop's,
the cost of deciding late). Applying a string result falls into the product path and dies as
the usual typed "strings are not numbers".

## Functions and conditionals

Function definitions are callable values. Names and parameters are still one-character
identifiers, so the recursive example uses `f`, not `fact`:

```
f(x) = x^2 + 1
f(3)                         ->  = 10
f(a,b) = c = ab; cc          -- c and the parameters are call-local
f(3,4)                       ->  = 144
f(n) = \if(n <= 1, 1, n*f(n-1))
```

Function bodies are semicolon-separated statements. A call gets a fresh local frame;
reads fall through to globals, while assignments never escape the call. The function's
own name is installed in that frame before the body runs, enabling recursion. Definitions
are first-class and display as `<fn f(x)>`.

Because `;` also separates top-level statements and the source has no newline token, a
function definition consumes the semicolon-separated body to the end of its input unit.
In a script, put definitions after the top-level setup they need; call them from a later
REPL input or source unit.

`\if(condition, then)` and `\if(condition, then, otherwise)` are lazy, call-shaped
conditionals. The selected branch alone is evaluated. The two-argument form is a
statement-level no-op when its condition is false; in an expression requiring a value,
that case reports an error. Parenthesized sequences provide multi-statement branches:

```
\if(x > 0, (y = x^2; y + 1), (y = -x; y * 2))
```

Comparisons `<`, `>`, `<=`, and `>=` return booleans, displayed as `true` or `false`.
Booleans are valid values and conditions but are not numeric operands.

## String literals

Strings are **literals, not values**. There is no string type in the value model; a string
never enters the environment, cannot be bound, stored, concatenated, or computed on. They
appear in exactly two places:

1. **As a whole argument of a call** — the `\py("dotted.path")` case. The literal converts
   directly to a native Python `str` at the boundary; no ad string value ever exists.
2. **As a whole statement** — ignored, exactly like a comment:
   ```
   > "chapter 3: convergence"
   > 1 + 1
   < = 2
   ```
   A string anywhere else inside an expression is a parse error with the caret at the
   opening quote (`1 + "a"` errors; `"a" + 1` also errors, at the `+`).

When a Python function hands a `str` back across the boundary, it is **display-only**: it
prints quoted (`= "hello"`), and any attempt to assign it fails (`strings cannot be assigned
— they are literals, not values`). See docs/numerics.md for the full conversion matrix.

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
- `x := e`, `x` bound → rebind, prints `x = v`
- `x := e`, `x` unbound → error: `` `x` does not exist! ``
- bare expression → prints `= v`

A callable binds like any other value (`s = \py("math.sqrt")` prints `s = <py math.sqrt>`);
a call returning a string is rejected instead of bound (strings are literals, see
`## String literals`). Two non-numeric values never compare equal unless identical.

## Deferred

`..` ranges, `Σ`/`Π`/`\lim`, logical operators, collections, the
exact-arithmetic tower beyond int/rational/float, symbolic algebra, graphing.
See `ROADMAP.md` and the tracker for the phase each lands in.
