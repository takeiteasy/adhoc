# Grammar

This reference covers supported syntax and evaluation rules. The parser
(`adhoc/parser.py`) follows the [formal grammar](grammar-ebnf.md). For a feature
overview, see the [language guide](language.md).

## Lexical rules

### Whitespace and comments

Whitespace separates tokens. A newline also separates complete statements. When
an operand is still required, parsing continues onto the next line: `1 +` followed
by `2` is one sum. This rule applies inside parentheses and argument lists.
Arguments on separate lines still need commas.

`--` starts a comment through the end of the line. Its ending newline remains a
statement separator.

### Number and string literals

| Spelling | Value |
|---|---|
| `3` | Exact integer |
| `0.5`, `12.34`, `.5` | Exact rational, read from the literal's digits |
| `1.` | Explicit float `1.0` |
| `5e-1`, `1.5e3`, `2e3` | Float |
| `2e` | Juxtaposition: `2 * e` |
| `1..10` | Integer, range operator, integer |

An exponent marker `e` or `E` requires a digit after its optional sign.
A dot outside a number starts the range operator. See [numerics](numerics.md).

Strings use double quotes and can span lines. Only four escapes decode:

| Escape | Character |
|---|---|
| `\"` | Quote |
| `\\` | Backslash |
| `\n` | Newline |
| `\t` | Tab |

