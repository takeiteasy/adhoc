# Grammar

The `ad` subset implemented today. This is the file the parser (`adhoc/parser.py`) is
written against — it should stay in lockstep with the code.

## Lexical rules

- Whitespace is insignificant, except as a token separator — and except that a **newline
  is a token** (`Newline`), everywhere. The parser skips newline runs wherever an
  *operand* is expected, so a statement or expression continues onto the next line
  mid-expression (`1 +` NL `2` is one sum, an argument may start on the line after its
  `,`); where an expression is complete, the newline separates statements. The rule is
  uniform inside `(...)`: a parenthesized group is the multi-line statement form
  (`## Groups`), and argument lists span lines comma-separated as they always have.
- `--` starts a line comment, running to end of line; the newline that ends it is an
  ordinary newline token.
- A **number literal** is an integer, an exact decimal, or a float spelling
  (docs/numerics.md): `3` is an exact integer; a dotted decimal without an
  exponent (`0.5`, `12.34`, `.5`) is an *exact rational* read from its own
  digits; the float spellings are the trailing-dot marker (`1.` is the float
  1.0, explicitly inexact) and any exponent form (`5e-1`, `1.5e3`, `2e3` — an
  `e`/`E` not followed by an optional sign and a digit stays juxtaposition, so
  `2e` is `2*e`). A `.` not consumed by a number is only ever the range
  operator's first dot — `1..10` lexes `1`, `..`, `10`.
- A **string literal** is `"…"`: characters up to the closing `"`, possibly spanning lines.
  Inside a literal exactly four escapes decode — `\"` (quote), `\\` (backslash), `\n`
  (newline), `\t` (tab) — and any other backslash pair is a lex error. Strings are full
  values: see `## String literals` for their operators.
- An **identifier** is one ASCII or unicode letter, optionally followed by a subscript run of
  digits `₀…₉` and letters `ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ` (`x`, `π`, `α`, `x₁`, `a₂₃`, `xᵢⱼ`); `x₁` is a
  name unrelated to `x`. The ASCII spelling is a letter, `_`, then ASCII letters or digits
  (`x_1`, `x_ij`, `x_b`); it is the same name as the glyph form where every character has a
  glyph, and its own name otherwise (`x_b`, `x_ib`). A `_` with no alphanumeric after it is
  the placeholder. A subscript glyph with no letter before it is a lex error. `ab` is still
  `a * b`, and `∅` lexes as an identifier that aliases `\emptyset`. See `docs/notation.md`.
- A **superscript run** (`²`, `⁻¹`, `ⁿ⁺¹`, `⁽ⁿ⁺¹⁾`: digits, letters, `⁺ ⁻ ⁽ ⁾`) is one token,
  sugar for `^` with the run read as an expression. A run without digits or letters is a lex
  error. `ᵀ` is not part of a run: it is the transpose `'`.
- The radicals `∛` and `∜` are prefix operators like `√`; they rewrite to `\root(x, 3)` and
  `\root(x, 4)`. `!` (factorial) and `‼` / `!!` (double factorial) are postfix. `!=` is a
  lex error pointing at `≠`.
- The radical `√` is the one **prefix operator**: it is a math symbol, not a letter, so
  it lexes as its own token and cannot be a name — it can never be aliased, bound, or
  shadowed. The parser rewrites `√` + operand into a `\sqrt(...)` application
  (docs/numerics.md for the values it produces).
- A **name** longer than one character is written `\`-prefixed (`\pi`, `\sin`, `\fact`, ...).
  After the first character a name may continue with letters or underscores (`\rel_tol`,
  `\my_var`); a `_` cannot start a name. Backslash names may be built-ins or user-defined
  names, including variables; an unbound one fails at evaluation. `\let` is the one
  statement keyword in this group: it is not a bindable name.
- Operators: `+ - * / @ ∘ ∪ ∩ ∖ ∈ ∉ ⊆ ⊂ ⊇ ⊃ ≠ ≈ ^ < > <= >= ≤ ≥ = .. ( ) [ ] { } ⟨ ⟩ #[ ' ! ‼ , ? :`. Statement separator: `;`
  (inside `[...]` it separates rows). `#[` is one token; a `#` not followed by `[` is a lex error.
  A lone `·` (U+00B7), `⋅` (U+22C5) or `_` is the partial-application placeholder
  (`## Composition and partial application`); inside a `\`-name `_` is an ordinary name
  character.
  A backtick starts a quote: `` `(expression) `` or a statement-sequence quote.
  `=` is the one binding/check operator (see `## Assignment semantics`); there is no
  `==` — two adjacent `=` are two tokens and cannot parse. `?` opens a ternary
  conditional and `:` closes it
  in expression position (the only other use of `:` is the import member list).
- The lambda heads `\λ` / `\fn` are the one spelling the parser consumes specially —
  and only when a parameter-list paren follows. Any other `\`-name lexes cleanly,
  binds like any name, and fails at evaluation if unbound.

## Grammar (EBNF)

```
program    ::= statement (sep statement)* sep? ;
sep        ::= newline-run | ";" ;    -- a ";" after a newline run is one separator too
statement  ::= func-def
             | let-stmt
             | import-stmt
             | pyimport-stmt
             | spelling-directive
             | string
             | name "=" expr
             | expr ;
let-stmt    ::= "\let" name "=" expr
             | "\let" name "(" params? ")" "=" statement (";" statement)* ;
import-stmt   ::= "\import" "(" string (":" member ("," member)*)? ")" ;
pyimport-stmt ::= "\pyimport" "(" string ":" member ("," member)* ")" ;
member        ::= identifier | "\"-name ;
spelling-directive ::= alias-stmt | dual-stmt ;
alias-stmt  ::= "\alias" name "," single-char ("," single-char)* ;
dual-stmt   ::= "\dual" name "," single-char params? "=" statement (";" statement)* ;
single-char ::= identifier ;                (* aliases are one-character letters *)
name        ::= identifier | "\"-name ;

expr       ::= ternary ;
ternary    ::= range ("?" ternary ":" ternary)? ;   (* right-associative *)
range      ::= comparison (".." comparison? | "," comparison ".." comparison?)? ;
                                           (* the "," form is not read inside lists *)
comparison ::= additive (cmp-op additive)? | additive ("∈" | "\\in" | "∉" | "\\notin") range-tail ;
range-tail ::= additive (".." additive? | "," additive ".." additive?) ;   (* membership only *)
cmp-op     ::= "<" | ">" | "<=" | "≤" | ">=" | "≥" | "≠" | "\\neq" | "≈" | "\\approx"
             | "∈" | "\\in" | "∉" | "\\notin" | "⊆" | "\\subseteq" | "⊂" | "\\subset"
             | "⊇" | "\\supseteq" | "⊃" | "\\supset" ;
additive   ::= multiplicative (("+" | "-" | "∪" | "\\cup" | "∖" | "\\setminus") multiplicative)* ;
multiplicative
           ::= juxtaposed (("*" | "/" | "@" | "\\contract" | "∩" | "\\cap" | "∘" | "\\circ" | "%" | "\\mod") juxtaposed)* ;
