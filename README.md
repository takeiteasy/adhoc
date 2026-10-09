# adhoc

> **Work in progress.** This project is under development; expect missing features and breaking changes.

`ad` is executable LaTeX for arithmetic — a calculator language where the ASCII you'd already
type to *write* a piece of math is the thing that *runs* it.

```
LaTeX source     \sum_{i=1}^{10} i^2
rendered         Σ(i=1..10) i²
ad               \sum(i=1..10) i^2
                 < = 385
```

Two rules produce that:

- An identifier is one letter, optionally subscripted (`x₁`); `ab` means `a * b`, as it would on paper.
- Anything longer is a `\`-command, spelled like its LaTeX name where one exists
  (`\pi`, `\sum`, `\sqrt`, `\sin`, `\in`, ...) — so `2\pi r` means what it looks like it means.

`ad` isn't a TeX parser and has no layout or document commands — the overlap is notation, not
compatibility. See [`docs/language.md`](docs/language.md) for supported features, and
[`docs/grammar.md`](docs/grammar.md) for the full grammar.

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
`;` or a newline). Working examples live in [`demos/`](demos/) — start with
`.venv/bin/adhoc run demos/basics.ad`.

Pass `--emit-py` anywhere on the command line to print the generated Python source for each
statement to stderr — a window into the lowering.

## Tests

```
.venv/bin/python -m pytest
```

Heavyweight tests are marked `slow`;
`.venv/bin/python -m pytest -m "not slow"` runs the fast subset.

## Docs

| Guide | Contents |
|---|---|
| [Language guide](docs/language.md) | Values, bindings, functions, collections and interop |
| [Grammar](docs/grammar.md) | Syntax, lexical rules and precedence |
| [Formal grammar](docs/grammar-ebnf.md) | EBNF parser productions |
| [Collection slicing](docs/slicing.md) | Range selectors, tensor shapes and bounds |
| [Notation](docs/notation.md) | Math glyphs and ASCII spellings |
| [Custom operators](docs/operators.md) | Infix declarations, precedence and scope |
| [Calculus](docs/calculus.md) | Derivatives and integrals |
| [Symbolic rewriting](docs/symbolic.md) | Simplification, expansion, factoring and solving |
| [LaTeX output](docs/tex.md) | Rendering quotes, functions and values |
| [Standard library](docs/stdlib.md) | Prelude constants and functions |
| [Numerics](docs/numerics.md) | Exact arithmetic, convergence, display and Python conversions |
| [Architecture](docs/architecture.md) | Package layout and evaluation pipeline |
| [Runtime lowering](docs/lowering.md) | Engine calls, scope and error mapping |

See [the roadmap](ROADMAP.md) for planned work.

## License

Copyright © 2025 George Watson. Licensed under [GPLv3 or later](LICENSE).
