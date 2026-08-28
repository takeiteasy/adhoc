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
- A **name** longer than one character is written `\`-prefixed (`\pi`, `\sin`, `\fact`, ...).
  After the first character a name may continue with letters or underscores (`\rel_tol`,
  `\my_var`); a `_` cannot start a name. Backslash names may be built-ins or user-defined
  names, including variables; an unbound one fails at evaluation.
- Operators: `+ - * / ^ < > <= >= = ≡ == .. ( ) ,`. Statement separator: `;`.
  `==` is an ASCII alias for `≡` — it declares a constant, it never compares (see
  `## Constants and the prelude`).

## Grammar (EBNF)

```
program    ::= statement (";" statement)* ";"? ;
statement  ::= func-def
             | const-stmt
             | import-stmt
             | pyimport-stmt
             | string
             | identifier "=" expr
             | expr ;
const-stmt ::= identifier "≡" expr
             | identifier "==" expr
             | "\const" name "=" expr
             | "\const" name "(" params? ")" "=" statement (";" statement)* ;
import-stmt   ::= "\import" "(" string (":" member ("," member)*)? ")" ;
pyimport-stmt ::= "\pyimport" "(" string ":" member ("," member)* ")" ;
member        ::= identifier | "\"-name ;

expr       ::= range ;
range      ::= comparison (".." comparison? | "," comparison ".." comparison?)? ;
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
arg        ::= expr | string | kwarg ;
kwarg      ::= (identifier | "\"-name) "=" (expr | string) ;
func-def   ::= identifier "(" params? ")" "=" statement (";" statement)* ;
params     ::= identifier ("," identifier)* ;
atom       ::= number | identifier | "\"-name | "(" sequence ")" ;
sequence   ::= statement (";" statement)* ;
```

A trailing `;` after the last statement is tolerated (`1;` and `2;` both parse as a single
statement, not as a statement followed by an empty one).

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
| 1 | `=` `≡` `==` | statement level only, non-associative |
| 2 | `..` (range) | non-associative |
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
list is purely an argument-passing form; statement-level `=` is the only assign-or-check.
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

Function definitions are callable values. Parameters are still one-character identifiers,
while a multi-character function name uses
the backslash sigil:

```
f(x) = x^2 + 1
f(3)                         ->  = 10
f(a,b) = c = ab; cc          -- c and the parameters are call-local
f(3,4)                       ->  = 144
\fact(n) = \if(n <= 1, 1, n*\fact(n-1))
```

Function bodies are semicolon-separated statements. A call gets a fresh local frame;
reads fall through to globals, while assignments never escape the call. The function's
own name is installed in that frame before the body runs, enabling recursion. Definitions
are first-class and display as `<fn f(x)>` or `<fn \fact(n)>`.

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

## Special forms: folds and limits

`\sum`, `\prod`, `\lim`, and the unicode spellings `Σ` ≡ `\sum`, `Π` ≡ `\prod` are
**special forms**, not functions: their first parenthesized argument is a binding — an
identifier, `=`, then the bound expression — which general expressions cannot contain.
The parser recognizes the `(ident =` shape after one of these heads; any other
parenthesized use is a parse-time usage error naming the expected binder form, and
without a paren the head is simply an unbound name at evaluation.

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
(`docs/numerics.md`), hard-capped at `MAX_TERMS`. The cap produces a typed error rather
than returning a possibly-misleading partial result; so does any non-finite partial.

**Limits are numeric only** — this is a calculator, not a CAS. `\lim(x=a) body` probes
both sides with geometrically shrinking steps and never binds `x` to `a` itself. Each
side must stabilize within `MAX_PROBES`; sides stabilizing further than twice the
tolerance apart report `` limit does not exist: left and right estimates disagree ``
(jump discontinuities like `\lim(x=0) \if(x < 0, -1, 1)`). A pole (`\lim(x=0) 1/x`)
never stabilizes and reports probe exhaustion instead. Cancellation-prone spellings of
removable singularities (e.g. `(x^2 - 1)/(x - 1)` near 1) lose float precision as steps
shrink and may fail to stabilize — write them simplified.

## String literals

Strings are **literals, not values**. There is no string type in the value model; a string
never enters the environment, cannot be bound, stored, concatenated, or computed on. They
appear in exactly two places:

1. **As a whole argument of a call** — the `\py("dotted.path")` case, positional or as a
   kwarg value (`\py("open")("f.ad", \mode="r")`). The literal converts directly to a
   native Python `str` at the boundary; no ad string value ever exists.
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
  the module, a protected name (prelude or session constant), or a name already bound
  to a different value is a typed error; a name already bound to the *identical*
  cached value is a silent no-op (re-import). Imported names land as ordinary
  bindings — rebindable, not protected.