juxtaposed ::= unary unary* ;              (* implicit multiplication *)
unary      ::= "-" unary | power ;
radical    ::= "√" unary ;                 (* prefix spelling of \sqrt(...) *)
nth-root   ::= ("∛" | "∜") unary ;         (* prefix spelling of \root(x, 3) / \root(x, 4) *)
power      ::= postfix ("^" unary)? ;      (* right-associative *)
postfix    ::= atom trailer* ;             (* application — see below *)
trailer    ::= "(" args? ")" | "[" expr ("," expr)* "]" | "'" | "ᵀ" | "!" | "‼" | "!!" | superscript
             | superscript "(" args? ")" ;   (* function power, on a name head only *)
superscript ::= (superscript-glyph)+ ;         (* sugar for "^" with the run read as an expression *)
args       ::= arg ("," arg)* ;
arg        ::= expr | string | kwarg | hole | operator ;   (* holes and operators only as a whole argument *)
hole       ::= "·" | "⋅" | "_" ;
operator   ::= "+" | "-" | "*" | "/" | "^" | "@" | "∘" | "∪" | "∩" | "∖" | "<" | ">" | "<="
             | ">=" | "≤" | "≥" | "≠" | "≈" | "∈" | "∉" | "⊆" | "⊂" | "⊇" | "⊃" | "√" | "∛" | "∜"
             | "!" | "‼" | "\\contract" | "\\circ" | "\\cup" | "\\cap" | "\\setminus" | "\\in"
             | "\\notin" | "\\subseteq" | "\\subset" | "\\supseteq" | "\\supset" | "\\neq" | "\\approx" ;
