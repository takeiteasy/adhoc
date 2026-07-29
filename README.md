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

Phase 0: a REPL that evaluates arithmetic exactly (`1/3 + 1/3 + 1/3` is `1`, not
`0.999...`), with assignment and force-reassignment. Everything past that — functions,
ranges, sums/products, collections, symbolic algebra, graphing — is on the roadmap, not yet
built.

## Running it

Requires Julia 1.12+.

```
julia --project=. -e 'using Pkg; Pkg.instantiate()'
./bin/adhoc
```

```
> 1 + 2 * 3
< = 7
> x = 1 + 2
< x = 3
```

## Tests

```
julia --project=. test/runtests.jl
```

## Docs

See [`docs/`](docs/) for the language reference, grammar, architecture, and numerics notes.
