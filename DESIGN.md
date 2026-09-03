## what

ADhoc Higher Order Calculator — a cli based calculator and language like `bc` and `hoc`. The language is designed to be as "math-like" as possible. The language is called `ad` and the calculator program is `adhoc`.

```
> -- comment
> 1 + 2 * 3
< = 7
> (1 + 2) * 3
< = 9
> x = 1 + 2 -- assign variable
< x = 3
> x = 4 -- variables are immutable, checks equality because `x` already exists
< false
```

- Whitespace is ignored
- Variable names and functions must be a single ascii or unicode character
- Case-dependent, `a is not A`
- Unicode is entirely optional in the core language: every unicode operator, constant, or keyword (`Σ`, `Π`, `⟨⟩`, `∪`, `π`, ...) has a mandatory ASCII equivalent. A program never has to use unicode to be valid `ad`; unicode is sugar for people who want the math-notation feel, not a requirement.

```
> f(a, b) = c = ab; cc
< f = <fn>
> x = f(3, 4)
< x = 144
```

`f` is a function that takes A and B parameters. It creates a local `c` variable with the result of `a * b` then return `c * c`.

## keywords and the \ sigil

- An identifier is exactly one character, ascii or unicode (see above) — this is what makes `ab` unambiguous as `a * b`.
- Every language-defined name longer than one character is written with a `\` prefix, regardless of script: `\pi`, `\sum`, `\sqrt`, `\sin`, `\solve`, `\map`, `\graph`, ... The backslash is what a multi-character name costs to stay unambiguous with juxtaposition.
- Where a `\`-name has a single-character unicode form, the two are the same name, not two different ones: `\pi` ≡ `π`, `\sum` ≡ `Σ`, `\prod` ≡ `Π`, `\sqrt` ≡ `√`, `\cup` ≡ `∪`, `\cap` ≡ `∩`, `\in` ≡ `∈`, `\subseteq` ≡ `⊆`, `\setminus` ≡ `∖`, `\circ` ≡ `∘`.
- Where there is no unicode form, the `\` spelling is the only spelling: `\lim`, `\arr`, `\expr`, `\if`, `\otherwise`, `\sin`, `\cos`, `\tan`, `\ln`, `\solve`, `\simplify`, `\expand`, `\factor`, `\eval`, `\body`, `\map`, `\fold`, `\filter`, `\graph`, `\infix`.
- The names are chosen to match their LaTeX command where one exists (`\sum`, `\prod`, `\sqrt`, `\cup`, `\cap`, `\in`, `\setminus`, `\circ`, `\lim`, `\sin`, `\ln`, ...) — `ad` source reads like the ASCII you'd already type to write the same expression in LaTeX. This is a naming convention, not a compatibility claim: `ad` is not a TeX parser and has no layout/document commands.
- Bracket syntax (`[...]`, `{...}`, `⟨...⟩`) is unaffected by this rule — `\arr(...)` is the ASCII *spelling* of `⟨...⟩`, a form rather than a name.
- User-defined infix operators (`⊕` via `\infix(N) ⊕(a, b) = ...`) are exempt — the sigil rule is about language-defined names, not names an author invents.
- Comparisons `<`, `>`, `<=`, `>=` produce real booleans, displayed as `true`/`false`: valid conditions and bindable values, rejected as numeric operands. The literal spellings are `\true`/`\false`, bound in the prelude. Logical operators remain future work.

## precedence

Loosest to tightest binding:

| level | operators | associativity |
|---|---|---|
| 1 | `=` (binding/check) | statement level only, non-associative |
| 2 | `..` (range) | non-associative |
| 3 | `+` `-` (binary) | left |
| 4 | `*` `/` | left |
| 5 | juxtaposition (implicit multiplication, `ab`) | left |
| 6 | unary `-` | prefix |
| 7 | `^` | right |
| 8 | postfix `'`, `[...]`, `(...)` | — |

Juxtaposition binding tighter than `*`/`/` but looser than `^` is a deliberate choice, matching how the expression reads on paper: `1/2x` is `1/(2x)`, not `(1/2)x`; `2x^2` is `2*(x^2)`, not `(2x)^2`. Worked examples: `1 + 2 * 3` = `7`; `(1 + 2) * 3` = `9`; `-2^2` = `-4` (unary minus is looser than `^`); `2^-1` = `1/2`; `2^3^2` = `2^(3^2)` = `512` (`^` is right-associative).

