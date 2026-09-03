# Language: what's implemented today

This describes the subset of `ad` that actually runs right now — not the full design. For the
target language, see `DESIGN.md`. For the formal grammar, see `docs/grammar.md`.

## Working today

- A REPL: `> ` prompts for input, `... ` prompts for a continuation when a statement is
  incomplete (an open paren or string — the gutter is the visible "still open" signal),
  `< ` prefixes output, Ctrl-D exits.
- Multi-line input: an unterminated statement (`(1 + 2`, `1 +`, `2 ^`, `x =`, `"abc`,
  an unclosed `(`) buffers and continues on the next line rather
  than erroring immediately. A blank line cancels a pending continuation.
- Script mode: `adhoc run script.ad` runs a file through the same grammar, printing one
  `< ...` line per top-level statement. Statements are separated by `;`, a newline, or
  simply by ending mid-expression and continuing on the next line — one uniform newline
  rule everywhere, inside parens and out. See `demos/` for working
  examples.
- Caret-pointing error diagnostics with source spans, e.g.:
  ```
  < ERROR! division by zero
      1/0
      ^~~
  ```
- REPL history, persisted to `$ADHOC_HISTORY` (default `~/.adhoc_history`).
- Arithmetic: `+ - * / ^`, unary minus, parentheses, implicit multiplication by juxtaposition
  (`2x` = `2 * x`, `ab` = `a * b`).
- Bare identifiers are exactly one character (ASCII or unicode); multi-character names,
  including user-defined function names, use the backslash sigil (`\fact`).
- Assignment (`x = 1`) with declare-once-then-check semantics: a fresh name binds; `x = 1`
  again *compares*, printing `true`/`false` — there is no reassignment and no declaration
  operator, every binding is immutable (docs/grammar.md, `## Assignment semantics`).
- Multi-character variables use the same backslash sigil as multi-character functions:
  `\bar = 100; \foo = 200; \foobar = \foo\bar`.
- `--` line comments, plus bare string literals as comment-like statements (`"a note"` alone
  on a statement is parsed and echoes nothing; docs/grammar.md).
