# adhoc

`ad` is executable LaTeX for arithmetic — a calculator language where the ASCII you'd already
type to *write* a piece of math is the thing that *runs* it.

```
LaTeX source     \sum_{i=1}^{10} i^2
rendered         Σ(i=1..10) i²
ad               \sum(i=1..10) i^2
                 < = 385
```

Two rules produce that:

- An identifier is exactly one character (`ab` means `a * b`, as it would on paper).
- Anything longer is a `\`-command, spelled like its LaTeX name where one exists
  (`\pi`, `\sum`, `\sqrt`, `\sin`, `\in`, ...) — so `2\pi r` means what it looks like it means.

`ad` isn't a TeX parser and has no layout or document commands — the overlap is notation, not
compatibility. See [`docs/language.md`](docs/language.md) for what's real today, and
[`docs/grammar.md`](docs/grammar.md) for the full grammar.

## Status

Core phase 0 plus phase-1 functions and interop v1: a REPL and script runner that evaluate arithmetic exactly
(`1/3 + 1/3 + 1/3` is `1`, not `0.999...`), with assignment, force-reassignment, caret-pointing
error diagnostics, postfix application (`f(x)`), and the `\py("math.sqrt")(2)` escape hatch into
Python — full trust, native conversion both ways (docs/numerics.md). Strings are literals,
not values: they name Python paths and act as comment-like statements, nothing more
(docs/grammar.md). The implementation is pure Python: `ad` lowers to Python's own AST and runs
on CPython. Ranges are lazy and support finite/infinite and inferred-step forms. Everything
else — sums/products, the rest of the numeric tower, collections,
symbolic algebra, graphing — is on the roadmap, not yet built. See [`ROADMAP.md`](ROADMAP.md).

## Running it

Requires Python 3.12+.

```
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/adhoc
```

```
> 1 + 2 * 3
< = 7
> x = 1 + 2
< x = 3
```

Or run a script: `.venv/bin/adhoc run script.ad` (statements in a file are separated by
`;`). Working examples live in [`demos/`](demos/) — start with
`.venv/bin/adhoc run demos/basics.ad`.

Pass `--emit-py` anywhere on the command line to print the generated Python source for each
statement to stderr — a window into the lowering.

## Tests

```
.venv/bin/python -m pytest
```

## Docs

See [`docs/`](docs/) for the language reference, grammar, architecture, and numerics notes.