## equality and =

`=` is a single token reused in three ways, disambiguated by position rather than by
introducing a separate `==` operator:

1. **Statement-level, bare identifier on the left** (`x = 1`) — declare-once-then-check: binds `x`
   into the current frame if unbound there, compares against it if bound there. See
   `## globals / constants` and docs/grammar.md, `## Assignment semantics`.
2. **Anywhere else in an expression** (`x = 0` as an operand, e.g. `\solve(e = 0, x)`) — plain
   boolean equality, no different from `<`/`>=`/etc. `\solve`'s first argument is simply a
   normal argument that happens to be an equality expression; no special-casing is needed for
   `\solve` itself.
3. **A small, closed list of builtins** — `\sum`, `\prod`, `\lim`, `\graph`, and any future
   range/domain-taking builtin — treat one specific argument position as a loop-variable or
   domain *binding* rather than parsing it as a general equality expression (`Σ(i=1..10)`,
   `\lim(x=0)`, `\graph(f, x=-5..5)`). This is a named special form tied to those specific
   builtins, not a generic named-argument mechanism available to ordinary user-defined
   functions — an ordinary call `f(a, b)` never takes `name=value` arguments, so this never
   shows up as ambiguous syntax in practice.

## ranges

```
> 1..10
< = <range 1..10>
> 1..
< = <range 1.. (lazy, infinite)>
> 1,3..10
< = <range 1,3..10> -- step inferred from first two elements (3 - 1 = 2)
> 1,3..
< = <range 1,3.. (lazy, infinite, step 2)>
> 10,8..1
< = <range 10,8..1> -- descending, step -2
```

- `a..b` — inclusive range, step 1
- `a..` — lazy, infinite range starting at `a`, step 1
- `a,c..b` — step inferred from `c - a`, not a literal `..` stacked with a step token (avoids `1..10..2` ambiguity, and reads like the textbook ellipsis notation for arithmetic sequences)
- `a,c..` — lazy, infinite, with inferred step

## sum / product / limit

```
> Σ(i=1..10) i^2
< = 385
> \sum(i=1..10) i^2 -- ASCII keyword is sugar for the same construct
< = 385
> Π(i=1..5) i
< = 120
> \lim(x=0) \sin(x)/x
< = 1
```

- `Σ`/`\sum` and `Π`/`\prod` bind a local loop variable (e.g. `i`) over a range and fold `+`/`*` over the body expression. The bound variable is local to the body, following the same scoping as function parameters.
- `Σ`/`Π` over a lazy infinite range (e.g. `Σ(i=1..) 1/i^2`) evaluates as the limit of partial sums/products — infinite sum and `\lim` share the same underlying mechanism rather than being separate features.
- `\lim(x=a) f(x)` is numeric only (this is a calculator, not a CAS) — it approximates by evaluating `f` as `x` approaches `a`, it does not solve symbolically.
- Convergence over a lazy infinite range is checked the same way the RRA tier already works (see `## exact arithmetic (internals)`): partial sums/products are evaluated until they stabilize within a tolerance, capped at a fixed number of terms. If they haven't stabilized by the cap, evaluation errors rather than returning a possibly-misleading partial result — this reuses the tolerance-based shape phase 3 already needs instead of inventing a second convergence mechanism, and stays consistent with the "calculator, not CAS" boundary (no symbolic divergence value, just a numeric answer or a clear error).

## conditionals

Piecewise bodies don't use braces — `\if`/`\otherwise` already self-delimit the branches as the
whole right-hand side, so braces would be redundant, and dropping them frees `{...}` for set
literals:

```
> f(x) = x \if x >= 0; -x \otherwise
< f = <fn>
> abs(x) = x \if x >= 0; -x \otherwise
< abs = <fn>
> f(-3)
< = 3
```

- Piecewise notation, matching how math textbooks write conditional functions, reusing the existing `;`-separated body style.
- `\otherwise` is sugar for a final catch-all branch (no condition needed).
- `=` inside a condition (`x >= 0`) is always a comparison, never a binding — binding-or-check `=` only appears at statement level (`x = 1`), never inside an expression. Comparisons `<`, `>`, `<=`, `>=` exist and produce booleans; `\and`/`\or`/`\not` and other logical operators remain future work.
- Recursion works — a function's own name is bound within its own body scope before evaluation, so `fact(n) = 1 \if n <= 1; n * fact(n-1) \otherwise` is valid. Specifics (e.g. tail-call handling) TBD.