- Postfix application `f(x)`: name-headed parens parse as calls; at evaluation a callable
  head applies, and a non-callable head with exactly one argument falls back to the paper
  product (`x(y+1)` = `x*(y+1)`). Number-headed parens (`2(x+1)`) are always
  juxtaposition. Zero-argument calls are legal. Keyword arguments pass through to Python
  callables natively: `\py("int")("ff", \base=16)` → `= 255` (multi-character kwarg names
  take the `\` sigil; user-defined functions take positional arguments only).
- The `\py` escape hatch: `\py("math.sqrt")(2)` → `= 1.4142135623730951`. Resolves any dotted
  Python path to a callable (full trust — same power as running Python itself); arguments and
  results convert at the boundary (docs/numerics.md). Strings are values: they bind,
  concatenate with `+`, and compose `\py` paths (`\py(n + ".sqrt")`).
- Anonymous functions (lambdas): `\fn(x) x + 1` or `\λ(x) x + 1` — a definition without
  the name. First-class, eager, fixed arity, closures capture the defining scope; a
  parenthesized lambda applies in head position (`(\fn(x) x)(5)` → `= 5`); bodies extend
  greedily unless bounded by a parenthesized group; display as `<λ(x)>` (docs/grammar.md,
  `## Lambdas`).
- Parenthesized statement groups: newlines separate statements inside `(...)` exactly as
  at top level, so a group is the multi-line, multi-statement form for def bodies,
  ternary branches, and lambda bodies — same flattening/scope rules as a top-level
  `Seq`, value of its last statement. Braces stay reserved for future set
  literals (docs/grammar.md, `## Groups`).
- Imports, statement-level and silent: `\import("lib")` binds the top-level names of `lib.ad`
  (all of them, or only the listed members: `\import("lib": f, \fact)`), each file evaluating
  once per session in a fresh root environment — imported functions keep the module's
  environment as their closure, re-imports reuse the cache, cycles are typed errors, and
  resolution searches the importing file's directory then the working directory.
  `\pyimport("math": \hypot, \tau)` binds named Python-module members (callables as
  callables, values through the conversion matrix); member selection is mandatory and
  there are no module values or dotted attribute access (docs/grammar.md,
  `## Modules and imports`).
- Exact integer and rational arithmetic (`1/3 + 1/3 + 1/3` is exactly `1`, not `0.999...`),
  exact symbolic closed forms (`√2 * √2` is exactly `2`), exact real algebraic
  numbers (`2^(1/3)` stays exact, displaying `1.25992104989487...`), and exact
  Recursive Real Arithmetic (`π + 1` stays exact, displaying
  `4.14159265358979...`; any error bound yields a rational within it).
- Exact rationals display as `a/b` (`1/2` prints `1/2`, not `0.5`).
- User-defined functions: `f(x) = x^2` or `\fact(n) = ...`, local parameters and assignments,
  semicolon-sequenced bodies, first-class function values, and recursion.
- Comparisons `<`, `>`, `<=`, `>=` return `true`/`false` and reject arithmetic use.
- Booleans are real values: comparisons produce them, arithmetic rejects them, the
  ternary consumes them, and `\true`/`\false` are bound constants. There
  is no numeric truthiness — a number is never a condition (`0 ? 1 : 2` is a typed
  error).
- Lazy conditionals: the ternary `c ? a : b` is the one conditional — only the selected
  branch evaluates. It is right-associative with the loosest expression precedence,
  and a parenthesized statement group is its multi-statement branch form
  (docs/grammar.md, `## Conditionals`).
- A protected prelude scope: `π`/`\pi` and `e` are exact symbolic reals (displaying with
  a trailing ellipsis), `\inf`/`\nan` the non-finite floats, `\true`/`\false` the booleans,
  and the `\sin`, `\cos`, `\tan`, `\ln`, `\sqrt` function builtins — exact arguments go
  through the symbolic closed-form tier (`\sqrt(2)` stays `√2`), everything else falls to
  the `math.*` float tier (`\sin(1)`).
  Prelude names can never be rebound or shadowed, and unicode/ASCII spellings are one and
  the same value (`π` and `\pi` are a single constant, via the name alias map). `√` is the
  prefix-operator spelling of `\sqrt(...)` — `√2 * √2` collapses back to the exact
  integer `2` (docs/numerics.md).
- Lazy arithmetic ranges: `a..b` is an inclusive step-1 range, `a..` is infinite, and
  `a,c..b` / `a,c..` infer the step as `c-a`. Finite ranges stop before crossing an
  unreachable endpoint; ranges display as `<range ...>` and can be assigned.
- Folds: `\sum(i=1..10) i^2` → `= 385` and `\prod(j=1..5) j` → `= 120`, with the unicode
  spellings `Σ` and `Π`. The loop variable scopes like a function parameter (reads fall
  through, writes stay local, nothing leaks). Finite ranges accumulate exactly.
- Name aliases: one name owns several spellings — `Σ` is `\sum`, `π` is `\pi`, and
  `\alias \sum, σ` declares your own for the session (declare-before-use, top-level
  only, protected names repurposed by no one; docs/grammar.md, `## Name aliases`).
- Dual-form definitions: `\dual \alpha, α = 3.14` and `\dual \fact, φ(n) = ...` define
  the canonical name and register its short spelling in one statement; both spellings
  read and compare as the same binding.
- Infinite-range folds: `\sum(i=1..) 1/i^2` ≈ ζ(2) evaluates as the limit of partial sums
  — approximate iteration in the float tier until values stabilize within tolerance,
  erroring at the iteration cap rather than returning a misleading partial (`\sum(i=1..) i`
  errors; docs/numerics.md).
- Numeric limits: `\lim(x=0) x/x` → `= 1.0` approximates by two-sided shrinking-step
  probing without ever evaluating at the anchor. Disagreeing one-sided limits (jump
  discontinuities) report `` limit does not exist ``.

## Not yet implemented

Everything phase 2 onward: logical operators, tensors/arrays/sets, the RRA tier of the
exact-arithmetic tower (symbolic closed forms and algebraic numbers are in), symbolic algebra
(`\expr`/`\solve`/...), metaprogramming, and graphing. See `ROADMAP.md` and the tracker for
status.

## The `\` sigil, briefly

Every name longer than one character is written with a `\` prefix — `\pi`, `\sum`, `\sin`,
`\solve`. This falls out of a single rule: identifiers are exactly one character, so `ab`
unambiguously means `a * b`; anything spelled with more than one character needs a marker to
avoid colliding with that. The `\` names are chosen to match LaTeX commands where one exists,
so `ad` source reads like the ASCII you'd already type to write the same expression in LaTeX —
see `README.md`. This is a naming convention, not a claim that `ad` parses TeX: there are no
layout or document commands, and the set of `\`-names with language-defined meaning is small
and closed.

The lexer itself carries no name table: any `\`+letters/underscores sequence tokenizes the
same way, and meaning comes from three places — the parser's closed set of special forms
(`\sum`/`\prod`/`\lim` binders,
`\py`, statement-shaped
`\import`/`\pyimport`, the lambda heads `\λ`/`\fn`),
the session alias map that normalizes short spellings to canonical
names (`Σ`→`\sum`, seeded and extended by `\alias`; docs/grammar.md, `## Name aliases`), and
the prelude scope of
built-in constants and function builtins (see docs/grammar.md, `## Constants and the
prelude`). Everything else lexes cleanly and fails at evaluation as an unbound name, so
later phases add bindings without touching the lexer.

## Known limitations (not bugs)

- Symbolic, algebraic and RRA values display 15 significant digits plus a trailing
  ellipsis (`π` is `3.14159265358979...`, `2^(1/3)` is
  `1.25992104989487...`, `π + 1` is `4.14159265358979...`). The value is exact;
  only the digits are approximate —
  the ellipsis says so (docs/numerics.md).
- Caret columns are counted in *characters*, not terminal display width. A genuinely
  full-width or combining-mark identifier character will make the caret land a column or two
  off; ordinary unicode letters like `π` are unaffected (1 character, 1 column). Not worth a
  `unicode-width` dependency for a case that essentially never arises in a calculator.