kwarg      ::= (identifier | "\"-name) "=" (expr | string) ;
func-def   ::= name "(" params? ")" "=" statement (";" statement)* ;
params     ::= name ("," name)* ;
atom       ::= number | string | identifier | "\"-name | "(" sequence ")"
              | "(" operator ")" | "(" operator operand ")" | "(" operand operator ")"
              | lambda | radical | quote | tensor | array | set ;
tensor     ::= "[" expr ("," expr)* "]"
             | "[" expr ("," expr)* (";" expr ("," expr)*)* ";"? "]" ;
set        ::= "{" (expr ("," expr)*)? "}" ;
array      ::= ("⟨" | "#[") (expr ("," expr)*)? ("⟩" | "]")
             | "\\arr" "(" (expr ("," expr)*)? ")" ;
quote      ::= ("\\expr" | "`") "(" expr ")"
             | ("\\expr" | "`") "(" "(" sequence ")" ")" ;
eval       ::= "\\eval" "(" expr ("," kwarg)* ")" ;
sequence   ::= statement (sep statement)* sep? ;
lambda     ::= ("\λ" | "\fn") "(" params? ")" expr ;
```

`\let` is a statement form. Its variable form is legal wherever a statement is legal;
its function form is top-level (including a group that flattens at top level). A bare
or misplaced `\let` is an error, and incomplete forms enter the REPL continuation path.

`\expr` and `` ` `` quote without evaluating. A parenthesized statement sequence uses
`\expr((x=1; x+1))`; a single-statement body has a trailing separator,
`\expr((x+1;))`. `\eval` evaluates an expression value with optional named bindings.
Binding values evaluate in the caller's scope before the quoted value runs. Other names
read from the scope of the `\eval` call; the bindings are local to that evaluation.
Protected names cannot be bound, except
`i` under the usual rule. Expression values print as parseable `\expr(...)` text, and the
binding rule compares them by AST structure and canonical names.
`\body(f)` returns the statement body of a user-defined function or lambda as an
expression value. Built-ins and Python callables have no reflected body.
`\reduce(e)` takes an expression quote and returns its beta-normal form. It uses
leftmost-outermost reduction, avoids variable capture, and stops with a typed error after
10,000 beta steps. Nested quotes are opaque. Named function calls stay as calls; arithmetic
stays as syntax until `\eval` runs the result. Statement quotes are rejected.

`sep` inside a group's `sequence` is a newline run or a single `;` — blank lines are
free, `;;` is an error. A trailing `;` after the last statement is tolerated (`1;` and
`2;` both parse as a single statement, not as a statement followed by an empty one),
at top level and before a group's closing `)` alike.

Special forms sit in postfix position but are not applications — their first parenthesized
argument is a binding, not a general expression (see `## Special forms`):

```
fold       ::= ("\sum" | "\prod" | "Σ" | "Π") "(" ident "=" expr ")" expr ;
limit      ::= "\lim" "(" ident "=" expr ")" expr ;
```

## Precedence table

Loosest to tightest:

| Level | Operators | Associativity |
|---|---|---|
| 1 | `? :` (ternary) | right |
| 2 | `=` (binding/check) | statement level only, non-associative |
| 3 | `..` (range) | non-associative |
| 4 | `<` `>` `<=` `>=` `≤` `≥` `≠` `≈` `∈` `∉` `⊆` `⊂` `⊇` `⊃` | non-associative |
| 5 | `+` `-` (binary), `∪` `∖` | left |
| 6 | `*` `/` `@` `%`, `∩`, `∘` | left |
| 7 | juxtaposition (implicit `*`) | left |
| 8 | unary `-`, `√` `∛` `∜` | prefix |
| 9 | `^` | right |
| 10 | postfix `(…)` application, `[…]` index, `'` transpose, `!` `‼` factorial, superscript `²` | left |

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
√2^2     ->  √(2²) = 2      -- the radical's operand parses at the unary level
2^√2     ->  2^(√2)         -- a radical can sit inside the exponent
2√3      ->  2*√3           -- the radical is an atom starter: it juxtaposes
2x²      ->  2 * (x^2)      -- superscript is a postfix trailer, tighter than juxtaposition
2^3!     ->  2^(3!) = 64    -- factorial binds tighter than ^
-3!      ->  -(3!) = -6
∛-8      ->  = -2           -- `\root(-8, 3)`
```

Glyphs and their ASCII spellings are in `docs/notation.md`.

A parenthesized composition is a call head: `(f ∘ g)(x)` applies. Unparenthesized,
`f ∘ g(x)` composes `f` with the result of `g(x)`.

`ATOM_STARTERS` (the set of tokens `juxtaposed` treats as "another factor follows") is
`number`, `string`, `identifier`, `\`-name, `√`, `∛`, `∜`, `(`, `[`, `{`, `⟨`, and `#[` — deliberately **not** `-` or `'`, so `a - b` always
parses as subtraction, never as `a * (-b)`. A string juxtaposed with anything (`"a" "b"`)
parses as the multiplication it spells and dies as the usual typed "strings are not
numbers" at evaluation — the same shape as any other string reaching a numeric operator.

## Application: dynamic name-headed parens

A `(…)` trailer attaches **only** to name-ish heads — a single-character identifier, a
`\`-name, another call, or a parenthesized lambda (see `## Lambdas`). Number-headed
parens never even parse as a call (`2(x+1)` is juxtaposition, always). What a call *does* is decided at evaluation by what the head holds:

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
reading `x(y+1) = x*(y+1)` alive while letting bound functions apply — at the price that
identical source text reads differently depending on what its head is bound to. Accepted
deliberately: the alternative (static application) made every arithmetic `x(...)` an error,
and multiplication-by-juxtaposition is the reading a calculator's users expect first.
Rebinding a name from number to function flips old lines' meaning — visible in source, and
the failure mode when it surprises you is a typed error, not a silent wrong value.

### Keyword arguments

Arguments may be given as `name=value` pairs, passed through application to Python
callables as native keyword arguments:

```
\py("int")("ff", \base=16)                 ->  = 255
\py("math.isclose")(1, 2, \rel_tol=0.5)    ->  = 1
s = \py("math.isclose")
s(1, 1.5, \abs_tol=1)                      ->  = 1
\py("open")("plot.svg", \mode="w")         -- the savefig/export shape
```

Multi-character kwarg names take the `\` sigil like every other multi-character name
(`\dpi=300`); a single-character name needs none (`s=10`). The value may be any expression
or a string literal (`\mode="w"`). A kwarg never assigns — `name=value` inside an argument
list is purely an argument-passing form; statement-level `=` is the only binding/check
operator.
Positional arguments and kwargs collect separately, so
their relative source order carries no meaning — Python's own binding rules decide what
`f(2, \a=1)` binds to. A duplicate kwarg name is a parse error; kwargs reaching a
user-defined function are a typed error (parameters are positional); a non-callable head
with kwargs is `` `…` is not a function `` rather than the product fallback. Python
callables that accept no keyword arguments (many C builtins) report their `TypeError` at
the call's span like any other callee failure.

Errors inside either reading point at the whole call node's span (wider than a bare binop's,
the cost of deciding late). Applying a string result falls into the product path and dies as
the usual typed "strings are not numbers".

## Functions and conditionals

Function definitions are callable values. Multi-character function and parameter names use
the backslash sigil:

```
f(x) = x^2 + 1
f(3)                         ->  = 10
f(a,b) = c = ab; cc          -- c and the parameters are call-local
f(3,4)                       ->  = 144
\fact(n) = n <= 1 ? 1 : n*\fact(n-1)
```

Function bodies are semicolon-separated statements; a parenthesized group (`## Groups`)
gives a def a multi-line body. A call gets a fresh local frame;
reads fall through to globals, while assignments never escape the call. The function's
own name is installed in that frame before the body runs, enabling recursion. Definitions
are first-class and display as `<fn f(x)>` or `<fn \fact(n)>`.

A definition inside a function or quoted statement body binds locally without an echo. Its
value is the new callable. A newline separates a nested definition from a following call:

```
f(x) = (
g(y) = x + y
g(2)
)
f(3)                         ->  = 5
```

A semicolon after `g(y) = ...` continues `g`'s body.

Because `;` also separates top-level statements, a function definition consumes the
semicolon-separated statements after its `=` **on its own line** as its body — write one
definition per line, or group a multi-statement body in parentheses (a `;` after the
group's closing `)` still belongs to the body — see `## Groups`).

## Groups: parenthesized statement sequences

A parenthesized group is a statement sequence with an explicit end — and the
multi-line statement form:

```
sequence ::= statement (sep statement)* sep? ;   -- sep: newline run | ";"
```

```
f(x) = (
y = x^2
y + 1
)                   -- an explicit multi-statement def body

c ? (a = 1
     a + 1) : 0     -- a group as a ternary branch
```

Statements inside a group separate on a newline run or a single `;` (blank lines are
free, `;;` is an error, a trailing `;` before `)` is tolerated), and the same uniform
newline rule holds that governs the top level: a line ending mid-expression continues
(`x = 1 +` NL `2` is one sum, a committed range `1..` runs to the `)`), while an
operator that *starts* a line belongs to a new statement (`x = 1` NL `+ 2` is two
statements, the second an error). The same rule makes argument lists span lines
comma-separated — an argument missing its comma is a new statement and a parse error.
There is no single-line/new-line distinction to learn: parens group, newlines
separate complete statements, trailing operators continue.

It parses through the same statement machinery as the top level and produces the
same `Seq` node — **no scope of its own**, the ordinary flatten/echo/frame rules.
A group is legal anywhere an expression is: statement position (it flattens into
the enclosing unit, each statement with its own echo line), def bodies, ternary
branches, lambda bodies. Its value is its last statement's value.

**Explicit extent.** The form earns its keep in expression position, where `,` and
`)` would otherwise end the sequence: def bodies and lambda bodies. It does **not**
shield against `;`: in a def body or at top level, a `;` after the closing `)`
simply continues the enclosing statement sequence (a group is one grouped statement
of it — definitions still consume their line). Imports are rejected inside an ordinary
group; a quoted statement sequence may contain them. `\alias`/`\dual` are rejected
(top-level directives). An unclosed group is incomplete
input — the REPL offers a continuation prompt, and a blank line cancels.

Braces `{}` are not a grouping form — they build sets (`## Sets`).

## Tensors

`[...]` builds a uniform numeric tensor: vectors are rank 1, matrices rank 2, and higher
ranks nest. Indexing is 1-based.

```
v = [1, 2, 3]                   -- rank 1
m = [1, 2; 3, 4]                -- `,` separates columns, `;` rows
[[1, 2; 3, 4], [5, 6; 7, 8]]    -- rank 3: nested tensors of one shape
m[2, 1]  ->  = 3                m[1]  ->  = [1, 2]
```

| Form | Meaning |
|---|---|
| `[a, b]` | vector; entries are numbers of any tier, or equal-shape tensors that stack |
| `[a, b; c, d]` | matrix; `;` rows hold numbers and have one length |
| `[a, b;]` / `[a; b]` | one-row / one-column matrix — a trailing `;` keeps a single row a matrix |
| `x[i, j]` | 1-based index; fewer indices than axes gives the sub-tensor |
| `x'` | transpose: reverses the axes; a vector is unchanged |
| `a @ b`, `a \contract b` | contraction of `a`'s last axis with `b`'s first: dot product, matrix product |
| `+ - * / ^` | elementwise; a scalar broadcasts, two tensors need one shape |

```
m * m        ->  = [1, 4; 9, 16]        m @ m   ->  = [7, 10; 15, 22]
m + 1        ->  = [2, 3; 4, 5]         m'      ->  = [1, 3; 2, 4]
[1, 2] @ [3, 4]  ->  = 11
```

Entries stay on their exact tiers (`[√2, 1/3] * 3`). Booleans, strings, and other
collections are typed errors, as are the empty tensor `[]`, shape mismatches, and an
index that is not an exact integer within range.[^tensor-index] Tensors compare with the
binding rule's check: same shape and equal entries. `\len(t)` is the outer length,
`\shape(t)` the shape as a vector, `\transpose(t)` the prelude spelling of `t'`.

Folds bind over a tensor's outer slices: `\sum(x=[1, 2, 3]) x^2` is `14`, and
`\sum(r=m) r` adds the rows.

`\contract` is an infix operator, never a name: it cannot bind or be aliased, and stands as
a value only as `(\contract)`, `(@)` or a whole call argument (`## Operator values`).

[^tensor-index]: A `[` trailer attaches only to name-ish heads (a name, a call, another
    index, a transpose), so `[1, 2][1]` is not an index: it juxtaposes two tensors and fails
    on the shape mismatch. A name holding a number followed by `[...]` multiplies, matching
    the call rule (`k = 3; k[1, 2]` is `[3, 6]`); any other head is `` `…` is not indexable ``.
    Whitespace is not significant, so `v [1]` also indexes.

## Arrays

`⟨...⟩`, `#[...]`, and `\arr(...)` are three spellings of one ordered container. Elements
are any values — numbers, strings, booleans, tensors, functions, other arrays — and
lengths may differ.

```
a = ⟨1, [1, 2], "three", ⟨4, 5⟩⟩     -- = a = ⟨1, [1, 2], "three", ⟨4, 5⟩⟩
a[2]      ->  = [1, 2]               a[4][1]  ->  = 4
\len(a)   ->  = 4                     ⟨⟩       ->  = ⟨⟩
\sum(x=⟨1, 2, 3⟩) x^2  ->  = 14
```

An array indexes with one 1-based exact-integer subscript (chain `a[i][j]` for nested
arrays) and folds bind over its elements in order. It has no algebra: every arithmetic
operator, comparison, and transpose on an array is a typed error. The binding rule's check
compares arrays by length and elements in order. Literal heads do not index (`⟨1, 2⟩[1]`
juxtaposes and fails), like tensor literals. `\arr` is reserved: it cannot be bound, and
takes positional values only.

## Sets

`{...}` builds an unordered set without duplicates. Elements are any values; two elements
are duplicates when the binding rule's check would call them equal.

```
{3, 1, 3, 2}                 ->  = {3, 1, 2}      -- first-seen order
{1, 2, 3} ∪ {3, 4}           ->  = {1, 2, 3, 4}
{1, 2, 3} \cap {2, 3, 4}     ->  = {2, 3}
{1, 2, 3} ∖ {2}              ->  = {1, 3}
2 ∈ {1, 2, 3}                ->  = true
{1, 2} ⊆ {1, 2, 3}           ->  = true
```

| Unicode | ASCII | Meaning | Level |
|---|---|---|---|
| `a ∪ b` | `a \cup b` | union | `+ -` |
| `a ∖ b` | `a \setminus b` | difference | `+ -` |
| `a ∩ b` | `a \cap b` | intersection | `* /` |
| `x ∈ s` | `x \in s` | membership, a boolean | comparison |
| `x ∉ s` | `x \notin s` | non-membership, a boolean | comparison |
| `a ⊆ b` | `a \subseteq b` | subset, a boolean | comparison |
| `a ⊂ b` | `a \subset b` | proper subset | comparison |
| `a ⊇ b` `a ⊃ b` | `a \supseteq b` `a \supset b` | superset, proper superset | comparison |

Every operator is infix. `∪ ∖ ∩ ⊆ ⊂ ⊇ ⊃` need sets on both sides; `∈` and `∉` take a set, an
array (element equality), or a range (a term of the progression, so `5 ∈ (1,3..9)`) on the
right; the range reads unparenthesized (`3 ∈ 1..5`), though `..` stays looser than every other comparison. `∅` / `\emptyset` is
the empty set. Anything else is a typed error, as are arithmetic, ordering, and indexing on a set. The
`\`-names `cup cap setminus in subseteq` and `notin subset supseteq supset neq approx` are operators, never names: they cannot bind or be aliased, and stand as a
value only as `(\cup)` or a whole call argument (`## Operator values`).

Sets display in first-seen order and compare regardless of it: `{1, 2} = {2, 1}` is
`true`. Sets nest (`{{1, 2}, {2, 1}}` is `{{1, 2}}`) and hold tensors, arrays, strings,
and functions. A `NaN` never equals itself, so `{\nan, \nan}` keeps both.
`\len(s)` is the size and folds bind over the elements. Building a set compares
elements pairwise.[^set-cost]

[^set-cost]: Quadratic in the number of elements; see
    [Known limitations](language.md#known-limitations-not-bugs).

## Composition and partial application

`f ∘ g` (ASCII `f \circ g`) is the function that applies `g`, then `f` to the result. It is
an infix operator at the `*` level, so `\circ` cannot bind or be aliased.
A `·` (or `⋅`, `_`) as a whole call argument leaves a hole: the call becomes a function of its holes,
filled left to right.

```
s(x) = x^2;  t(x) = x + 1;  f(a, b) = a - b
(s ∘ t)(2)              ->  = 9              -- s(t(2))
g = f(10, ·)            ->  g = <fn f(10, ·)>
g(3)                    ->  = 7
f(·, ·)(10, 3)          ->  = 7
\py("pow")(·, 2)(5)     ->  = 25
(f(·, 1) ∘ f(·, 1))(5)  ->  = 3
```

| Rule | Detail |
|---|---|
| Composition operands | Both sides are callable (user, lambda, prelude, Python, composed, partial); otherwise a typed error |
| Composition arity | `g` takes the arguments; `f` receives its single result |
| Partial head | Must be callable — no product fallback; a user function's arity is checked when the partial is built |
| Holes | Only as a whole positional argument; `f(· + 1)` and `f(x=·)` are parse errors, as is `·` in `\py`, `\arr`, `\eval` |
| Keyword arguments | Fixed at partial time for Python callables; user functions take none |

Both forms are values: they bind, pass, display (`<fn s ∘ t>`, `<fn f(10, ·)>`), and
compare by identity. A range is an ordinary argument: `\map(f, 1..3)`.

## Higher-order functions

`\map`, `\filter`, and `\fold` are prelude functions over ranges and collections. Tensors
iterate by outer slice, like folds.

```
\map(s, [1, 2, 3])                  ->  = [1, 4, 9]
\map(s, {1, -1, 2})                 ->  = {1, 4}
\filter(\fn(x) x > 1, ⟨1, 2, 3⟩)    ->  = ⟨2, 3⟩
\fold(\fn(a, b) a + b, ⟨1, 2, 3⟩)   ->  = 6
\fold(\fn(a, b) a + b, ⟨⟩, 10)      ->  = 10
```

| Call | Result |
|---|---|
| `\map(f, xs)` | `f` on each element, in the kind of `xs`: tensor → tensor (results must restack), array → array, set → set (deduplicated), finite range → array |
| `\filter(p, xs)` | the elements where `p` returns a boolean `true`, in the kind of `xs`; a non-boolean is a typed error, and a tensor with nothing kept is an error (no empty tensor) |
| `\fold(f, xs)` | left fold `f(f(x1, x2), x3)…`; an empty collection is an error |
| `\fold(f, xs, init)` | left fold starting from `init`; an empty collection returns `init` |
| `\scan(f, xs)` | running left fold `x1, f(x1, x2), …`, in the kind of `xs`; an empty collection is an error |
| `\scan(f, xs, init)` | running fold `f(init, x1), f(f(init, x1), x2), …`; an empty collection gives an empty result |
| `\take(n, xs)` | the first `n` elements (fewer if there are fewer), in the kind of `xs` like `\map`; `n` is an exact integer, 0 or more |

Operators pass as values: `\fold(+, xs)` (`## Operator values`).

### Infinite ranges and lazy sequences

`\map`, `\filter`, and `\scan` over an infinite range (`1..`) or another lazy sequence
return a **lazy sequence**, which runs nothing until something consumes it: `\take`, or a fold
binder.

```
s(x) = x^2
q = \map(s, 1..)                                 ->  q = <seq \map(s, 1..)>
\take(3, q)                                      ->  = ⟨1, 4, 9⟩
\take(2, \filter(\fn(x) x > 5, q))              ->  = ⟨9, 16⟩
\take(4, \scan(+, 1..))                          ->  = ⟨1, 3, 6, 10⟩
\fold(+, \map(\fn(x) 1/x^2, 1..))               ->  = 1.6449…  -- like the \sum binder
\sum(k=\map(\fn(x) 1/x^2, 1..)) k                ->  = 1.6449…  -- converges like Σ over 1..
```

| Rule | Detail |
|---|---|
| Re-iteration | A sequence re-runs from the start each time it is consumed; it caches nothing |
| Errors | A failing element (or a `\filter` predicate returning a non-boolean) errors when it is reached, not when the sequence is built |
| Folds | `\sum`/`\prod` binders and `\fold` consume a sequence with the infinite-range convergence rule (`## Special forms`): float tier, plateau exit, error at 2,000,000 elements; only `\fold(+, …)` gets the sum tail estimate. `\len` rejects it |
| `\filter` cap | A predicate that stops matching gives up after 2,000,000 elements in a row with a typed error |
| Values | They bind, pass, and compare by identity; `\take` on a finite range gives an array |

## Operator values

An operator is a function value in two positions: as a **whole call argument**
(`\fold(+, xs)`, like `·`) and **parenthesized** anywhere (`(+)`).

```
\fold(+, 1..10)                ->  = 55
\map(√, [4, 9])                ->  = [2, 3]
g = (+)                        ->  g = <fn +>
g(1, 2)                        ->  = 3
\filter((<)(·, 3), ⟨1, 5, 2⟩)  ->  = ⟨1, 2⟩
((-) ∘ s)(2)                   ->  = -4          -- with s(x) = x^2
```

| Operator | Arguments | Meaning |
|---|---|---|
| `+ * / ^` | 2 | arithmetic |
| `%` `\mod` | 2 | floored modulo: the result takes the divisor's sign |
| `-` | 1 or 2 | negate, or subtract |
| `@` `\contract` | 2 | contraction — the same as infix `@` |
| `∘` `\circ` | 2 | composition |
| `∪ ∩ ∖` `\cup \cap \setminus` | 2 | set operations |
| `< > <= >= ≤ ≥` | 2 | ordering, returns a boolean |
| `≠` `\neq` | 2 | not equal: the negated `=` check |
| `≈` `\approx` | 2 | approximately equal, numbers only |
| `∈` `∉` `\in` `\notin` | 2 | `x ∈ s`: the element, then the set, array or range |
| `⊆` `⊂` `⊇` `⊃` `\subseteq` `\subset` `\supseteq` `\supset` | 2 | subset relations, return booleans |
| `!` `‼` | 1 | factorial, double factorial |
| `√` | 1 | `\sqrt` itself |
| `∛` `∜` | 1 | the partials `\root(·, 3)` and `\root(·, 4)` |

| Rule | Detail |
|---|---|
| Values | Callable like any function: they bind, pass, compose, and take holes (`(+)(·, 1)`) |
| Identity | Each operator is one value, so `(∪) = (\cup)` after `g = (∪)` checks `true` |
| Arguments | Positional only; the wrong count is a typed error at the call |
| Display | `<fn +>`; quotes print `(+)` |
| Elsewhere | A bare operator is a parse error: `g = +`, `f(+ 1)` |

### Sections

`(+ 1)` and `(2 ^)` fix one operand of a parenthesized operator: shorthand for the hole
forms `(+)(·, 1)` and `(^)(2, ·)`.

```
(+ 1)(2)                 ->  = 3
(2 ^)(3)                 ->  = 8
\map((* 2), [1, 2, 3])   ->  = [2, 4, 6]
\filter((< 3), ⟨1, 5, 2⟩) ->  = ⟨1, 2⟩
(+ 1*2)(5)               ->  = 7          -- operand `1*2`
((1 + 2) *)(4)           ->  = 12
```

| Rule | Detail |
|---|---|
| Operand | Reads as the operator's own right-hand side would, so `(+ 1*2)` fixes `1*2` and `(1 * 2 +)` fixes `1*2`; a looser operand is a parse error asking for parentheses: `(* 1 + 2)`, `(1 + 2 *)`, `(-2 ^)` |
| Minus | `(- 1)` is negation, so a right section for `-` is `(+ -1)` or `(-)(·, 1)`; `(1 -)` is a section |
| Radical | `(√ x)`, `(∛ x)` are calls, not sections; postfix `!` `‼` have none either |
| Quotes | A section is the hole form: `\expr((+ 1))` prints `\expr((+)(·, 1))` |


## Conditionals: the ternary

The ternary `condition ? then : otherwise` is the one conditional. It is lazy —
only the selected branch evaluates — and the condition must be a boolean. It
binds looser than every other expression
operator (precedence table, level 1) and nests right-associatively through its
branches; a nested middle closes at the first free `:`. A missing `:` at end of
input offers the REPL continuation prompt. There is no two-branch form — a
conditional that could do nothing would have no value to give, so a ternary is an
expression that always needs its else. Branches may be any expression, including
parenthesized statement groups (the multi-statement branch — `## Groups`):

```
x > 0 ? 1 : -1                  ->  = 1
\sum(i=1..10) i > 5 ? i : 0     ->  = 40
5 > 3 ? 1..3 : 4..6             ->  = <range 1..3>
a > 0 ? 1 : b > 0 ? 2 : 3       -- a ? 1 : (b ? 2 : 3)
1 < 2 ? (x = 4
         x + 1) : 99            ->  = 5    -- a group is the multi-statement branch
```

Comparisons `<`, `>`, `<=`, and `>=` return booleans, displayed as `true` or `false`.
Booleans are valid values and conditions but are not numeric operands. There is no
numeric truthiness: a number is never a condition — `0 ? 1 : 2` is a typed error,
not a silent pick, and the only conditions are comparisons and `\true`/`\false`.

## Lambdas: anonymous functions

```
lambda ::= ("\λ" | "\fn") "(" params? ")" expr ;
```

A lambda is exactly a function definition without the name — `\λ(x) x + 1` (ASCII
spelling `\fn(x) x + 1`; the sigil rule — every unicode form has an ASCII one). It is
a first-class callable value: eager, fixed arity, and its body evaluates in a fresh
frame over a closure of the defining scope. Reads fall through to the enclosing
scopes; assignments stay call-local. There is no self-name to recurse through —
recursion goes through named defs or a fixpoint combinator (the Z form works eagerly).
Lambdas display as `<λ(x)>` and compare by identity like other callables; they take
positional arguments only, and a parameter named like a prelude constant is rejected
at evaluation, exactly as for defs — with the one exception of `i` (see
`## Assignment semantics`).

**Body extent** follows the fold/limit rule: the body extends greedily over the rest
of the current expression, up to the enclosing delimiter (`,` `)` `;`, end of
input — a line break inside the expression continues it). One-statement lambdas
therefore nest right-associatively with no delimiters
at all, and a parenthesized group gives an explicit extent and multiple statements:

```
\fn(x) x^2                             -- a one-statement body needs no group
\fn(n) \fn(f) \fn(x) f(n(f)(x))        -- greedy nesting: each body is the rest
\fn(f) (
g = \fn(x) f(f(x))
g
)                                      -- explicit extent, two statements
```

**Application**: a parenthesized lambda is a name-ish head, so a trailer applies it —
`(\fn(x) x)(5)` is `5`. Unparenthesized, the greedy body has already consumed any
trailer (`\fn(x) x(5)` is a lambda whose body is the call/product `x(5)`). Zero-
argument lambdas are legal, matching `f()` legality; `\fn(a, b) a` takes two. A bare
`\fn` without the parameter-list paren is an ordinary unbound name and reports a
usage message at evaluation; `\fn(x) = 3` is a parse error (a lambda takes a body,
not `=` — name it with `f(x) = body`).

```
\inc = \fn(x) x + 1                    ->  \inc = <λ(x)>
\inc(4)                                ->  = 5
(\fn(x) x)(5)                          ->  = 5
\mk = \fn(n) \fn(x) x + n              -- closures capture the defining scope
\five = \mk(5); \five(1)               ->  = 6

\zero = \fn(f) \fn(x) x                -- Church numerals run as ordinary code
\succ = \fn(n) \fn(f) \fn(x) f(n(f)(x))
\two = \plus(\succ(\zero))(\succ(\zero))
\two(\fn(v) v + 1)(0)                  ->  = 2
```

## Special forms: folds and limits

`\sum`, `\prod`, and `\lim` are
**special forms**, not functions: their first parenthesized argument is a binding — an
identifier, `=`, then the bound expression — which general expressions cannot contain.
The parser recognizes the `(ident =` shape after one of these heads; any other
parenthesized use is a parse-time usage error naming the expected binder form, and
without a paren the head is simply an unbound name at evaluation. The unicode
spellings `Σ` and `Π` are name aliases of `\sum` and `\prod` (see `## Name aliases`)
— they normalize to the canonical heads before the special-form table is consulted,
and a user `\alias` onto those names gets the same treatment for free.

```
\sum(i=1..10) i^2            ->  = 385          -- fold + over the range
\prod(j=1..5) j              ->  = 120          -- fold *
Σ(k=1,3..7) k                ->  = 16           -- stepped ranges bind too
\lim(x=0) x/x                ->  = 1.0          -- numeric limit; anchor never evaluated
```

**Body extent**: the body extends greedily over the rest of the current expression, up to
the enclosing delimiter (`,` `)` `;` or end of input). Parenthesize to end it earlier:
`\sum(i=1..2) (i + 1) * 2` folds `i + 1`, then doubles the total, while wrapping the whole
fold — `(\sum(i=1..2) i + 1) * 2` — adds 1 to the total and then doubles it.

**Scoping** mirrors function parameters exactly: each term or probe evaluates in a fresh
frame holding only the loop variable. Reads of other names fall through to the enclosing
scope, assignments stay local to the iteration, and the loop variable never leaks into the
outer environment.

**Finite vs infinite**: folding over a finite range accumulates exactly at the lowest
tier that stays exact (`\sum(i=1..10) i^2` is an exact integer all the way through). A
lazy infinite range switches to approximate iteration: partial sums/products advance in
the float tier until consecutive values stabilize within `CONVERGENCE_TOLERANCE`
(relatively scaled; `docs/numerics.md`), hard-capped at `MAX_TERMS` — while infinite
sums additionally stop early on a confirmed tail estimate (monotone-decay or Leibniz
shapes with a bounded claimed error). The cap produces a typed error rather
than returning a possibly-misleading partial result; so does any non-finite partial.

**Limits are numeric only** — this is a calculator, not a CAS. `\lim(x=a) body` probes
both sides with geometrically shrinking steps and never binds `x` to `a` itself. Each
side must stabilize within `MAX_PROBES`; sides stabilizing further than twice the
(relatively scaled) tolerance apart report `` limit does not exist: left and right estimates disagree ``
(jump discontinuities like `\lim(x=0) x < 0 ? -1 : 1`). A pole (`\lim(x=0) 1/x`)
never stabilizes and reports probe exhaustion instead. Cancellation-prone spellings of
removable singularities (e.g. `(x^2 - 1)/(x - 1)` near 1) lose float precision as steps
shrink and may fail to stabilize — write them simplified.

## String literals

Strings are **values**. They bind (`s = "data"`), display quoted and round-trippable
(`= "a\"b"` — the `\"`/`\\` the lexer decodes is exactly what display emits), pass through
`\py` boundaries as native `str`, and appear anywhere an expression does:

- `+` **concatenates** two strings: `"data" + ".csv"`. It is the *only* string operator —
  there is no mixed arithmetic: `"a" + 1` fails with the usual typed "strings are not
  numbers", as do `- * / ^`, unary `-`, and the ordering comparisons `< <= > >=`.
- A string is an ordinary atom, so it may be a whole call argument (the `\py("dotted.path")`
  case, positional or as a kwarg value `\mode="r"`) — or an operand: `\py(n + ".sqrt")`
  composes a path from a bound name.
- A string **alone as a statement** still echoes nothing — the comment-like literate note:

  ```
  > "chapter 3: convergence"
  > 1 + 1
  < = 2
  ```

- Strings compare equal only to strings, and only through the binding rule's check
  (`s = "a"; s = "a"` echoes `true`): the language has no `==` operator at all —
  `==` lexes as two `=` and cannot parse — so there is no string equality *expression*.

When a Python function hands a `str` back across the boundary it is a plain ad string
value: printable (`= "hello"`), bindable, concatenable. See docs/numerics.md for the full
conversion matrix.

## Modules and imports

Two statement-level forms, two targets — a module value does not exist in the value
model, and dotted attribute access (`math.sqrt` on a bound module) is not in the
grammar, so both forms bind *members* rather than namespaces. An import is a statement:
it binds names, produces no output, and has no value (a parenthesized sequence group
cannot hold one; in expression position the head is an unbound name with a usage
message, the `\py` pattern).

`\import("lib")` reads an **ad source file** (`lib.ad`; a path already ending in `.ad`
is taken literally) and binds its top-level names into the importing environment — all
of them, or only the members after the colon (`\import("lib": f, \fact)`). Module code
is ordinary ad source: single-character or `\`-sigiled names, functions, constants.

`\pyimport("math": \sqrt, \tau)` binds members of a **Python module**. Member selection
is mandatory — there is nothing to bind without names. Callables bind as callables (the
`\py` rule); every other member converts through the interop matrix or fails at the
import's span, so `tau` binds as a number while a dict member is a typed rejection.

Shared rules:

- **Resolution**: `\import` searches the importing file's directory first, then the
  working directory (REPL: working directory). A name that resolves as a Python module
  instead of a file gets an error hinting at `\pyimport`. `\pyimport` resolves dotted
  paths exactly like `\py`.
- **Once per session**: each ad file evaluates exactly once per session, in a fresh
  root environment of its own; the module's bindings are cached and re-imports re-copy
  the cached values without re-evaluating. Evaluating a module twice (e.g. two
  sessions) yields fresh, unrelated values.
- **Closures**: imported functions keep the module's environment as their closure —
  reads of module globals stay live through the closure — while the copied values are
  snapshots bound into the importer.
- **Cycles**: importing a file that is already being evaluated (directly or through a
  chain) is a typed error naming the chain.
- **Binding rules**: everything validates before anything binds. A member missing from
  the module, a protected prelude name, or a name already bound to a different value is
  a typed error; a name already bound to the *identical* cached value is a silent
  no-op (re-import). Imported names land as ordinary bindings — not protected, and a
  repeat `=` compares rather than overwrites.

```
\import("lib")                 -- bind everything lib.ad defines at the top level
\import("lib": f, \fact)       -- bind only f and \fact
\pyimport("math": \hypot)      -- bind math.hypot as \hypot
\hypot(3, 4)                   ->  = 5.0
```

## The `\` sigil

A name is one letter, optionally subscripted (`x₁`, `xᵢ`, `x_1`). Any language-defined name longer than one character
is `\`-prefixed, regardless of script — `\pi`, `\sum`, `\sin`, `\solve`, `\map`, `\graph`. Where
a `\`-name has a single-character unicode form, they are the same name (`\pi` ≡ `π` — the
name-alias mechanism, `## Name aliases`); where
there is no unicode form, the `\` spelling is the only one (`\sin`, `\lim`, `\solve`, ...).

The names are chosen to match their LaTeX command where one exists, so `ad` source reads like
the ASCII you'd already type to write the same expression in LaTeX — this is a naming
convention, not a claim that `ad` parses TeX. The built-ins bound today are listed under
`## The prelude`; `docs/language.md` has the fuller picture and `README.md` the
framing.

## Name aliases

One name may own several spellings: `Σ` IS `\sum`, `π` IS `\pi` — one binding, two
ways to write it, not two names that happen to hold one value. The mechanism is a
session alias map (short spelling → canonical name) that the parser consults
everywhere a name is consumed, seeded with:

| spelling | canonical |
|---|---|
| `Σ` | `\sum` |
| `Π` | `\prod` |
| `π` | `\pi` |

`\alias` extends the map for the rest of the session:

```
\alias \sum, σ        -- σ now reads (and checks against) as \sum
\alias \alpha, α, ϵ   -- several short spellings may share one canonical name
```

`\dual` declares the pair and defines the canonical name in one statement — the
ordinary definition forms with a second spelling attached:

```
\dual \alpha, α = 3.14               -- binds \alpha; echoes α = 3.14
\dual \fact, φ(n) = n*\fact(n-1)     -- echoes φ = <fn φ(n)>
```

Rules:

- **Canonical first**: the first spelling is the canonical name (either name form);
  the rest are single-character aliases — one character that lexes as an identifier,
  i.e. a letter. Definitions bind the canonical name only, and the short spelling
  reads (and checks against, via the statement `=` rule) as the very same name from
  its declaration on. The radical `√` is not a name (it is not a letter) and so is
  outside the alias mechanism entirely — it is a fixed operator spelling.
- **Parse-time, declare-before-use**: declarations take effect with the next
  statement in the same unit; a use parsed before the declaration reads the raw
  spelling, and no alias declaration renames it retroactively.
- **Top-level only**: `\alias` and `\dual` are directives, not expressions — they
  cannot appear inside a function body or parenthesized group (their effect is
  parse-time, and a body's declarations would fire whether or not it ever runs).
- **Protected names**: a spelling that names a prelude value cannot be repurposed as an
  alias (`\alias x, e` errors). Aliasing *onto* a canonical prelude
  name is allowed — `\alias \pi, ϖ` gives `ϖ` to the constant — and protection still
  holds, since every use of the short spelling becomes a use of the canonical name.
- **Session scope**: the REPL threads the map across inputs alongside the environment;
  scripts and `\import`ed modules parse with the seed
  alone — they never inherit or export declarations. The driver API threads the map
  explicitly (`parse_program`/`compile_source` take `aliases=`).
- **Source spelling**: each name-bearing occurrence retains the spelling written at
  that occurrence as non-semantic metadata. Canonical names still determine identity,
  lookup, and protection; diagnostics and fresh declaration echoes use the written
  spelling. For example, `\dual \alpha, α = 3.14` echoes `α = 3.14` while storing
  `\alpha` in the environment.
- **Atomic registration**: declarations merge into the session map only after the
  parse of their input unit succeeds; a failed or cancelled line declares nothing.
  An evaluation failure after a successful parse may leave a declaration registered.

Bare `\alias`/`\dual` heads (not followed by a name) stay ordinary unbound names and
report their usage at evaluation, like `\py`.

## Assignment semantics

One rule everywhere (`x = e`, any statement context):

- `x` protected (a prelude name, except `i`) → error naming the written spelling, e.g.
  `` `π` is protected ``
- `x` unbound in the current frame → **bind** it, prints `x = v`
- `x` bound in the current frame → **compare** current value to `v`, prints `true` / `false`

The comparison is value-based on the numeric tower, not type-checked: `x = 1; x = 1.0`
echoes `true`, `0.5` and `1/2` compare `true`, `"a" = 1` echoes `false` (mixed kinds
simply are not equal). There is no reassignment operator. A binding is made once by the
first `=` and can never be overwritten, only compared against. `\let name = expr` is
the explicit fresh-only spelling: it binds a new current-frame name, echoes the same
`name = value` line, and errors when that name is already bound in the current frame.
To iterate on a value, bind a fresh name or compute inside a function, where every call
starts from a fresh frame.

**The `i` exception**: the imaginary unit's spelling is the conventional loop-binder
name, so `i` is the one prelude name a binding may shadow — `i = 5` binds a fresh `i`,
`\sum(i=1..3) i` uses it as the binder, `f(i) = i*i` takes it as a parameter, exactly
like any other identifier. Both spellings read the one binding, so a shadow covers `i`
and `\i` alike, and the shadow lifts when the scope ends (the unit is reachable inside
as `\complex(0, 1)`). It is an ordinary identifier clash handled by the ordinary
frame rules — not a hole in protection: `π` and every other prelude name stay
unshadowable, and `\alias` still refuses to repurpose the `i` spelling.

Frame locality: reads walk the chain (locals → enclosing → globals → prelude), but
binds and compares are frame-local. Inside a body, `y = e` shadows a global `y` with a
fresh local (it never touches the global), and a repeat `y = e` compares the local.
Function definitions are the one exception to bind-or-check: `f(x) = body` on a bound
or protected name is an error — definitions are declarations, and functions compare by
identity, so a check would be meaningless. The top-level `\let f(x) = body` form has
the same fresh-only behavior. Note that inside an argument list, `name=value` is a
keyword argument and never assigns.

Statement groups flatten: a top-level `(a; b)` becomes plain top-level statements, each
with its own echo line — the parentheses do not create a scope, so a group cannot
overwrite a global either (its `=` compares). Expression-position groups (function
bodies, ternary branch groups) run the same rule in the frame they evaluate in.

## The prelude

There are no user-declared constants: every binding is immutable by the assignment rule
itself, while `\let` is only the explicit fresh-binding spelling. Built-in names live
in a prelude scope protected by the same mechanism:

| spelling | value |
|---|---|
| `π` / `\pi` | the symbolic real π — exact; displays `3.14159265358979...` (docs/numerics.md) |
| `e` | the symbolic real e — exact; displays `2.71828182845905...` |
| `i` / `\i` | the imaginary unit — an exact complex value (`i` displays as `i`); the one prelude name a binding may shadow (see `## Assignment semantics`) |
| `\inf` / `\nan` | the non-finite floats `Inf` / `NaN` — float tier only; the exact tiers have neither (`1/0` is a typed error). IEEE semantics, docs/numerics.md |
| `\true` / `\false` | the booleans — comparisons return them, arithmetic rejects them |
| `\sin` `\cos` `\tan` `\ln` `\sqrt` | seam-native builtins: exact arguments go through the symbolic closed-form tier (`\sqrt(2)` stays `√2`, `\sin(π/3)` is `√3/2`, `\sqrt(-2)` is `√2·i`, `\ln(-1)` is `π·i`); algebraic `√` arguments through the algebraic tier (`\sqrt(2^(1/3))` is `2^(1/6)`); anything finite the lower tiers cannot hold through the RRA tier (`\sin(1)` stays exact, complex results included); everything else falls to the `math.*` float tier. Display as `<fn \sqrt(x)>` |
| `\isnan` / `\isinf` / `\isfinite` | test the float tier's non-finite states; exact-tier values are finite, so `\isnan` and `\isinf` are false and `\isfinite` is true. Non-numeric arguments are typed errors. Display as `<fn \isnan(x)>`, `<fn \isinf(x)>`, and `<fn \isfinite(x)>` |
| `\complex` | builds a complex value from two real components: `\complex(2, 3)` is `2+3i`, a vanishing imaginary part collapses to the real; float components read as their exact decimals |
| `\re` / `\im` | project the real or imaginary side (`\re(2+3i)` is `2`, `\im(π·i)` is `π`); a float's imaginary side is `0.0` |
| `\root` | `\root(x, n)`: the exact positive integer `n`th root, `x^(1/n)` on the numeric seam; `∛x` is `\root(x, 3)`. Displays as `<fn \root(x)>` |
| `\emptyset` / `∅` | the empty set, a protected constant |
| `\map` / `\filter` / `\fold` / `\scan` / `\take` | higher-order functions over collections (`## Higher-order functions`). Display as `<fn \map(x)>` etc. |
| `\len` / `\shape` / `\transpose` | collection length, tensor shape (a vector), and tensor transpose. Display as `<fn \len(x)>` etc. |
| `\prec` | the RRA display-precision setting: `\prec(5)` shows `π + 1` as `4.1416...` — an exact integer 1..1000, returns the new value, protected like every prelude name. Displays as `<fn \prec(x)>` |

Prelude names are **protected everywhere**: `π = 3`, a parameter named `π`, a local
`π = ...`, or a `\sum(π=...)` binder are all redefinition errors (`` `π` is protected ``,
naming the spelling written at the failing occurrence), never shadows — except `i`,
the one shadowable prelude name (above).
Unicode and ASCII spellings are the same value — `π` and `\pi` are one
name, not two, and `i` and `\i` are one name reached as a bare identifier and as a
`\`-reference. The function builtins replaced the original float-tier `math.*` aliases
in place: binding names unchanged, but exact closed forms stay exact
(`√2 * √2` collapses back to the integer `2`); a result with no recognized closed form
stays exact in the algebraic or RRA tier (`π + 1` is `4.14159265358979...`), and the float tier keeps
`math.*`'s own behavior for float arguments (`\sqrt(2.)` is `1.4142135623730951`).
`√` is the prefix-operator spelling of `\sqrt(...)` — same evaluation, no separate
name. Exact-tier domain failures are typed errors (`\ln(0)`,
`\tan(π/2)`); the float tier keeps `math.*`'s own raising (`\sqrt(-1.0)` →
`ValueError`, wrapped and spanned).

## Ranges

Ranges are lazy arithmetic progressions. Finite ranges include their endpoint when the
step reaches it and stop before crossing it; infinite ranges never materialize their
contents. The two-element form infers the step as `c - a`, and a zero step is an error.

```
1..4       -> <range 1..4>
1..         -> <range 1.. (lazy, infinite)>
1,3..10    -> <range 1,3..10>       -- 1, 3, 5, 7, 9
10,8..1    -> <range 10,8..1>       -- 10, 8, 6, 4, 2
```

**In lists, `,` separates items.** Inside call arguments, tensor, array, and set literals,
and index brackets, a comma never starts a stepped range: `⟨1, 3..9⟩` has two items and
`\map(f, 1..3)` passes `f` and the range. Parenthesize a stepped range there:
`\map(f, (1,3..9))`. Everywhere else — top level, groups, quotes, and fold binders
(`Σ(k=1,3..7) k`, also inside a list) — `a,b..c` is stepped.

Ranges can be assigned and passed through the runtime; folds bind them directly
(`\sum(i=1..10) …`, `Σ(i=1..) …` — see `## Special forms`).

A callable binds like any other value (`s = \py("math.sqrt")` prints `s = <py math.sqrt>`);
a call returning a string binds like any value too (see `## String literals`). Two
non-numeric values never compare equal unless identical — strings by content.

## Deferred

Logical operators ([#80](https://todo.sr.ht/~takeiteasy/adhoc/80)), symbolic algebra, graphing.
`==` and `!=` do not exist: `≠` / `\neq` is the inequality operator, and the binding
rule's check is the only equality, with tier-aware semantics: exact for
the rational, symbolic and algebraic tiers (minimal-polynomial fallback included)
and the Richardson–Fitch heuristic for any RRA-involved pair (docs/numerics.md).
User-declarable *operator* spellings ride the phase-4 custom
infix operators — `\alias` covers names only. Name aliases
and `\dual` are built today (see `## Name aliases`).
See `ROADMAP.md` and the tracker for the phase each lands in.