## globals / constants

```
> π = 3.14159265358979
< π = 3.14159265358979
> π = 4 -- a repeat `=` compares; it can never overwrite
< false
```

- Every binding is immutable by the assignment rule itself: a fresh `=` binds, a repeat
  compares (value-based, tower semantics — `1 = 1.0` is `true`). There is no
  reassignment operator and no declaration spelling — the former `≡`/`==`/`\const`
  forms are gone outright, since plain `=` already gave the same immutability.
- Function definitions (`f(x) = body`) are declarations, not checks: a protected or
  already-visible name is an error, since functions compare by identity and a check
  would be meaningless.
- Built-in constants/functions (`π`/`\pi`, `e`, `i`/`\i`, `\true`/`\false`, `\sin`, `\cos`, `\tan`, `\ln`, `\sqrt`, `\complex`, `\re`, `\im`) live in a prelude scope. Every unicode-named builtin has an ASCII name bound to the same value — `π` and `\pi` are the same name, not two different ones. The function builtins are seam-native: exact arguments are recognized through the symbolic closed-form tier (`√2 * √2` collapses back to `2`, `\sqrt(-2)` is `√2·i`), everything else rises through the exact tiers, and only non-established-reals fall to the `math.*` float tier.
- Prelude names are **protected everywhere**, not shadowable — a function parameter, local binding, or fold/limit binder named `π` (or any other prelude name) is a redefinition error, not a local shadow. This keeps a prelude name's meaning fixed regardless of where it's read from, at the cost of a handful of single-character names (`π`, `e`) being permanently unavailable as ordinary variable names. The one exception is `i`: the imaginary unit's spelling is the conventional loop-binder name, so it shadows like any identifier (both spellings read the one binding, and the shadow lifts with the scope).

## numeric types

```
> 3
< = 3            -- int
> 0.5
< = 1/2           -- a decimal literal is an exact rational; 0.5e0 or 1. is float
> 1/2
< = 1/2           -- int/int stays an exact rational; displayed as a fraction
> 2 + 3i
< = 2+3i         -- complex, exact
```

- Every numeric tier is a value: exact integers and rationals (a decimal
  literal `0.5` is the rational `1/2`, read from its own digits; the float
  spellings are the trailing-dot marker `1.` and any exponent form `5e-1`),
  exact complex (`Gaussian` rationals, `2+3i`), symbolic closed forms
  (real or pure-imaginary: `π`, `√2`, `π·i`), algebraic numbers (real or
  complex), the RRA fallback (every other finite number), and the float tier
  beneath as the explicitly-inexact one. Promotion runs upward automatically
  (`int / int` is the exact rational; any float operand demotes to float —
  except a complex operand, which is a typed error: there is no complex-float
  tier), and results collapse back down whenever they can (`i²` is `-1`,
  `(2+2i)/(1+i)` is `2`).
- Negative bases split by exponent: `p/q` in lowest terms with `q` odd takes
  the real branch (`(-8)^(1/3)` is `-2`), anything else the complex principal
  (`(-2)^(1/2)` is `√2·i`); the float tier keeps its pinned NaN.
- The `i` collision is resolved by ordinary scoped shadowing: `i` binds like
  any identifier (`Σ(i=1..10)` keeps working), both spellings read the one
  binding, and the unit is spelled `\complex(0, 1)` inside such a scope.

## execution modes

```
$ adhoc
> x = 1 + 2
< x = 3
> ^D

$ adhoc run script.ad
< x = 3
< = 7
```

- `adhoc` runs both as a REPL and as a script interpreter (`.ad` files) — same grammar, just fed a whole file instead of line-by-line. Error/output semantics between the two modes TBD.

## vectors / matrices

```
> v = [1, 2, 3]
< v = [1, 2, 3]
> m = [1, 2; 3, 4] -- `;` separates rows, `,` separates columns
< m = [1, 2; 3, 4]
> v[1]
< = 1 -- 1-indexed, matching math convention
> m[1, 2]
< = 2 -- row, column
> m'
< = [1, 3; 2, 4] -- transpose
```

