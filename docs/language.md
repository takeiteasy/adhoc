# Language: what's implemented today (phase 0)

This describes the subset of `ad` that actually runs right now — not the full design. For the
target language, see `DESIGN.md`. For the formal grammar, see `docs/grammar.md`.

## Working today

- A REPL: `> ` prompts for input, `. ` prompts for a continuation when a statement is
  incomplete, `< ` prefixes output, Ctrl-D exits.
- Multi-line input: an unterminated statement (`(1 + 2`, `1 +`, `2 ^`, `x =`) buffers and
  continues on the next line rather than erroring immediately. A blank line cancels a
  pending continuation.
- Script mode: `adhoc run script.ad` runs a file through the same grammar, printing one
  `< ...` line per top-level statement.
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
- `--` line comments.
- Exact integer and rational arithmetic (`1/3 + 1/3 + 1/3` is exactly `1`, not `0.999...`).
- Exact rationals display as `a/b` (`1/2` prints `1/2`, not `0.5`).

## Not yet implemented

Everything phase 1 onward: ranges, `Σ`/`Π`/`\lim`, functions, piecewise conditionals,
comparison/logical operators, tensors/arrays/sets, the rest of the exact-arithmetic tower
(symbolic closed forms, algebraic numbers, RRA), symbolic algebra (`\expr`/`\solve`/...),
metaprogramming, and graphing. See `ROADMAP.md` and the tracker for status.

## The `\` sigil, briefly

Every name longer than one character is written with a `\` prefix — `\pi`, `\sum`, `\sin`,
`\solve`. This falls out of a single rule: identifiers are exactly one character, so `ab`
unambiguously means `a * b`; anything spelled with more than one character needs a marker to
avoid colliding with that. The `\` names are chosen to match LaTeX commands where one exists,
so `ad` source reads like the ASCII you'd already type to write the same expression in LaTeX —
see `README.md`. This is a naming convention, not a claim that `ad` parses TeX: there are no
layout or document commands, and the `\`-name table is a small fixed set.

None of the `\`-names are bound in phase 0 — the lexer recognizes them (so `\pi` tokenizes
cleanly), but evaluating one is currently an "unbound name" error, not a lex error. They're
seeded now so later phases only need to add bindings, not touch the lexer.

## Known limitations (not bugs)

- Caret columns are counted in *characters*, not terminal display width. A genuinely
  full-width or combining-mark identifier character will make the caret land a column or two
  off; ordinary unicode letters like `π` are unaffected (1 character, 1 column). Not worth a
  `unicode-width` dependency for a case that essentially never arises in a calculator.
