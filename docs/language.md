# Language: what's implemented today (phase 0)

This describes the subset of `ad` that actually runs right now — not the full design. For the
target language, see the project's design notes (kept outside version control; ask if you
need them). For the formal grammar, see `docs/grammar.md`.

## Working today

- A REPL: `> ` prompts for input, `< ` prefixes output, Ctrl-D exits. Lex/parse/eval errors
  render a caret pointing at the offending source span -- eval errors (unbound name, division
  by zero, ...) point at the specific sub-expression that failed, not just the whole line.
  A statement that runs out of input mid-expression (`(1 +`, unclosed parens, a trailing
  operator, ...) gets a `. ` continuation prompt for the next line instead of an error; a
  blank line cancels a pending continuation.
- `bin/adhoc` on an interactive tty gets input history and in-line editing from an in-process
  cl-readline session (arrow keys, `Ctrl-R` search, history persisted to
  `$ADHOC_HISTORY`/`~/.adhoc_history` across runs). Building requires libreadline present
  (`make build` fails without it, same as any other missing Lisp dependency); given a
  successful build, `ADHOC_NO_READLINE=1` falls back to wrapping the image in `rlwrap` instead
  (`ADHOC_NO_RLWRAP=1` on top of that for no editing at all).
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
metaprogramming, script mode, graphing, and the interaction-net evaluator. See the tracker for
status.

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

- `x := e` on an unbound `x` underlines the whole assign statement rather than just `x` — the
  statement is the smallest span that carries meaning for a name that was never bound.