- Bracket + row/column-separator syntax (`,` for columns, `;` for rows) follows the same convention as MATLAB/Octave — well-worn, math-notation-adjacent, and reuses `;` without conflict since it's scoped inside `[...]`.
- Indexing is 1-based, matching standard math notation (`m[1,2]` not `m[0,1]`).
- `'` for transpose (common shorthand); TODO: distinguish elementwise vs. matrix multiply/divide (e.g. MATLAB's `.*`/`./`) once operator design happens.
- Strings are values, deliberately minimal (revised from the original "no string type" stance once text round-trips mattered for data loading and `\graph`-style export flows). `"…"` binds, concatenates via `+` (the only string operator; mixed arithmetic is the usual typed rejection), and composes `\py` paths; a standalone string statement remains the comment-like literate note. There is no string indexing, ordering, or equality *operator* — the language has no `==` at all.
- Vector/matrix are special cases (1D/2D) of a general **tensor** type — see below. `[...]` syntax and its rules (1-indexed, `,`/`;` separators, transpose) apply uniformly to tensors of any rank.

## collection types: tensor / array / set

Three distinct types, each with a different contract — collapsing them would lose real semantic differences (algebra only makes sense on a uniform numeric shape; sets can't be ragged/ordered).

**Tensor** — `[...]`, uniform (rectangular) shape, numeric entries only, carries algebra (`+`, `*`, dot product, transpose, contraction). Vector = 1D tensor, matrix = 2D tensor.
```
> t = [1, 2; 3, 4]
< t = [1, 2; 3, 4]
> t + t
< = [2, 4; 6, 8]
```
TODO: literal syntax for rank ≥ 3 (nested `[...]` vs. a per-dimension separator) not yet decided.

**Array** — `⟨...⟩` (unicode) / `\arr(...)` (ASCII sugar), general-purpose ordered container. Can be ragged and hold heterogeneous element types (numbers, tensors, other arrays). No implied elementwise algebra — just indexing/iteration. `\arr(...)` is unambiguous with function calls since function/variable names are constrained to a single character and every multi-char name takes the `\` sigil, so `\arr` can never collide with a user identifier.
```
> a = ⟨1, [1,2], 3.5⟩
< a = ⟨1, [1,2], 3.5⟩
> a = \arr(1, [1,2], 3.5)
< a = ⟨1, [1,2], 3.5⟩
> a[2]
< = [1, 2]
```

**Set** — `{...}`, unordered, deduplicated. Standard set operations, each with an ASCII keyword alternative: `∪`/`\cup`, `∩`/`\cap`, `∈`/`\in`, `∖`/`\setminus` difference, `⊆`/`\subseteq`. ASCII forms stay infix (`a \cup b`, not `\cup(a, b)`) — the `\` sigil already removes the ambiguity that would otherwise motivate normalizing to prefix calls, so the more readable infix form survives.
```
> s = {1, 2, 3}
< s = {1, 2, 3}
> {1, 2, 3} ∪ {3, 4}
< = {1, 2, 3, 4}
> {1, 2, 3} \cup {3, 4} -- ASCII equivalent
< = {1, 2, 3, 4}
> 2 ∈ {1, 2, 3}
< = true
> 2 \in {1, 2, 3} -- ASCII equivalent
< = true
```

Tensor literals of rank ≥ 3 nest `[...]` (e.g. a 2x2x2 tensor as `[[1,2;3,4], [5,6;7,8]]`) rather than introducing a new per-dimension separator.

## symbolic algebra

The language extends beyond pure numeric evaluation: expressions can exist as unevaluated, first-class **expression values** — this is the same underlying mechanism that makes reflection/metaprogramming (below) possible, not a separate feature.

```
> e = \expr(x^2 - 4)
< e = x^2 - 4
> e = `(x^2 - 4)         -- ` is sugar for \expr(...)
< e = x^2 - 4
> \solve(e = 0, x)
< x = {2, -2}
> \simplify(\expr((x+1)^2 - x^2 - 2x))
< = 1
> \eval(e, x=3)
< = 5
```

- `\expr(...)` captures its argument unevaluated as a value; `` `(...) `` is shorthand for the same thing.
- `\solve`, `\simplify`, `\expand`, `\factor` operate on expression values and return expression values or sets of solutions.
- `\eval(e, binding...)` evaluates an expression value under a substitution.
- This is a substantial architectural step up from earlier numeric-only decisions (e.g. `\lim` stayed numeric) — expressions-as-data is now a first-class type, not just sugar over immediate evaluation. TODO: full semantics (what `\simplify`/`\solve` can actually handle) TBD; this section is syntax-level only for now.

## metaprogramming

```
> g = f ∘ h                  -- composition: g(x) = f(h(x))
> g = \circ(f, h)            -- ASCII equivalent
> \map(f, [1, 2, 3])
< = [f(1), f(2), f(3)]
> \fold(+, [1, 2, 3])         -- generalizes the Σ/Π fold mechanism to arbitrary arrays
< = 6
> square = f(a, ·)             -- partial application, fixes the first argument
> square = f(a, _)             -- ASCII equivalent, `_` is the placeholder
> \body(f)                    -- reflection: returns f's underlying expression value
< = a * b
> \infix(7) ⊕(a, b) = a + b    -- user-defined infix operator, explicit precedence
> 3 ⊕ 4
< = 7
```

- Function composition (`∘`/`\circ(f, g)`), higher-order functions (`\map`/`\fold`/`\filter`), and partial application (`f(a, ·)`/`f(a, _)`) all follow directly from functions already being first-class values.
- Anonymous function literals are in the language today — `\λ(params) body` (ASCII `\fn(params) body`), with a parenthesized statement group as the explicit multi-statement body form; see docs/grammar.md, `## Lambdas`. They are the primitives composition, `\map`/`\fold`, and partial application build on.
- `\body(f)` reflection returns a function's expression value (same type as `\expr(...)` produces) — a function is, under the hood, a bound parameter list plus an expression value.
- Custom infix operators declare an explicit precedence per operator (`\infix(N) ⊕(a, b) = ...`) rather than sharing one fixed tier, trading a little more ceremony for Haskell-style fixity flexibility. The operator symbol itself (`⊕` here) is entirely the author's choice — nothing stops it from being ASCII (e.g. `\infix(7) <+>(a, b) = ...`); the `\`-sigil rule applies to *language-defined* operators/names, not user-defined ones. TODO: precedence numbering scheme (range, relation to built-in operators) not yet decided.

## exact arithmetic (internals)

Following the approach used by Android's calculator app (see https://chadnauseam.com/coding/random/calculator-app), numbers are represented internally through a tower of representations, each tried before falling back to the next — the goal is to keep everyday results exact and fast, and only pay for arbitrary precision when actually needed:

1. **Bignum integers** — arbitrary-precision, the base case.
2. **Bignum rationals** — numerator/denominator pairs of bignums.
3. **Symbolic closed forms** — common irrationals (`π`/`\pi` and integer powers of it, `√n`/`\sqrt(n)`, `e^n`, `\ln(n)`, `\sin(π*n)`/`\sin(\pi*n)`, `\cos(π*n)`/`\cos(\pi*n)`, `\tan(π*n)`/`\tan(\pi*n)`, ...) kept as a rational coefficient times a recognized symbolic real, rather than approximated. This is the same underlying value shape as `\expr(...)` from the symbolic algebra section — a "number" and an "unevaluated expression" aren't fully separate concepts here. `√` is sugar for `\sqrt(...)`, same rule as everything else unicode; `\sin`/`\cos`/`\tan`/`\ln` have no unicode form and are always written with the sigil. The strict single-term shape is deliberate: a value with no coefficient×atom form (`π + 1/3`, `π·√2`) falls through to the next tier rather than widening the shape — the tier stays a recognizer, not a general symbolic algebra (that's phase 4).
4. **Algebraic numbers** — roots of rational-coefficient polynomials, for exact values that don't reduce to a known symbolic form (e.g. roots from `solve`).
5. **Recursive Real Arithmetic (RRA)** — the fallback for everything else. Every such real is represented as a function `tolerance -> rational`, i.e. "give me an error bound and I'll give you a rational within it." Arbitrarily precise on demand, but the slowest tier.

Arithmetic operations try to stay at the lowest tier that remains exact (e.g. `rational + rational` stays rational; `√2 * √2` recognizes and collapses back to the integer `2` rather than falling to RRA), only demoting to a higher tier when the result doesn't fit a lower one.

- **Display**: exact rationals display as a fraction (`a/b`), not decimal — `1/3` is `1/3`, never `0.333...`, since it never leaves the rational tier per the rule above. Decimal display is reserved for the RRA tier: rather than picking a fixed number of digits upfront, the REPL repeatedly requests tighter tolerance from the RRA function until enough digits are provably stable, then prints those. (An earlier draft of this doc showed `1/3` going through RRA-style display, which was a category error, not a deliberate choice — decided and fixed.)
- **Equality testing**: exact for rational/algebraic tiers (decidable). For general RRA-tier values, equality is undecidable in general — the design follows Richardson & Fitch (1994): evaluate the difference at increasing precision and treat it as equal if it stays indistinguishable from zero, relying on Schanuel's conjecture. This is a heuristic, not a proof, and is a known, accepted limitation of the approach (not a placeholder to fix later).

```
> 1/3 + 1/3 + 1/3
< = 1                    -- stays exact rational, no float drift
> √2 * √2
< = 2                    -- symbolic tier collapses back to an exact integer
> \sqrt(2) * \sqrt(2)     -- ASCII equivalent
< = 2
> 1/3
< = 1/3                  -- exact rational, displays as a fraction -- never reaches RRA at all
> π
< = 3.14159265358979...
> \pi                    -- ASCII equivalent
< = 3.14159265358979...
```

## graphing

```
> \graph(f, x=-5..5)
```

- Reuses the existing range syntax (`x=-5..5`) as the plotting domain — no new range concept needed.
- Renders **inline in the terminal** by default: detects sixel or kitty graphics protocol support and renders a real bitmap plot if available, falling back to a Unicode braille-pattern ASCII plot (denser and smoother than plain ASCII block characters) when the terminal doesn't support either.
- Can also export to a file instead of/as well as rendering inline — through the Python
  boundary, no special argument syntax needed:
```
> \py("matplotlib.pyplot.savefig")("plot.svg")
```
- There is deliberately **no `out=` argument syntax and no path-literal construct**. The pre-Python design scoped a narrow filename literal to I/O-boundary positions; that is obsolete now that `\py` exists — file paths are ordinary string literals passed to Python calls, and strings remain literals rather than values everywhere else (see `## vectors / matrices`).
- TODO: sampling strategy (fixed resolution vs. adaptive sampling near discontinuities/high-curvature regions) not yet decided. TODO: multi-function overlay syntax (plotting more than one `f` on the same axes) not yet decided.

## interpreter/compiler engine: interaction combinators (future direction)

This section records design thinking for a possible future evaluation engine — it is not
scheduled work and does not appear in `ROADMAP.md`. The current and durable engine lowers
`ad` to Python's own AST and executes on CPython (`adhoc/compiler.py` + `adhoc/driver.py`);
see `docs/architecture.md`. Nothing here should be
read as a near-term plan.

Rather than a tree-walking evaluator with a call stack and environment, `ad` could compile expressions into an **interaction net** (Lafont's interaction combinators) and execute by graph rewriting to normal form. The design below is from scratch, tailored to `ad`'s needs — HVM/HVM2 (Victor Taelin) is prior art/reference, not something to be ported directly.

**Core model:**
- The graph is made of **agents** connected by wires. Each agent has one *principal port* and zero or more *auxiliary* ports.
- Three base agent types (Lafont's original system, universal for combinatory-logic-style reduction): constructor (γ), duplicator (δ), eraser (ε).
- Reduction only happens where two agents' principal ports connect — an **active pair**. A small fixed rule table governs what happens:
  - **annihilation** — two agents of the *same* type meet: they cancel, their other wires reconnect directly to each other.
  - **commutation** — two agents of *different* types meet: they duplicate past each other.
- That's the whole reduction system: no global stack, no scheduler. Any active pair can be rewritten in any order and the result is the same normal form (confluence) — the property that makes this parallelizable later, even though the first implementation is single-threaded.

**Why this substrate fits `ad` specifically, not just generically:**
- **Laziness for infinite ranges** (`Σ(i=1..) 1/i^2`) falls out for free — parts of the net with no active pair just never reduce, no explicit thunk/suspension machinery needed.
- **`\simplify`/`\expand`/`\solve`/`\expr(...)` values** aren't a separate subsystem — an expression value *is* a sub-net, and simplification is just continuing reduction on it. Function application and symbolic simplification share one mechanism instead of two.
- **`\map`/`\fold`/composition/partial application** map directly onto duplicator/eraser agents (copy a subgraph N times / discard it), which is what argument usage in higher-order calls needs regardless of arity.

**Numeric extension agents:** pure Lafont combinators alone are impractically wasteful for representing numbers (unary/Church-style encoding). Following HVM's approach, the base three agents are extended with native fixed-arity numeric agents that wrap the exact-arithmetic tier system (bignum int/rational/symbolic/algebraic/RRA) directly — arithmetic runs as real operations on those representations, not as combinator reduction.

**Implementation scope, first pass:** single-threaded reference reduction engine — get sequential rewriting to normal form correct first. Parallel/concurrent active-pair rewriting (the main long-term payoff of this model) is a later optimization layered on top, not a correctness requirement for v1.

Agent names `γ`/`δ`/`ε` are internal implementation vocabulary only — they never appear in `ad` source code, so they're exempt from the "every unicode symbol needs an ASCII alternative" rule (that rule is about the language surface, not implementation terminology).

## outstanding issues (audit)

Found on a final pass through the doc — real contradictions/gaps, not just unfinished TODOs already called out inline. Resolved items keep their original wording for the record, with the resolution appended; open items carry a tracker ticket rather than being decided here.

1. **RESOLVED — piecewise braces contradiction.** The original `## conditionals` section still showed brace syntax while a later revision dropped braces. Fixed by merging into a single `## conditionals` section using the brace-free form throughout.

2. **RESOLVED — `=` overloaded across contexts.** Kept as a single token, disambiguated by position rather than adding a separate `==` (which was later itself removed as a declaration alias once the binding rule settled): statement-level bare-identifier `=` is declare-once-then-check (phase 0, revised by ticket #46); anywhere else in an expression `=` is plain boolean equality (subsuming what would otherwise be a separate comparison operator and `\solve`'s equation argument, which needs no special-casing); a small closed list of builtins (`\sum`, `\prod`, `\lim`, `\graph`) treat one specific argument as a binding rather than an equality. See `## equality and =`.

3. **RESOLVED — string-literal contradiction.** Originally resolved as a narrow `out=` path/filename literal scoped to I/O-boundary argument positions. Superseded once the Python interop landed (call arguments and comment-like statements only), then revised again: strings are now full values — they bind, concatenate with `+`, and compose `\py` paths — with escapes (`\" \\ \n \t`) in literals; file export still goes through `\py`. See `## graphing` and docs/grammar.md.

3b. **RESOLVED — application vs juxtaposition.** First resolved as *static* application: paren trailers attach only to name-ish heads, so `x(y+1)` applied rather than multiplied. Superseded by **dynamic juxtaposition**: a call whose head evaluates to a non-callable with exactly one argument falls back to the paper product (`x(y+1)` = `x*(y+1)`); callable heads apply; any other non-callable shape errors at the call's span. Number-headed parens (`2(x+1)`) never parse as calls. The price — identical text reading differently depending on bindings — was weighed against static's price (every arithmetic `x(...)` erroring) and accepted: the calculator audience expects the product reading first, and the surprise mode fails as a typed error, not silently. Function definitions lower into callable values; the ternary `c ? a : b` is the one conditional — lazy, with a parenthesized statement group as its multi-statement branch form. See docs/grammar.md.

4. **RESOLVED — multi-char keyword vs. implicit-multiplication ambiguity.** The very first example (`c = ab`) establishes that multiplication is implicit juxtaposition of single-char variables. Every multi-char name — not just the ones with a unicode counterpart — now takes a `\` sigil (`\pi`, `\sum`, `\sin`, `\solve`, ...), so it can never collide with a product of single-char variables. See `## keywords and the \ sigil`.

5. **RESOLVED — inconsistent ASCII-sugar calling convention.** Most ASCII alternatives are prefix-call form (`\sum(...)`, `\arr(...)`, `\circ(f, g)`); set operations stay infix (`a \cup b`, `2 \in s`) rather than being normalized to prefix — the `\` sigil already removes the ambiguity that would have motivated normalizing them, so the more readable infix form was kept deliberately.

6. **RESOLVED — no operator precedence/associativity table.** Added as `## precedence`. Juxtaposition binds tighter than `*`/`/`, looser than `^`, matching handwritten math (`1/2x` = `1/(2x)`).

7. **RESOLVED — rational display format.** Exact rationals display as a fraction (`a/b`); decimal display is reserved for the RRA tier, since a value only ever reaches RRA once it's no longer exact. The original decimal-always examples weren't a deliberate choice — one of them (`1/3` shown via RRA-style display) was a category error, since `1/3` never leaves the rational tier.

8. **RESOLVED — stray comment-marker variant.** Several examples used an em dash + hyphen instead of `--` for comments — an autocorrect artifact from the original stub, along with the curly quotes in the intro. Normalized to `--` and straight quotes throughout.
