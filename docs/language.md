# Language: what's implemented today

This describes the subset of `ad` that actually runs right now — not the full design. For the
target language, see `DESIGN.md`. For the formal grammar, see `docs/grammar.md`.

## Working today

- A REPL: `> ` prompts for input, `. ` prompts for a continuation when a statement is
  incomplete, `< ` prefixes output, Ctrl-D exits.
- Multi-line input: an unterminated statement (`(1 + 2`, `1 +`, `2 ^`, `x =`, `"abc`) buffers
  and continues on the next line rather than erroring immediately. A blank line cancels a
  pending continuation.
- Script mode: `adhoc run script.ad` runs a file through the same grammar, printing one
  `< ...` line per top-level statement. A file is one source and whitespace is
  insignificant, so statements are separated by `;` (the REPL parses line-by-line, which
  is why interactive input doesn't need them). See `demos/` for working examples.
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
- Assignment (`x = 1`), equality-check-if-bound (`x = 1` again), force-reassign (`x := 1`).
- Multi-character variables use the same backslash sigil as multi-character functions:
  `\bar = 100; \foo = 200; \foobar = \foo\bar`.
- `--` line comments, plus bare string literals as comment-like statements (`"a note"` is
  parsed and ignored — strings are literals, not values; docs/grammar.md).
- Postfix application `f(x)`: name-headed parens parse as calls; at evaluation a callable
  head applies, and a non-callable head with exactly one argument falls back to the paper
  product (`x(y+1)` = `x*(y+1)`). Number-headed parens (`2(x+1)`) are always
  juxtaposition. Zero-argument calls are legal. Keyword arguments pass through to Python
  callables natively: `\py("int")("ff", \base=16)` → `= 255` (multi-character kwarg names
  take the `\` sigil; user-defined functions take positional arguments only).
- The `\py` escape hatch: `\py("math.sqrt")(2)` → `= 1.4142135623730951`. Resolves any dotted
  Python path to a callable (full trust — same power as running Python itself); arguments and
  results convert at the boundary (docs/numerics.md). Returned strings print display-only and
  cannot be bound.
- Exact integer and rational arithmetic (`1/3 + 1/3 + 1/3` is exactly `1`, not `0.999...`).
- Exact rationals display as `a/b` (`1/2` prints `1/2`, not `0.5`).
- User-defined functions: `f(x) = x^2` or `\fact(n) = ...`, local parameters and assignments,
  semicolon-sequenced bodies, first-class function values, and recursion.
- Comparisons `<`, `>`, `<=`, `>=` return `true`/`false` and reject arithmetic use.
- Booleans are real values: comparisons produce them, arithmetic rejects them, `\if`
  consumes them, and `\true`/`\false` are bound constants.
- Lazy conditionals: `\if(condition, then)` and `\if(condition, then, otherwise)`. A false
  two-argument conditional is a statement-level no-op; parenthesized sequences such as
  `(a = 1; a + 1)` support multi-statement branches.
- Constant declarations: `c ≡ 5`, `c == 5` (ASCII alias — declares, never compares), or
  `\const c = 5` declare permanently-immutable globals —
  no `=`, `:=`, local assignment, parameter, or binder can ever rebind the name, and
  `\const f(x) = ...` declares an immutable function the same way.
- A protected prelude scope: `π`/`\pi`, `e`, `\true`/`\false`, and the `\sin`, `\cos`,
  `\tan`, `\ln`, `\sqrt` function aliases (the plain `math.*` callables, float tier).
  Prelude names can never be rebound or shadowed, and unicode/ASCII spellings are one and
  the same value (`π` and `\pi` are a single constant).
- Lazy arithmetic ranges: `a..b` is an inclusive step-1 range, `a..` is infinite, and
  `a,c..b` / `a,c..` infer the step as `c-a`. Finite ranges stop before crossing an
  unreachable endpoint; ranges display as `<range ...>` and can be assigned.
- Folds: `\sum(i=1..10) i^2` → `= 385` and `\prod(j=1..5) j` → `= 120`, with the unicode
  spellings `Σ` and `Π`. The loop variable scopes like a function parameter (reads fall
  through, writes stay local, nothing leaks). Finite ranges accumulate exactly.
- Infinite-range folds: `\sum(i=1..) 1/i^2` ≈ ζ(2) evaluates as the limit of partial sums
  — approximate iteration in the float tier until values stabilize within tolerance,
  erroring at the iteration cap rather than returning a misleading partial (`\sum(i=1..) i`
  errors; docs/numerics.md).
- Numeric limits: `\lim(x=0) x/x` → `= 1.0` approximates by two-sided shrinking-step
  probing without ever evaluating at the anchor. Disagreeing one-sided limits (jump
  discontinuities) report `` limit does not exist ``.

## Not yet implemented

Everything phase 2 onward: logical operators, tensors/arrays/sets, the rest of the
exact-arithmetic tower (symbolic closed forms, algebraic numbers, RRA), symbolic algebra
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
same way, and meaning comes from two places — the parser's closed set of special forms
(`\sum`/`\prod`/`\lim` binders, call-shaped `\if`, `\py`, `\const`) and the prelude scope of
built-in constants and function aliases (see docs/grammar.md, `## Constants and the
prelude`). Everything else lexes cleanly and fails at evaluation as an unbound name, so
later phases add bindings without touching the lexer.

## Known limitations (not bugs)

- Caret columns are counted in *characters*, not terminal display width. A genuinely
  full-width or combining-mark identifier character will make the caret land a column or two
  off; ordinary unicode letters like `π` are unaffected (1 character, 1 column). Not worth a
  `unicode-width` dependency for a case that essentially never arises in a calculator.
- Strings have no escape sequences: a literal ends at its closing quote, so a string
  containing a double quote is unrepresentable. Deliberate v1 scope; revisit if a real need
  shows up.