```
\import("lib")                 -- bind everything lib.ad defines at the top level
\import("lib": f, \fact)       -- bind only f and \fact
\pyimport("math": \hypot)      -- bind math.hypot as \hypot
\hypot(3, 4)                   ->  = 5.0
```

## The `\` sigil

An identifier is exactly one character. Any language-defined name longer than one character
is `\`-prefixed, regardless of script — `\pi`, `\sum`, `\sin`, `\solve`, `\map`, `\graph`. Where
a `\`-name has a single-character unicode form, they are the same name (`\pi` ≡ `π`); where
there is no unicode form, the `\` spelling is the only one (`\sin`, `\lim`, `\solve`, ...).

The names are chosen to match their LaTeX command where one exists, so `ad` source reads like
the ASCII you'd already type to write the same expression in LaTeX — this is a naming
convention, not a claim that `ad` parses TeX. The built-ins bound today are listed under
`## Constants and the prelude`; `docs/language.md` has the fuller picture and `README.md` the
framing.

## Assignment semantics

- `x = e`, `x` unbound → bind `x`, prints `x = v`
- `x = e`, `x` bound → **compare** current value to `v`, prints `true` / `false`
- `x ≡ e` / `x == e` / `\const x = e`, `x` fresh → declare permanently immutable, prints `x = v`
- `x ≡ e` / `x == e` / `\const x = e`, `x` bound or protected → error (see `## Constants and the prelude`)
- bare expression → prints `= v`

There is no force-reassignment operator — a global is bound once and thereafter only
compared against (a paper page doesn't reassign either). To iterate on a value, bind a
fresh name (`\x_2 = ...`) or compute inside a function, where every call starts from a
fresh frame and body writes are plain frame writes. Note that inside an argument list,
`name=value` is a keyword argument and never assigns — statement-level `=` is the only
assign-or-check.

Statement groups flatten: a top-level `(a; b)` becomes plain top-level statements, each
with its own echo line — the parentheses do not create a scope. Writes that survive are
the expression-position ones: function bodies and `\if` branch groups write into the
frame they evaluate in (branch locals when fresh, the enclosing frame otherwise).

## Constants and the prelude

`x ≡ e` (ASCII `x == e`, keyword `\const x = e`) declares a global binding that can never
be rebound — not by `=`, not by a local assignment, a parameter, or a binder
name. `\const f(x) = ...` declares a function under the same rule (the `≡`/`==` spellings
are bindings only). A declaration is not assign-or-check: the name must be fresh and
top-level.

`==` deliberately declares rather than compares: it is the fast-to-type spelling of `≡`,
chosen precisely because statement-level `=` already covers assign-or-check and expression
`=` is reserved for plain boolean equality — no `==` comparison operator exists or will.
Read `x == 5` as "x is *identically* 5", never as a question.

Built-in names live in a prelude scope protected by that same mechanism:

| spelling | value |
|---|---|
| `π` / `\pi` | 3.141592653589793 |
| `e` | 2.718281828459045 |
| `\true` / `\false` | the booleans — comparisons return them, arithmetic rejects them |
| `\sin` `\cos` `\tan` `\ln` `\sqrt` | the `math.*` float-tier callables |

Prelude names are **protected everywhere**: `π = 3`, a parameter named `π`, a local
`π = ...`, or a `\sum(π=...)` binder are all redefinition errors (`` `π` is a constant ``),
never shadows. Unicode and ASCII spellings are the same value — `π` and `\pi` are one
constant, not two. The function aliases are the plain float-tier `math.*` callables
(`\sqrt(2)` is `1.4142135623730951`, not an exact symbolic value); the symbolic closed
forms of the exact-arithmetic tower will replace those bindings in place.

User constants (`c ≡ 5`) join the protected set for the rest of the session — across
REPL inputs, exactly like ordinary bindings.

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

Ranges can be assigned and passed through the runtime; folds bind them directly
(`\sum(i=1..10) …`, `Σ(i=1..) …` — see `## Special forms`).

A callable binds like any other value (`s = \py("math.sqrt")` prints `s = <py math.sqrt>`);
a call returning a string is rejected instead of bound (strings are literals, see
`## String literals`). Two non-numeric values never compare equal unless identical.

## Deferred

Logical operators, collections, the
exact-arithmetic tower beyond int/rational/float, symbolic algebra, graphing.
See `ROADMAP.md` and the tracker for the phase each lands in.
