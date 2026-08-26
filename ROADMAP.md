## roadmap

This document is mirrored into the sr.ht tracker: phases 0-1 as one ticket per bullet, phases
2+ as one checklist ticket per phase, and unresolved `DESIGN.md` audit items as their own
tickets. This file stays the source of reasoning; the tracker is the source of status.

Phased implementation plan derived from `DESIGN.md`, ordered by value and dependency rather
than by section order in the design doc. The interaction-net engine described in `DESIGN.md`
is a recorded future direction, not scheduled work — it does not appear as a phase here. The
lowering pipeline (`adhoc/compiler.py` executing on CPython) is the durable evaluation engine;
later phases add language surface on top of it, they don't replace it.

### phase 0 — foundations

- Implementation language: **Python**. Numeric backing via stdlib `int`/`Fraction`/`float`
  behind the numeric seam (see `docs/numerics.md`; gmpy2/sympy can slot behind the same
  seam later).
- Lexer: whitespace-insensitive, single-char ascii/unicode identifiers, `--` comments,
  case-sensitivity, byte-offset spans on every token.
- Parser: core grammar — literals, arithmetic (`+ - * / ^`, parens), assignment/equality-check
  `=`, force-reassign `:=`. AST as frozen dataclasses, spans on every node.
- Diagnostics: caret-pointing error rendering with source spans, per-node span narrowing.
- REPL: multi-line continuation, history, line editing.
- Script mode: `adhoc run script.ad` — the same grammar fed a whole file instead of
  line-by-line, sharing the REPL's diagnostic rendering.
- Evaluator: lowering of the adhoc AST to Python's own AST, executed on CPython through a
  span-tracking runtime seam.

### phase 1 — core language semantics

- Functions: `f(a, b) = ...` definition, application, local scoping, `;`-sequenced bodies.
  The definition shape is already reserved and parsed (evaluating reports "reserved for
  phase 1"), and postfix application plus callable values exist since interop v1 —
  definitions lower into that same callable world.
- Recursion: function's own name bound within its own body scope.
- Conditionals: piecewise `x \if x >= 0; -x \otherwise`.
- Comparison/logical operators, added as needed (not enumerated in `DESIGN.md` — open, expect
  `<`, `>`, `<=`, `>=`, `\and`, `\or`, `\not` at minimum).
- Ranges: `a..b`, `a..` (lazy infinite), `a,c..b` / `a,c..` (step-inferred).
- `Σ`/`\sum`, `Π`/`\prod`, `\lim` — fold over a range; infinite-range `Σ`/`Π` as limit of partial
  sums.
- Globals/constants: `=`/`:=` rules, `≡`/`\const` for permanent immutability.
  - Prelude constants (`π`, `e`, `\sin`, ...) are protected everywhere, not shadowable
    (decided).
- Non-converging infinite `Σ`/`Π`: error after a tolerance/iteration cap, reusing the phase-2
  RRA tier's tolerance-based shape rather than a separate mechanism (decided).

### phase 2 — exact arithmetic tower

The calculator's actual differentiator; the numeric seam already routes every operation, so
symbolic/algebraic backends (sympy being an obvious candidate) slot in without touching
anything above the seam — no reason to wait on phase 3's collection types, which are
independent of it.

- Symbolic closed-form irrationals (`π`, `√n`, `eⁿ`, `ln(n)`, `sin(πn)`, `tan(πn)`, ...).
- Algebraic numbers (roots of rational-coefficient polynomials).
- Recursive Real Arithmetic (RRA) fallback: `tolerance -> rational` functions.
- Display precision via iterative tolerance tightening (RRA tier only — exact rationals
  already display as `a/b`, decided and implemented in phase 0).
- Equality testing: exact for rational/algebraic tiers; Richardson-Fitch heuristic (Schanuel's
  conjecture) for RRA tier — accepted limitation, not a bug to fix.
- Numeric type surface: `int`, `real`, `rational`, `complex` literal syntax and
  promotion/coercion rules.
  - Open: literal syntax for each, and int/int → rational-vs-real coercion rule.
  - Open: `i` collision between imaginary-unit literal and conventional loop-binder variable.

### phase 3 — collection types

Independent of phases 1-2; nothing else depends on it.

- Tensor (`[...]`): vector (1D) / matrix (2D) as special cases, `,`/`;` separators, 1-indexing,
  `+`/`*`/dot product/transpose.
  - Open: elementwise vs. matrix multiply/divide distinction (MATLAB's `.*`/`./` or similar).
  - Rank ≥ 3: nested `[...]` (settled).
- Array (`⟨...⟩` / `\arr(...)`): ragged, heterogeneous, ordered, indexing/iteration only, no
  implied algebra.
- Set (`{...}`): unordered, deduplicated, `∪ ∩ ∈ \ ⊆`.

### phase 4 — symbolic algebra & metaprogramming

No longer gated on a future evaluation engine — the mechanism is quoting and rewriting the
AST enum directly (`match`-and-rebuild), the same way any other Rust code manipulates a typed
tree.

- `\expr(...)` / `` `(...) `` quoting, `\eval(e, binding...)`.
- `\solve`, `\simplify`, `\expand`, `\factor` as AST rewriting over expression values.
  - Open: full semantics of what these can actually handle — currently syntax-level only in
    the design.
- Function composition (`∘`), `\map`/`\fold`/`\filter` (generalizing the `Σ`/`Π` fold), partial
  application (`f(a, ·)`).
- Reflection: `\body(f)`.
- Custom infix operators: `\infix(N) ⊕(a, b) = ...` with declared precedence.
  - Open: precedence numbering scheme (range, relation to built-in operators).

### phase 5 — graphing

Depends on phase 2 (numeric evaluation); pairs naturally with script mode for saved plots,
but doesn't depend on it.

- `\graph(f, x=a..b)` — domain sampling over a function.
  - Open: fixed-resolution vs. adaptive sampling near discontinuities/high-curvature regions.
- Terminal-native rendering: sixel/kitty graphics protocol detection, Unicode braille-pattern
  ASCII fallback.
- File export (`out="plot.svg"` etc.) — the old scoped-path-literal idea is dead: export goes
  through `\py` (e.g. matplotlib's `savefig`) with an ordinary string-literal argument, since
  interop v1. No special argument syntax.
- Open: multi-function overlay syntax (plotting more than one function on shared axes).

### future directions (unscheduled)

Recorded in `DESIGN.md` as design thinking, not committed to a phase:

- **Interaction-net evaluation engine** — replacing the tree-walking interpreter with a
  Lafont-combinator graph-rewriting engine. Would be a substantial rearchitecture; nothing
  in phases 0-5 is written expecting it.
- **Parallel active-pair rewriting** — concurrent reduction on the interaction-net engine
  above, if it's ever built. Depends entirely on that engine existing first.
