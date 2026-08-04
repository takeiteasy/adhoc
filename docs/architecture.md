# Architecture

## Layout: library and binary

`adhoc` is two crates in one package: a library (`src/lib.rs`) that *is* the language, and a
thin binary (`src/main.rs`) that runs it. Nothing in the library touches stdin/stdout beyond
what `diagnostic::render` returns as a string — the REPL loop, history, and script-file
handling live entirely in the binary and depend on the library the way any other consumer
would.

```
adhoc (library)                        adhoc (binary)
├── span        — byte-offset spans    ├── main      — argv, script-mode driver
├── lexer       — tokens               ├── repl      — prompt loop, rustyline glue
├── ast         — typed node enum      └── output    — shared diagnostic printing
├── parser      — precedence climbing
├── num         — the numeric seam
├── interp      — tree-walking evaluator
└── diagnostic  — caret-pointing renderer
```

## Pipeline

```
source text
    │
    ▼
lexer (src/lexer.rs)      -- tokens: numbers, identifiers, \-names, operators; byte spans
    │
    ▼
parser (src/parser.rs)    -- precedence-climbing over docs/grammar.md, produces an AST
    │
    ▼
ast (src/ast.rs)          -- typed Node/NodeKind enum, each node carries its own Span
    │
    ▼
interp (src/interp.rs)    -- tree-walking interpreter, environment = HashMap<char, AdNum>
    │                        all arithmetic goes through src/num.rs
    ▼
repl / main (binary)      -- read/print loop or script-file driver, shared error rendering
```

`src/num.rs` is a seam, not a pipeline stage — every point that touches a number value calls
into it rather than using a Rust arithmetic operator directly. See `docs/numerics.md`.

## Spans and diagnostics

Every token and every AST node carries a `Span { start: u32, end: u32 }` — byte offsets,
0-based, half-open — tagged at construction time. The parser tags a node's span when it
*builds* the node, not on the way back out of the `parse_*` call that produced it: the
`(expr)` case in `parse_atom` returns the inner expression's node unchanged, and tagging on
unwind there would overwrite that inner node's own, narrower span with the paren-inclusive
one.

`interp.rs` evaluates a `BinOp`'s operands *before* wrapping the arithmetic call itself in
error handling, so a sub-expression's own error (an unbound variable, a nested division by
zero) keeps its own narrow span; only the arithmetic operation is tagged with the enclosing
node's span. `docs/numerics.md` and the module docs on `interp.rs` have the pinned narrowing
examples.

`diagnostic::render(source, label, message, span)` takes a span and a message rather than an
error value, which is what lets the REPL and script mode (`main.rs`) share it unchanged — the
one difference between them is *when* each calls it, not how the output looks.

## The interpreter is the engine

There is no bootstrap-then-replace split here. `interp.rs`'s tree-walking evaluator and the
REPL/script drivers around it are the durable implementation, not a stand-in for a future
interaction-net engine — that design direction is recorded in `DESIGN.md` as a future
direction, not scheduled work (see `ROADMAP.md`). Nothing in this codebase is written
expecting to be deleted.

## The numeric tower

The design's exact-arithmetic tower — bignum integers, bignum rationals, symbolic closed
forms, algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback — is described in
full in `DESIGN.md`. `docs/numerics.md` covers what's implemented today (the bottom two
exact tiers plus a float fallback) and where the seam for the rest goes.
