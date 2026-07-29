# Architecture

## Pipeline (phase 0)

```
source text
    │
    ▼
lexer (src/lexer.jl)      -- tokens: numbers, identifiers, \-names, operators
    │
    ▼
parser (src/parser.jl)    -- precedence-climbing over docs/grammar.md, produces an AST
    │
    ▼
ast (src/ast.jl)          -- NumLit, Var, BinOp, UnOp, Assign, Seq
    │
    ▼
eval (src/eval.jl)        -- tree-walking interpreter, environment = Dict{Char,AdNum}
    │                        all arithmetic goes through src/num.jl
    ▼
repl (src/repl.jl)        -- read/print loop, per-line error recovery
```

`src/num.jl` is a seam, not a pass in the pipeline — every stage that touches a number value
calls into it rather than using Julia arithmetic directly. See `docs/numerics.md`.

## What's durable vs. disposable

The roadmap's phase 4 replaces the evaluator with an interaction-net engine (Lafont
combinators, graph rewriting to normal form) — a from-scratch design, not a port of an
existing engine. That phase only replaces `src/eval.jl`'s *reduction strategy*:

- **Durable** — the lexer, AST shape, parser, and the `Num` interface. Phase 1-3 language
  features add AST nodes and grow `Num`, but don't change this structure.
- **Disposable** — `src/eval.jl`'s tree-walk and `src/repl.jl`'s glue. These exist to validate
  language semantics before the interaction-net engine exists to test them against; they're
  expected to be deleted, not evolved, when phase 4 lands.

This is why phase 0 keeps the tree-walker deliberately simple: effort spent hardening it
beyond "correct enough to validate phase 1-3 semantics" doesn't carry forward.

## Numeric tower (target shape, phase 3+)

The design's exact-arithmetic tower — bignum integers, bignum rationals, symbolic closed
forms, algebraic numbers, and a Recursive Real Arithmetic (RRA) fallback — is described in
full in the project's design notes. `docs/numerics.md` covers what phase 0 actually
implements (the bottom two tiers) and where the seam for the rest goes.
