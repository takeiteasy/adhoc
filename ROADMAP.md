## roadmap

This document is mirrored into the sr.ht tracker: one ticket per phase bullet, and unresolved
`DESIGN.md` audit items as their own tickets. This file stays the source of reasoning; the
tracker is the source of status.

Phased implementation plan derived from `DESIGN.md`, ordered by value and dependency rather
than by section order in the design doc. The lowering pipeline (`adhoc/compiler.py` executing
on CPython) is the durable evaluation engine; later phases add language surface on top of it,
they don't replace it. The interaction-net engine and parallel rewriting recorded in
`DESIGN.md` are retired from this roadmap (see future directions).

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

- Functions: `f(a, b) = ...` definition, application, local scoping, and `;`-sequenced bodies.
  Definitions lower into the same callable world as interop values.
- Recursion: function's own name is bound within its own body scope.
- Conditionals: lazy `\if(condition, then[, otherwise])`; parenthesized sequence groups
  support multi-statement branches. A false no-otherwise conditional is a statement no-op.
- Comparisons: `<`, `>`, `<=`, `>=`; logical operators remain future work.
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

Not committed to a phase, ordered roughly by weight. The interaction-net engine and parallel
active-pair rewriting from earlier drafts are retired: `DESIGN.md` keeps the design thinking,
but nothing builds toward them unless an HVM-style engine is ever actually adopted as a real
backend. The λ-literals and term-rewriting exploration is tracked as tickets 34/35 — the
former is phase-independent, the latter rides phase 4.

- **LaTeX export** — `\tex(\expr(...))` renders an expression value back out as TeX/Unicode
  source: `ad` reads like LaTeX, this is the round-trip. Small once phase-4 expression
  values exist — pretty-printing over the quoted AST.
- **Literate script mode** — strings are already comment-like statements; a script-mode flag
  emits a Markdown/LaTeX transcript with each result inline. Half the feature exists.
- **Number-theory prelude + postfix `!`** — `\gcd`, `\mod`, `\choose`, and factorial as a
  postfix operator (the precedence table already reserves postfix slots). Wrinkle to settle
  first: `a ≡ b (mod n)` congruence notation collides with `≡`-as-const.
- **Exactness introspection** — ask which tier a value lives on (`\exact(v)`), control RRA
  display precision. Small, and it makes the numerics story visible.
- **Textbook multi-clause definitions** — `f(0) = 1; f(n) = n·f(n-1)` as one definition,
  first matching clause winning; generalizes the designed piecewise `\otherwise` form.
  Design tension: a clause sequence must read as one definition, not successive rebinding,
  to coexist with the immutability rules.
- **Recurrence-defined lazy sequences** — `a(n) = a(n-1) + a(n-2)` memoized and lazy,
  foldable over `a(1)..`. The natural consumer of the existing lazy/convergence machinery.
- **Units and dimensional analysis** — `9.8 \m \per \s^2` with dimension errors at the
  numeric seam. The exact tower loves it and prelude protection gives unit names a home;
  costly, high ceiling — positions `ad` as the physics quick-calc tool.
- **Exact symbolic differentiation** — `\diff(\expr(x^2), x)` via product/chain-rule AST
  rewriting; easier than `\solve` and exact where CAS-lite tools float. A candidate to
  promote into phase 4 rather than past it.
- **Arbitrary-precision float tier** — MPFR/gmpy2 behind the numeric seam with a `\prec(n)`
  directive (docs/numerics.md already anticipates the slot); makes RRA display tunable.
- **Module system growth** — `\import`/`\pyimport` exist (ad files and Python members,
  statement-level, cached per session); what remains: imported constants joining the
  protected set on import ("this file's constants are protected", generalizing the
  prelude machinery), dotted attribute access on bound Python objects, and module
  namespaces as values.