Other backslash pairs are lexical errors. See [string literals](#string-literals)
for value operations.

### Identifiers and backslash names

A bare identifier is one ASCII or Unicode letter, optionally followed by a
subscript. `ab` is `a * b`; `x₁` is a name distinct from `x`.

| Form | Examples | Rule |
|---|---|---|
| Unicode subscript | `x₁`, `a₂₃`, `xᵢⱼ` | Digits `₀…₉` or supported subscript letters[^subscripts] |
| ASCII subscript | `x_1`, `x_ij`, `x_b` | Letter, `_`, then ASCII letters or digits |
| Backslash name | `\pi`, `\rel_tol`, `\my_var` | Letters and underscores; underscore cannot start the name |

ASCII and glyph subscripts identify the same name when every character has a
glyph. Other ASCII forms, such as `x_b` or `x_ib`, remain distinct names.
A subscript glyph without a preceding letter is an error.

`\atan2` is the exception permitting a final digit. Backslash names can refer to
built-ins or user bindings; an unbound name fails at evaluation. `\let` is a
statement keyword and cannot be bound.

`∅`, `∫` and `∂` are identifiers aliasing `\emptyset`, `\int` and `\diff`.
See [notation](notation.md) and [name aliases](#name-aliases).

### Superscripts, radicals and delimiters

| Form | Meaning |
|---|---|
| `²`, `⁻¹`, `ⁿ⁺¹`, `⁽ⁿ⁺¹⁾` | One superscript token; sugar for `^` followed by an expression |
| `ᵀ` | Transpose, equivalent to `'`; outside superscript runs |
| `√x` | Prefix spelling of `\sqrt(x)` |
| `∛x`, `∜x` | Prefix spellings of `\root(x, 3)` and `\root(x, 4)` |
| `!`, `‼`, `!!` | Postfix factorial and double factorial |
| `⌊ ⌋`, `⌈ ⌉`, `\| \|`, `‖ ‖` | [Delimited forms](#delimited-forms); `∥` also reads as `‖` |

A superscript run uses digits, letters, `⁺ ⁻ ⁽ ⁾` and must contain a digit or
letter. `√` is an operator token, so it cannot be bound, aliased or shadowed.
`!=` is a lexical error pointing to `≠`.

### Operators and punctuation

```text
↦ -> + - * / % @ × ⊗ ∘ ∠ ∪ ∩ ∖ ∈ ∉ ⊆ ⊂ ⊇ ⊃ ≠ ≈ ∧ ∨ ¬ → ↔ ^
< > <= >= ≤ ≥ = .. ( ) [ ] { } ⟨ ⟩ #[ ' ! ‼ , ? :
```

| Token | Use |
|---|---|
| `;` | Statement separator; tensor row separator inside `[...]` |
| `#[` | One array-opening token; a lone `#` is an error |
| `·`, `⋅`, `_` | Partial-application placeholder; `_` within a backslash name is a name character |
| Backtick | Expression or statement-sequence quote |
| `=` | Binding or check at statement start; equality in expressions |
| `==` | Congruence, with a required `(mod n)` or `(\mod n)` suffix |
| `? :` | Ternary conditional; `:` also separates an import's member list |
| `↦`, `->`, `\mapsto` | Lambda arrow; `\mapsto` is not a name |

An unused Unicode mathematical symbol (`Sm`) can be a custom operator glyph.
Existing lexical meanings, including congruence `≡` / `\equiv` / `==`, are reserved.
Declared punctuation operators use longest matching over `+ - * / ^ % @ < > & ~`; built-in spellings and runs
containing `--` or `->` are reserved. See [custom operators](operators.md).

The parser recognizes `\λ` and `\fn` as lambda heads when followed by a parameter
list. Other backslash names tokenize normally and require a binding at evaluation.

## Grammar (EBNF)

The [formal grammar](grammar-ebnf.md) lists the parser productions.
The rules below explain their semantics.

`\let` is a statement form. Its variable form is legal wherever a statement is legal;
its function form is top-level (including a group that flattens at top level). A bare
or misplaced `\let` is an error, and incomplete forms enter the REPL continuation path.

### Quotes and evaluation

| Form | Behavior |
|---|---|
| `\expr(x+1)` or `` `(x+1) `` | Quote an expression without evaluating |
| `\expr(x^2=4)` or `` `(x^2=4) `` | Quote an equation; `\solve` solves it and `\eval` returns equality |
| `\expr((x=1; x+1))` | Quote a statement sequence |
| `\expr((x+1;))` | Quote a single-statement sequence; trailing separator required |
| `\eval(q, x=3)` | Evaluate a quote or nested array of quotes with local named bindings |
| `\body(f)` | Return a user function or lambda's body as an expression value |
| `\reduce(q)` | Beta-reduce an expression quote |

Evaluation bindings are computed in the caller's scope before the quote runs.
Other names resolve in the evaluation scope. Bindings stay local and cannot
shadow protected names except `i`. Expression values print as parseable
`\expr(...)` text; binding checks compare AST structure and canonical names.
Built-ins and Python callables have no reflected body.

An equation occupies the whole expression quote and has one outer `=`. Enclosing
parentheses are optional: `\expr((x=4))` is an equation quote. Evaluating it
compares both sides without binding `x`. A separator marks a statement sequence:
`\expr((x=4;))` quotes an assignment. The outer `=` of an equation quote
separates full expressions: `\expr(\true ∧ \false = \false)` compares
`\true ∧ \false` with `\false`. Nested equality expressions use ordinary
[comparison precedence](#equality-expressions).

Reduction leaves arithmetic as syntax and named functions as calls. Statement
quotes are rejected.[^reduction]

### Separators and binders

A statement separator is a newline run or a single `;`. Blank lines and one
trailing separator are allowed; `;;` is an error. This applies at top level and
inside groups.

[Special forms](#special-forms-folds-and-limits) sit in postfix position but bind
a name in their first parentheses rather than accepting an ordinary argument.
Their productions are in the [formal grammar](grammar-ebnf.md#special-forms).

## Precedence table

Loosest to tightest:

| Level | Operators | Associativity |
|---|---|---|
| 1 | `? :` (ternary) | right |
| 2 | `=` (binding/check) | statement level only; RHS is an expression |
| 3 | `↔` | non-associative |
| 4 | `→` | right |
| 5 | `∨` | left |
| 6 | `∧` | left |
| 7 | `¬` | prefix |
| 8 | `..` (range) | non-associative |
| 9 | `=` `<` `>` `<=` `>=` `≤` `≥` `≠` `≈` `∈` `∉` `⊆` `⊂` `⊇` `⊃` | non-associative |
| 10 | `∠` (polar form) | non-associative |
| 11 | `+` `-` (binary), `∪` `∖` | left |
| 12 | `*` `/` `@` `×` `⊗` `%`, `∩`, `∘` | left |
| 13 | juxtaposition (implicit `*`) | left |
| 14 | unary `-`, `√` `∛` `∜` | prefix |
| 15 | `^` | right |
| 16 | postfix `(…)` application, `[…]` index, `'` transpose or derivative, `!` `‼` factorial, superscript `²` | left |

Juxtaposition binds tighter than `*`/`/` but looser than `^`, matching how the expression
reads on paper:

```
1/2x     ->  1 / (2*x)      -- not (1/2)*x
2x^2     ->  2 * (x^2)      -- ^ still tightest
-2^2     ->  -(2^2) = -4    -- unary minus is looser than ^
2^-1     ->  1/2            -- exact rational, displays as a fraction ([numerics](numerics.md))
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

Glyphs and their ASCII spellings are in [notation](notation.md).

A parenthesized composition is a call head: `(f ∘ g)(x)` applies. Unparenthesized,
`f ∘ g(x)` composes `f` with the result of `g(x)`.

Juxtaposition recognizes the start of another factor; a declared custom operator
ends the factor sequence and parses as infix.[^atom-starters]

## Delimited forms

Each delimited form is an atom that rewrites to a prelude call over the whole bracketed span.

| Form | Call |
|---|---|
| `⌊x⌋` | `\floor(x)` |
| `⌈x⌉` | `\ceil(x)` |
| `\|x\|` | `\abs(x)` |
| `‖x‖` `∥x∥` | `\norm(x)` |

`|x|` and `\abs(x)` return scalar magnitude or complex modulus. For a square
matrix they return its signed determinant; other tensor shapes are errors.
`‖x‖` and `∥x∥` return the norm.

```
|1 - |2 - 5||     ->  = 2
|2||3|            ->  = 6
|[1, 2; 3, 4]|   ->  = -2
2⌊3/2⌋            ->  = 2
‖[3, 4]‖          ->  = 5
```

Where an operand is expected, a bar opens a form. After an operand, a bar closes the
innermost open form of the same glyph, and opens a new factor when none is open, so
`|a||b|` is `|a|·|b|`. A different glyph always opens: `|a ‖b‖|` nests. Brackets, braces, call
arguments and groups start afresh, so `|f(2 |3|)|` reads the inner bars as a factor of the
argument. A nested pair of the same glyph reached after an operand needs parentheses:
`|a (|b|)|`, not `|a|b||`.[^bars]

Trailers attach to the closer: `|x|²`, `⌊x⌋!`. A stray closer is an `unexpected token` error, a
mismatched one ``expected `⌋`, found `⌉` ``, and an unclosed form is incomplete input.

## Application: dynamic name-headed parens

A `(…)` trailer attaches **only** to name-ish heads — a single-character identifier, a
`\`-name, another call, a parenthesized lambda (see [Lambdas](#lambdas-anonymous-functions)), or a parenthesized
`f ∘ g` or `f⁻¹`. Number-headed
parens never even parse as a call (`2(x+1)` is juxtaposition, always). What a call *does* is decided at evaluation by what the head holds:

```
\py("math.sqrt")(2)   ->  head is callable — apply it
s = \py("math.sqrt")  ->  s is bound to the callable
s(4)                  ->  = 2.0
f()                   ->  zero-argument call (legal)
x = 3; x(1+2)         ->  = 9    -- not callable, one argument: paper product x*(1+2)
x(2, 3), x()          ->  ERROR  -- non-callable with ≠1 arguments can't be a product
```

| Head value | Behavior |
|---|---|
| Callable | Apply it |
| Non-callable, exactly one positional argument | Multiply |
| Other non-callable call | Typed “is not a function” error at the call span |

The head's value determines whether `x(y+1)` applies a function or multiplies.
Errors cover the whole call span. Strings on the product path produce the usual
“strings are not numbers” error.

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

Function bodies are semicolon-separated statements; a parenthesized group ([Groups](#groups-parenthesized-statement-sequences))
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
group's closing `)` still belongs to the body — see [Groups](#groups-parenthesized-statement-sequences)).

## Groups: parenthesized statement sequences

A parenthesized group is a statement sequence with an explicit end — and the
multi-line statement form:

```
sequence ::= statement (sep statement)* sep? ;   -- sep: newline run | ";"
```

Without a separator, parentheses contain one expression: `(x=3)` is equality,
and `(f(x)=3)` compares a call result. Use `(x=3;)` or a newline after `x=3`
for a bind/check group. Explicit statement forms such as `(\let x=3)` require
no separator. See [equality expressions](#equality-expressions).

```
f(x) = (
y = x^2
y + 1
)                   -- an explicit multi-statement def body

c ? (a = 1
     a + 1) : 0     -- a group as a ternary branch
```

### Newlines and extent

| Input shape | Parse rule |
|---|---|
| Complete statement followed by newline | Start the next statement |
| `x = 1 +` followed by `2` | Continue the same expression |
| `x = 1` followed by `+ 2` | Two statements; the second is an error |
| Arguments on several lines | Require commas between arguments |
| Blank lines or one trailing `;` | Allowed |
| `;;` | Error |

A group creates no scope and returns its last statement's value. In statement
position, it flattens into the enclosing unit with an echo for each statement.
In a function or conditional branch, it uses that evaluation frame.

Parentheses give a body an explicit end, but a `;` after the closing parenthesis
continues the enclosing statement sequence. Function definitions still consume
their line. A committed open range such as `1..` ends at the closing `)`.

Imports are rejected in ordinary groups and allowed in quoted statement
sequences. Alias directives are top-level only. An unclosed group triggers REPL
continuation; a blank line cancels it. Braces build [sets](#sets).

## Tensors

`[...]` builds a uniform numeric tensor: vectors are order 1, matrices order 2, and higher
orders nest. Indexing is 1-based.

```
v = [1, 2, 3]                   -- order 1
m = [1, 2; 3, 4]                -- `,` separates columns, `;` rows
[[1, 2; 3, 4], [5, 6; 7, 8]]    -- order 3: nested tensors of one shape
m[2, 1]  ->  = 3                m[1]  ->  = [1, 2]
```

| Form | Meaning |
|---|---|
| `[a, b]` | vector; entries are numbers of any tier, or equal-shape tensors that stack |
| `[a, b; c, d]` | matrix; `;` rows hold numbers and have one length |
| `[a, b;]` / `[a; b]` | one-row / one-column matrix — a trailing `;` keeps a single row a matrix |
| `x[i, j]` | 1-based index; fewer indices than axes gives the sub-tensor |
| `x[2..3]`, `x[..,2]` | range or whole-axis selection; ranges retain axes, integers remove them ([slicing](slicing.md)) |
| `x'`, `xᵀ` | transpose: reverses the axes; a vector is unchanged (`'` on a function is its derivative, [calculus](calculus.md)) |
| `a @ b`, `a \contract b` | contraction of `a`'s last axis with `b`'s first: dot product, matrix product |
| `a × b`, `a \times b` | cross product of two length-3 vectors; with a scalar operand, the same as `*` |
| `a ⊗ b`, `a \otimes b` | tensor product: the operands' shapes concatenate; with a scalar operand, the same as `*` |
| `+ - * / ^` | elementwise; a scalar broadcasts, two tensors need one shape |

```
m * m        ->  = [1, 4; 9, 16]        m @ m   ->  = [7, 10; 15, 22]
m + 1        ->  = [2, 3; 4, 5]         m'      ->  = [1, 3; 2, 4]
[1, 2] @ [3, 4]  ->  = 11
```

Entries stay on their exact tiers (`[√2, 1/3] * 3`). Booleans, strings, and other
collections are typed errors, as are the empty tensor `[]`, shape mismatches,
non-integer or out-of-bounds indices, and slices with invalid bounds.[^tensor-index] Tensors compare with the
binding rule's check: same shape and equal entries. `\len(t)` is the outer length,
`\shape(t)` the shape as a vector, `\transpose(t)` the prelude spelling of `t'`.

Folds bind over a tensor's outer slices: `\sum(x=[1, 2, 3]) x^2` is `14`, and
`\sum(r=m) r` adds the rows.

`\contract`, `\times` and `\otimes` are infix operators, never names: they cannot bind or be
aliased, and stand as values only as `(\contract)`, `(@)`, `(×)`, `(⊗)` or a whole call
argument ([Operator values](#operator-values)). The matrix functions are in [standard library](stdlib.md).

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

An array accepts one 1-based exact-integer index or [slice selector](slicing.md)
(chain `a[i][j]` for nested arrays). Ranges and bare `..` return arrays;
folds bind over elements in order. Arithmetic, ordering, approximate comparison,
and transpose on arrays are typed errors. Equality (`=` and `≠`) and binding
checks compare arrays by length and elements in order. Literal heads do not index (`⟨1, 2⟩[1]`
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
value only as `(\cup)` or a whole call argument ([Operator values](#operator-values)).

### Set-builder

`{x ∈ S | p}` filters, `{e | x ∈ S}` maps, and guards follow after commas. The result is a
set: elements deduplicate as in a literal.

```
{x ∈ 1..10 | x^2 < 50}     ->  = {1, 2, 3, 4, 5, 6, 7}
{x^2 | x ∈ 1..4}           ->  = {1, 4, 9, 16}
{x^2 | x ∈ 1..4, x > 1}    ->  = {4, 9, 16}
{x ∈ 1..10 | x > 2, x < 5} ->  = {3, 4}
```

The first top-level `|` after the first item of a `{ }` is the separator, decided before
bars are read: bars still open at an operand (`{|x| | x ∈ s}`), but after an operand the
bar separates. A first item of the form `x ∈ S` is the filter form; otherwise the binder
`x ∈ S` follows the bar. The domain is a finite range or collection (an infinite one is an
error; parenthesize `(1..)` when a bar follows a range end), guards are booleans, and
the binder scopes like a fold's. Map-form generators and guards evaluate left to right;
later domains see earlier bindings. A false guard skips the remaining clauses for
that branch. Binder names must be distinct. A map-form clause `name ∈ domain` is a
generator; other clauses are guards. Filter shorthand binds one name.

```text
{x+y | x ∈ 1..3, x > 1, y ∈ 1..x} -> = {3, 4, 5, 6}
```

Sets display in first-seen order and compare regardless of it: `{1, 2} = {2, 1}` is
`true`. Sets nest (`{{1, 2}, {2, 1}}` is `{{1, 2}}`) and hold tensors, arrays, strings,
and functions. A `NaN` never equals itself, so `{\nan, \nan}` keeps both.
`\len(s)` is the size and folds bind over the elements. Building a set compares
elements pairwise.[^set-cost]

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

Operators pass as values: `\fold(+, xs)` ([Operator values](#operator-values)).

### Infinite ranges and lazy sequences

`\map`, `\filter`, `\scan`, `\enumerate` and `\zip` (when every argument is infinite) over an
infinite range (`1..`) or another lazy sequence return a **lazy sequence**, which runs nothing
until something consumes it: `\take`, or a fold binder.

```
s(x) = x^2
q = \map(s, 1..)                                 ->  q = <seq \map(s, 1..)>
\take(3, q)                                      ->  = ⟨1, 4, 9⟩
\take(2, \filter(\fn(x) x > 5, q))              ->  = ⟨9, 16⟩
\take(4, \scan(+, 1..))                          ->  = ⟨1, 3, 6, 10⟩
\take(2, \enumerate(q))                          ->  = ⟨⟨1, 1⟩, ⟨2, 4⟩⟩
\fold(+, \map(\fn(x) 1/x^2, 1..))               ->  = 1.6449…  -- like the \sum binder
\sum(k=\map(\fn(x) 1/x^2, 1..)) k                ->  = 1.6449…  -- converges like Σ over 1..
```

| Rule | Detail |
|---|---|
| Re-iteration | A sequence re-runs from the start each time it is consumed; it caches nothing |
| Errors | A failing element (or a `\filter` predicate returning a non-boolean) errors when it is reached, not when the sequence is built |
| Folds | `\sum`/`\prod` binders and `\fold` consume a sequence with the infinite-range convergence rule ([Special forms](#special-forms-folds-and-limits)): float tier, plateau exit, error at 2,000,000 elements; only `\fold(+, …)` gets the sum tail estimate. `\len` rejects it |
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
| `∠` `\angle` | 2 | `r∠θ`: the complex number of modulus `r` and angle `θ` |
| `∧ ∨ → ↔` `\and \or \implies \iff` | 2 | connectives on booleans; as values they evaluate both operands |
| `¬` `\not` | 1 | boolean negation |
| `-` | 1 or 2 | negate, or subtract |
| `@` `\contract` | 2 | contraction — the same as infix `@` |
| `×` `\times` | 2 | cross product or scalar multiple — the same as infix `×` |
| `⊗` `\otimes` | 2 | tensor product or scalar multiple — the same as infix `⊗` |
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
| Custom operators | Declared names, glyphs and punctuation support both sections; ordinary calls take priority when a custom spelling is followed by `(`, even with spaces. Use `⊕(·,(1+2))` for a grouped right operand |
| Quotes | A section is the hole form: `\expr((+ 1))` prints `\expr((+)(·, 1))` |

## Custom infix operators

`\infix(N)` defines an ordinary two-argument function with infix syntax:

```text
\infix(11) \blend, ⊕(a,b) = a+b
2 ⊕ 3*4                  -- 14
\blend(2,3)              -- 5
```

An operator has a backslash name, an unused mathematical glyph, a punctuation
spelling, or a backslash name paired with one glyph or punctuation spelling. Parameter names are distinct. Valid integer levels
are **3, 4, 5, 6, 9, 10, 11, 12, 15**, using the table above. At each selected
level, the expression grammar also accepts the declared operator.

Custom operators associate left; built-ins retain their own association. Mixed
chains involving a non-associative built-in at the same level require parentheses.
Custom calls evaluate both operands and use ordinary function scoping, recursion,
values, partial application and sections. `(⊕ 2)` is `⊕(·,2)`; `(2 ⊕)` is
`⊕(2,·)`. Section boundaries use the declared precedence. See
[custom operator sections](operators.md#sections) for operand and call rules.

Declarations are top-level and affect their body and later statements. The REPL
retains them; scripts and imported modules have independent parsing declarations.
A complete successful parse publishes declarations, including when subsequent
evaluation fails. Failed or incomplete parses publish nothing.

See [custom operators](operators.md) for spelling rules, examples, API state, and
[limitations](operators.md#limitations).

## Conditionals: the ternary

The ternary `condition ? then : otherwise` is the one conditional. It is lazy —
only the selected branch evaluates — and the condition must be a boolean. It
binds looser than every other expression
operator (precedence table, level 1) and nests right-associatively through its
branches; a nested middle closes at the first free `:`. A missing `:` at end of
input offers the REPL continuation prompt. There is no two-branch form — a
conditional that could do nothing would have no value to give, so a ternary is an
expression that always needs its else. Branches may be any expression, including
parenthesized statement groups (the multi-statement branch — [Groups](#groups-parenthesized-statement-sequences)):

```
x > 0 ? 1 : -1                  ->  = 1
\sum(i=1..10) i > 5 ? i : 0     ->  = 40
5 > 3 ? 1..3 : 4..6             ->  = <range 1..3>
a > 0 ? 1 : b > 0 ? 2 : 3       -- a ? 1 : (b ? 2 : 3)
1 < 2 ? (x = 4
         x + 1) : 99            ->  = 5    -- a group is the multi-statement branch
```

### Piecewise

`{c₁: v₁; c₂: v₂; otherwise}` is a chain of conditions in braces: the first true
condition's value, evaluated lazily. Clauses separate on `;` or a newline; the last bare value
is the default and may be left out, in which case an uncovered input is the typed error
`no piecewise case matched`. Conditions are booleans.

```
f(x) = {x < 0: -x; x}
f(-3)                         ->  = 3
s(x) = {x < 0: -1; x > 0: 1; 0}
{
x < 0: "neg"
"other"
}                             -- clauses on their own lines
```

A `{ }` whose first item is followed by `:` is a piecewise; `{c ? a : b}` is still a set of
a ternary.

Comparisons `=`, `≠`, `<`, `>`, `<=`, and `>=` return booleans, displayed as `true` or `false`.
Booleans are valid values and conditions but are not numeric operands. There is no
numeric truthiness: a number is never a condition — `0 ? 1 : 2` is a typed error,
not a silent pick. Comparisons, boolean values and logical expressions are conditions.

### Integer congruence

`a ≡ b (mod n)` (ASCII `a \equiv b (mod n)` or `a == b (mod n)`) is a comparison
with a required parenthesized modulus suffix. `(\mod expression)` is also accepted.
The suffix terminates the RHS before call or juxtaposition parsing consumes it.
The modulus is a full expression; operands must be exact integers and the
modulus nonzero. Congruence does not chain. See [integer congruence](congruence.md)
for spellings, nesting and examples.

### Equality expressions

`lhs = rhs` compares values without binding a name. Each side evaluates once,
left to right, using the same value equality as a binding check. Equality binds
at comparison precedence, tighter than logic and the ternary. Comparisons do
not chain: `1=2=3` and `1<2=3` are errors; parenthesize a side to compare booleans.

| Context | Meaning |
|---|---|
| `x=3` at statement start | Bind or check `x` |
| `f(x)=body` at statement start | Define `f` |
| `(x=3)` | Compare `x` with `3`; an unbound `x` is an error |
| `(f(x)=3)` | Compare the call result with `3` |
| `(x=3;)` or `(x=3` followed by a newline and `)` | Bind/check in a statement group |
| `p=x=3` | Bind/check `p` against the boolean `x=3` |
| `g(x=3)` | Named argument `x` with value `3` |
| `g((x=3))` | Positional boolean argument |
| `g(p=x=3)` | Named argument `p` with a boolean value |

```text
x=3
(x^2=9) ? 10 : 20             ->  = 10
(x=3) ∧ (x<4)                 ->  = true
```

A newline after `=` or another operator continues the expression:
`(x=` followed by a newline and `3)` compares values. Leading newlines inside
parentheses do not select statement-group parsing. Explicit statement forms
such as `(\let x=3)` remain statements without a separator. Special-form
binders retain their meaning, including `\sum(i=1..3)` and `\lim(x=0)`.

Equality is an infix expression; `(=)`, `(= 3)`, `(3 =)` and bare `=` operator
arguments are parse errors. Explicit equation quotes retain their
[whole-side parsing](#quotes-and-evaluation).

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
[Assignment semantics](#assignment-semantics)).

### Arrow form

`x ↦ body` is `\fn(x) body`, and `(x, y) ↦ body` is `\fn(x, y) body`; `() ↦ body` takes no
arguments. The ASCII spellings are `->` and `\mapsto`.[^arrow] The node and the greedy body
are the lambda's, so arrows nest right-associatively.

```
\map(x -> x^2, [1, 2, 3])     ->  = [1, 4, 9]
((x, y) ↦ x * y)(3, 4)       ->  = 12
(x -> y -> x + y)(1)(2)      ->  = 3
```

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

`\sum`, `\prod`, `\lim`, `\diff`, `\int`, `\forall` and `\exists` are
**special forms**, not functions: their first parenthesized argument is a binding — an
identifier, `=`, then the bound expression — which general expressions cannot contain.
Folds and quantifiers also take `∈` (or `\in`) in place of `=`; `\lim` binds a point, so it
takes `=` only. The parser recognizes the `(ident =` shape after one of these heads; any other
parenthesized use is a parse-time usage error naming the expected binder form, and
without a paren the head is simply an unbound name at evaluation. The unicode
spellings `Σ` and `Π` are name aliases of `\sum` and `\prod` (see [Name aliases](#name-aliases))
— they normalize to the canonical heads before the special-form table is consulted,
and a user `\alias` onto those names gets the same treatment for free.

```
\sum(i=1..10) i^2            ->  = 385          -- fold + over the range
\prod(j=1..5) j              ->  = 120          -- fold *
Σ(k=1,3..7) k                ->  = 16           -- stepped ranges bind too
\lim(x=0) x/x                ->  = 1.0          -- numeric limit; anchor never evaluated
\diff(x=1) \sin(x)          ->  = 0.5403…      -- numeric derivative (∂ is the same name)
∂(x=1, 3) x^4              ->  approximately 24.0 -- third derivative
∫(x=0..π) \sin(x)            ->  = 2.0          -- numeric integral (∫ is the same name)
∀(x=1..5) x > 0              ->  = true         -- quantifiers bind like \sum
∀(x∈1..5) x > 0              ->  = true         -- `∈` reads the same as `=`
Σ(k∈⟨1, 2, 3⟩) k             ->  = 6            -- folds take it too
∃(n=1..) n^2 > 1000          ->  = true         -- searches an infinite range
```

`∀` and `∃` (`\forall`, `\exists`) take a boolean body and return a boolean: `∀` stops at the
first `false`, `∃` at the first `true`, and an empty domain gives `true` and `false`. An
infinite domain with no deciding element is a typed "undecided" error after 2,000,000
elements. Unlike a sum, the bound stays exact.

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
(relatively scaled; [numerics](numerics.md)), hard-capped at `MAX_TERMS` — while infinite
sums additionally stop early on a confirmed tail estimate (monotone-decay or Leibniz
shapes with a bounded claimed error). The cap produces a typed error rather
than returning a possibly-misleading partial result; so does any non-finite partial.

`\diff` and `\int` bind `x` the same way and evaluate the body in a fresh frame per probe;
`\diff(x=a, n)` takes an optional positive integer order, evaluated outside the body's
binder scope; omitted order means one. `\int` takes a range binder.
Their methods and tolerances are in [calculus](calculus.md), and `\diff`
and `\int` (`∂`, `∫`) join `Σ` and `Π` in the alias table.

**Limits are numeric only** — this is a calculator, not a CAS. `\lim(x=a) body` probes
both sides with geometrically shrinking steps and never binds `x` to `a` itself. Each
side must stabilize within `MAX_PROBES`; sides stabilizing further than twice the
(relatively scaled) tolerance apart report `` limit does not exist: left and right estimates disagree ``
(jump discontinuities like `\lim(x=0) x < 0 ? -1 : 1`). A pole (`\lim(x=0) 1/x`)
never stabilizes and reports probe exhaustion instead. Cancellation-prone spellings of
removable singularities (e.g. `(x^2 - 1)/(x - 1)` near 1) lose float precision as steps
shrink and may fail to stabilize — write them simplified.

## String literals

Strings are values: they bind, appear anywhere an expression does and display as
quoted, round-trippable text. Escaped quotes and backslashes use the same spelling
on input and output.

| Use | Behavior |
|---|---|
| `"data" + ".csv"` | Concatenate two strings |
| `"a" + 1`, other arithmetic, or ordering | Typed “strings are not numbers” error |
| `\py("dotted.path")`, `\mode="r"` | Positional or keyword argument |
| `\py(n + ".sqrt")` | Compose a Python callable path |
| `s = "a"; s = "a"` | Binding check prints `true` |
| Bare string statement | Silent note |

```text
> "chapter 3: convergence"
> 1 + 1
< = 2
```

Strings compare equal only to strings with the same content. String
equality uses `=`, as in `("a"="a")`; `==` denotes integer congruence.
A Python `str` returns as an ordinary ad string, and ad strings cross into Python as native `str`. See the
[conversion matrix](numerics.md#the-python-boundary-conversion-matrix).

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

| Rule | Behavior |
|---|---|
| File resolution | Importing file's directory, then working directory; REPL uses working directory |
| Python resolution | Dotted paths, as with `\py`; a Python module passed to `\import` gets a `\pyimport` hint |
| Caching | Each ad file evaluates once per session in its own root environment |
| Closures | Imported functions retain the module's environment |
| Cycles | Typed error naming the import chain |
| Validation | Validate every requested member before binding any |
| Existing names | Protected names or conflicting values error; the identical cached value is a silent no-op |

Imports copy bindings into the importer; repeating `=` checks them rather than
reassigning. Re-imports reuse cached values.[^imports]

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
name-alias mechanism, [Name aliases](#name-aliases)); where
there is no unicode form, the `\` spelling is the only one (`\sin`, `\lim`, `\solve`, ...).

The names are chosen to match their LaTeX command where one exists, so `ad` source reads like
the ASCII you'd already type to write the same expression in LaTeX — this is a naming
convention, not a claim that `ad` parses TeX. Built-ins are listed under
[The prelude](#the-prelude); [language guide](language.md) has the fuller picture and `README.md` the
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
| `∀` | `\forall` |
| `∃` | `\exists` |
| `∫` | `\int` |
| `∂` | `\diff` |

`\alias` extends the map for the rest of the session:

```
\alias \sum, σ        -- σ reads and checks as \sum
\alias \alpha, α, ϵ   -- several short spellings may share one canonical name
```

`\dual` declares the pair and defines the canonical name in one statement — the
ordinary definition forms with a second spelling attached:

```
\dual \alpha, α = 3.14               -- binds \alpha; echoes α = 3.14
\dual \fact, φ(n) = n*\fact(n-1)     -- echoes φ = <fn φ(n)>
```

| Rule | Behavior |
|---|---|
| Canonical first | First name is canonical; remaining names are single-letter aliases |
| Declare before use | A declaration affects subsequent statements in the same input unit |
| Top-level only | `\alias` and `\dual` cannot appear in functions or groups |
| Protected names | Existing prelude spellings cannot be repurposed; aliases onto prelude names are allowed |
| Session scope | REPL aliases persist; scripts and modules start from seeded aliases |
| Source spelling | Lookup uses canonical names; diagnostics and fresh echoes use the written spelling |
| Atomic registration | Failed or cancelled parsing registers nothing; an evaluation failure can leave a parsed alias registered |

`\alias \pi, ϖ` adds a spelling for the protected constant; `\alias x, e` is an
error. `√` is an operator rather than a letter, so it cannot be an alias.
Declarations do not rename earlier parsed uses. Scripts and imported modules
neither inherit nor export session aliases.[^alias-api]

Bare `\alias`/`\dual` heads (not followed by a name) stay ordinary unbound names and
report their usage at evaluation, like `\py`.

## Assignment semantics

`name = expr` binds or checks in the current frame:

| Name in current frame | Result |
|---|---|
| Protected prelude name, except `i` | Redefinition error |
| Unbound | Bind once; print `name = value` |
| Bound | Compare with the existing value; print `true` or `false` |

There is no reassignment operator. `\let name = expr` requires a fresh name and
errors if it is already bound in the current frame. To compute another value,
use a fresh name or a function call with a fresh frame.

Comparison follows value semantics across numeric tiers. Exact decimals compare
with equal rationals; incompatible kinds compare unequal.

```text
x = 1
x = 1.                 -> true
s = "a"
s = 1                  -> false
```

### Frame locality

Reads search locals, enclosing scopes, globals and the prelude. Binding and
checking stay in the current frame. A local `y = expr` shadows a global `y`;
repeating it checks the local value without changing the global.

Function definitions always declare: defining `f(x) = body` on a bound or
protected name is an error. The top-level `\let f(x) = body` form has the same
fresh-only behavior. Within call arguments, `name=value` passes a keyword
argument and never binds.

Top-level groups flatten into statements with individual echo lines and create
no scope. Expression-position groups use their evaluation frame.

### The imaginary-unit exception

`i` and `\i` are the same shadowable name. `i = 5`, `f(i) = i*i` and
`\sum(i=1..3) i` use ordinary frame rules. A shadow covers both spellings and
ends with its scope; `\complex(0, 1)` still accesses the imaginary unit.
Other prelude names remain protected, and `\alias` cannot repurpose `i`.

## The prelude

Built-in constants and functions live in a protected prelude scope. Every binding
is immutable; `\let` explicitly requires a fresh binding.

| Name | Value or operation |
|---|---|
| `π` / `\pi` | Exact symbolic π; displays `3.14159265358979...` |
| `e` | Exact symbolic e; displays `2.71828182845905...` |
| `i` / `\i` | Exact imaginary unit; the one shadowable prelude name |
| `\inf` / `\nan` | Float constants `Inf` and `NaN` |
| `\true` / `\false` | Boolean constants |
| `\sin` `\cos` `\tan` `\ln` `\sqrt` | Elementary functions; exact arguments stay exact |
| `\isnan` / `\isinf` / `\isfinite` | Numeric finiteness tests; exact tiers are finite |
| `\complex(re, im)` | Build a complex value; zero imaginary part collapses to real |
| `\re` / `\im` | Real and imaginary components |
| `\root(x, n)` | `x^(1/n)` for exact positive integer `n`; `∛x` uses `n=3` |
| `\emptyset` / `∅` | Empty set |
| `\map` / `\filter` / `\fold` / `\scan` / `\take` | [Higher-order functions](#higher-order-functions) |
| `\jacobian` / `\hessian` | [Symbolic calculus arrays](symbolic-calculus.md) |
| `\tensor(xs)` | Rectangular nested numeric array to tensor |
| `\len` / `\shape` / `\transpose` | Collection length, tensor shape and transpose |
| `\prec(n)` | RRA display precision, 1–1000 significant digits; returns `n` |

Prelude protection applies to assignments, parameters, local bindings and binders.
`π = 3`, `f(π) = π` and `\sum(π=1..3) π` are redefinition errors. Diagnostics
name the spelling written at the failing occurrence. `i` is the exception; see
[assignment semantics](#assignment-semantics).

Unicode and ASCII aliases refer to one binding. `√` is a prefix operator that
calls `\sqrt`, with no separate binding.

```text
√2 * √2                  ->  = 2
\sqrt(2^(1/3))           -- exact algebraic 2^(1/6)
\sin(1)                  -- exact RRA value
\sqrt(2.)                ->  = 1.4142135623730951
\sqrt(-1.)               ->  = 1.0i
\re(2+3i)                ->  = 2
\im(π·i)                 -- exact π
```

Elementary functions use the symbolic, algebraic or RRA tier for exact results,
and float or complex float arithmetic for float inputs. Exact-tier domain
failures such as `\ln(0)` and `\tan(π/2)` are typed errors. Float domain errors
are wrapped and spanned. See [numerics](numerics.md) for dispatch and display.

Finiteness tests reject non-numeric arguments. `\im` of a real float returns `0.0`.
`\complex` reads float components as exact decimals. Built-in functions display
as `<fn \sqrt(x)>`, `<fn \root(x)>` and corresponding names. See the
[standard library](stdlib.md) for all prelude functions.

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
(`\sum(i=1..10) …`, `Σ(i=1..) …` — see [Special forms](#special-forms-folds-and-limits)).

If either endpoint is explicitly infinite, the same syntax creates a
non-iterable [interval](intervals.md), such as `-\inf..0` or `0..\inf`.
Intervals supply reusable integral bounds and test continuous real membership;
they cannot serve as fold domains. Finite-start `a..` keeps its progression
semantics.

An open range ends at a closing delimiter, including `}`, `]`, `⟩`, `⌋`, and `⌉`.
Sets and arrays store a range as one element without expanding it:
`{1..}` contains one lazy infinite range, and `⟨1..3⟩` contains one finite range.
Tensors require numeric elements, so `[1..]` is a typed error. Set-builders require
finite domains even when their guards would select only finitely many elements.

A callable binds like any other value (`s = \py("math.sqrt")` prints `s = <py math.sqrt>`);
a call returning a string binds like any value too (see [String literals](#string-literals)). Two
non-numeric values never compare equal unless identical — strings by content.

## Units

[Unit commands](units.md) are protected numeric values. `\per` is a division
alias with the same precedence and associativity as `/`. Long unit names such as
`\metre` leave bare single-letter variables available.

## Limitations

Graphing is not implemented.
`!=` is unsupported; use `≠` / `\neq`. Equality uses `=`; `==` denotes
[integer congruence](congruence.md) and requires a modulus suffix.
Custom infix declarations are described in [custom operators](operators.md).
Name aliases cover names only (see [Name aliases](#name-aliases)).
Planned work is tracked in [GitHub issues](https://github.com/takeiteasy/adhoc/issues).

[^bars]: `|a|b||` reads as `|a|·b·|` and fails at the last bar. Inside `{ }` the first item
    reads with a separator bar on the stack, so `{a |b|}` is set-builder and needs `{a*|b|}`
    for the product ([Sets](#sets)).

[^tensor-index]: A `[` trailer attaches only to name-ish heads (a name, a call, another
    index, a transpose), so `[1, 2][1]` is not an index: it juxtaposes two tensors and fails
    on the shape mismatch. A name holding a number followed by `[...]` multiplies, matching
    the call rule (`k = 3; k[1, 2]` is `[3, 6]`); any other head is `` `…` is not indexable ``.
    Whitespace is not significant, so `v [1]` also indexes.

[^set-cost]: Quadratic in the number of elements; see
    [Limitations](language.md#limitations).

[^arrow]: `->` in these docs' examples also marks "evaluates to" (`f(3)  ->  = 10`); in code it
    is always the lambda arrow. It is not the implication `→` (`\implies`).

[^subscripts]: Supported subscript letters are `ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ`.

[^atom-starters]: `ATOM_STARTERS` (the set of tokens `juxtaposed` treats as "another factor follows") is
    `number`, `string`, `identifier`, `\`-name, a custom operator glyph, `√`, `∛`, `∜`,
    `(`, `[`, `{`, `⟨`, and `#[` — deliberately **not** `-` or `'`, so `a - b` always
    parses as subtraction, never as `a * (-b)`. A string juxtaposed with anything (`"a" "b"`)
    parses as the multiplication it spells and dies as the usual typed "strings are not
    numbers" at evaluation — the same shape as any other string reaching a numeric operator.
    Declared custom operator spellings end a juxtaposition run and parse as infix instead.

[^alias-api]: The driver threads the alias map explicitly through the `aliases=`
    argument to `parse_program` and `compile_source`. Each name occurrence retains
    source spelling as non-semantic metadata.

[^imports]: Cached values are copied as snapshots, while function closures retain
    module-global reads. Separate sessions evaluate fresh, unrelated values.

[^reduction]: Reduction is leftmost-outermost and avoids variable capture. Nested
    quotes remain opaque. The reducer produces a typed error after 10,000 beta
    steps; `\eval` performs arithmetic on the reduced result.
