# Rewrite plan: Rust → Python

The Rust implementation (phase 0) is being rewritten in Python, lowering `ad` to Python's
own `ast` so generated code runs on CPython via `compile()`/`exec` — which is what makes
Python libraries reachable from `ad`. This file is the plan of record; each stage lands on
`main`, and the Rust tree stays untouched as the behavioral reference until the parity gate
(stage 4) passes.

## Decisions

| Question | Decision |
|---|---|
| Execution architecture | **Pure lowering** — everything compiles to Python AST; a small runtime module carries exact arithmetic and span-tagged errors. One engine. |
| Numeric backing | **stdlib** — Int→`int`, Rat→`fractions.Fraction`, Float→`float`; `/` and `^` route through runtime helpers to keep exactness (`/` returns float, `**` with a negative exponent returns float). gmpy2 can slot behind the same seam later if perf demands. |
| Python interop syntax | **Escape hatch first** — `\py("math.sqrt")(x)` resolves a dotted path now; real `\import(name)` + dotted-attribute grammar is designed later, once it earns its place. |
| Rust implementation | **Deleted at parity** — tagged `rust-final`, removed from `main` after all ported tests pass. |

Known numeric divergence to pin down explicitly when the runtime lands (docs/numerics.md):
MPFR floats have unbounded exponent range; Python floats overflow on huge exponents. The
overflow behavior gets defined deliberately rather than inherited silently.

## Target shape

```
pyproject.toml          -- package "adhoc", py >= 3.12, console script `adhoc`
adhoc/
  span.py               -- Span(start, end) byte offsets          <- span.rs
  lexer.py              -- tokens, KNOWN_BACKSLASH_NAMES          <- lexer.rs
  syntax.py             -- AST dataclasses (not ast.py — stdlib shadow) <- ast.rs
  parser.py             -- precedence climbing, incomplete-input sentinel <- parser.rs
  diagnostic.py         -- caret rendering                        <- diagnostic.rs/output.rs
  runtime.py            -- numeric seam + assign/check + AdError  <- num.rs + interp semantics
  compiler.py           -- adhoc AST -> python ast.Module         -- new
  driver.py             -- compile/exec + traceback->span mapping <- replaces interp.rs
  repl.py, __main__.py  -- REPL + script mode                     <- repl.rs/main.rs
tests/                  -- pytest; ports of every cargo test
```

## Lowering mechanics

- One generated Python source *line* per `ad` statement, with a `lineno → span` table so any
  escaped exception maps back to a caret position.
- `NumLit` → `Constant` (int without `.`, float with); single-char variables → `Name`
  directly (unicode letters like `π` are legal Python identifiers); `\name` → mangled
  `ad_name`.
- Every operator routes through a runtime helper carrying a span id: `add/sub/mul/neg` are
  thin wrappers (uniformity keeps error spans narrow everywhere); `div/pow` carry real logic
  (exact Fraction paths, `0^-n` → division by zero).
- Statement-level `x = e` never lowers to Python assignment — it lowers to a runtime call
  implementing bind-or-compare; bare expressions wrap for `= v` printing. The environment is
  the exec globals dict; reads stay plain name loads.
- `--emit-py` dumps generated source for debugging.

## Stages

| # | Stage | Exit criteria | Status |
|---|-------|---------------|--------|
| 0 | Scaffold: pyproject, package skeleton, pytest, `.venv` | `pytest` green; `python -m adhoc --version` works | done |
| 1 | Frontend port: span/lexer/syntax/parser/diagnostic | All lexer/parser unit tests green incl. incomplete-input sentinels; caret output identical to Rust | done |
| 2 | Runtime seam: numerics, errors, formatting | All `num.rs` tests ported green | done |
| 3 | Lowering + driver | `interp.rs` suite passes end-to-end through compile/exec; span-narrowing tests pass; emitted-Python snapshot tests | |
| 4 | CLI parity: REPL continuation/history, script mode | `tests/{repl,script}.rs` behaviors green; transcript diff of Rust vs Python binaries clean on an `.ad` corpus | |
| 5 | Interop v1: `\py(...)`, application syntax, value-conversion rules + docs | `\py("math.sqrt")(2)` → `= 1.4142135623730951`; conversion-matrix tests | |
| 6 | Cutover: tag `rust-final`, remove Rust tree, doc sweep | Repo is Python-only, all tests green | |

Stage 5 introduces postfix application `f(x)` early — the grammar already reserves it for
later phases, so this is a forward-compatible addition, not a detour.

## After cutover

Roadmap phases resume on the Python base. The move makes several substantially cheaper:
sympy is a natural backend for the symbolic tier and `\solve`/`\simplify` (phases 2/4);
numpy/matplotlib for `\graph` (phase 5). The interaction-net direction in `DESIGN.md` is
unaffected.
