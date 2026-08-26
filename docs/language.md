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
- Identifiers are exactly one character (ASCII or unicode).
- Assignment (`x = 1`), equality-check-if-bound (`x = 1` again), force-reassign (`x := 1`).
- `--` line comments, plus bare string literals as comment-like statements (`"a note"` is
  parsed and ignored — strings are literals, not values; docs/grammar.md).
- Postfix application `f(x)`: name-headed parens parse as calls; at evaluation a callable
  head applies, and a non-callable head with exactly one argument falls back to the paper
  product (`x(y+1)` = `x*(y+1)`). Number-headed parens (`2(x+1)`) are always
  juxtaposition. Zero-argument calls are legal.
- The `\py` escape hatch: `\py("math.sqrt")(2)` → `= 1.4142135623730951`. Resolves any dotted
  Python path to a callable (full trust — same power as running Python itself); arguments and
  results convert at the boundary (docs/numerics.md). Returned strings print display-only and
  cannot be bound.
- Exact integer and rational arithmetic (`1/3 + 1/3 + 1/3` is exactly `1`, not `0.999...`).
- Exact rationals display as `a/b` (`1/2` prints `1/2`, not `0.5`).

## Not yet implemented

Everything phase 1 onward: function *definitions* (the `f(x) = body` shape is reserved and
parses today, but evaluating it reports "reserved for phase 1"), ranges, `Σ`/`Π`/`\lim`,
piecewise conditionals, comparison/logical operators, tensors/arrays/sets, the rest of the
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
layout or document commands, and the `\`-name table is a small fixed set.

One `\`-name is bound today: `\py("dotted.path")` resolves into Python and returns the callable
(docs/grammar.md). The rest still recognize and lex cleanly, but evaluating one is currently
an "unbound name" error, not a lex error — they're seeded so later phases only need to add
bindings, not touch the lexer.

## Known limitations (not bugs)

- Caret columns are counted in *characters*, not terminal display width. A genuinely
  full-width or combining-mark identifier character will make the caret land a column or two
  off; ordinary unicode letters like `π` are unaffected (1 character, 1 column). Not worth a
  `unicode-width` dependency for a case that essentially never arises in a calculator.
- Strings have no escape sequences: a literal ends at its closing quote, so a string
  containing a double quote is unrepresentable. Deliberate v1 scope; revisit if a real need
  shows up.
