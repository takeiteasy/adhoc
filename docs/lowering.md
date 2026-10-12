# Runtime lowering

Every operation on a user value lowers to an `Engine` call with a source-span ID.
The user environment is a separate dictionary; Python execution globals hold the
engine and compiled code. See the [architecture overview](architecture.md) for
the pipeline and package layout.

## Variables and calls

| Language operation | Engine call or behavior |
|---|---|
| Variable read | `_e.var` |
| Backslash-name read | `_e.bref` |
| Bind or check | `_e.assign`; `\let` selects fresh-only mode |
| Equality expression or evaluated equation quote | `_e.eq(lhs, rhs, sid)`; value equality without binding |
| Application | `_e.app(head, args, kwargs, sid, spelling)` |
| Function clause | `_e.define`; compiled pattern values and a separately compiled body |
| Ternary | `_e.if_expr` with lazy branch thunks |
| Python callable resolution | `_e.py`; results use the conversion matrix |

A callable head applies. A non-callable head with one positional argument and
no keywords multiplies; other non-callable calls fail at the call span.
Keyword arguments pass through to Python callables and prelude functions that
accept them, such as `\solve` with `\domain="real"`.

Named calls match ordered clause patterns before creating a local frame; only the
selected body runs. Clauses retain their compiled bodies, source and defining
engines. Additions preserve callable identity and require the original name and
defining environment dictionary. `\let` selects fresh-only declarations.

Calls create local frames with parent read-through. Body writes stay local;
recursion pre-binds the function in its call frame. Internal prelude and user
functions preserve booleans; external Python results use the
[conversion matrix](numerics.md#the-python-boundary-conversion-matrix).

`\tex` reads the calling frame when rendering quotes. The call context follows
aliases and higher-order application and is restored after each call. Rendering
a function reads its defining frame and masks parameters and binders.

## Imports

| Form | Engine call |
|---|---|
| `\import` | `_e.import_(path, members, sid, member_spellings)` |
| `\pyimport` | `_e.pyimport(...)` |

The root engine holds the session module registry, import base directory and
in-progress import chain. Child frames and imported module engines share this
state. It supplies caching, cycle errors and resolution relative to the
importing file. See [import rules](grammar.md#modules-and-imports).

## Collections

| Operation | Engine call |
|---|---|
| Tensor literal | `_e.tensor(items, row_length, sid)` |
| Index | `_e.index(head, items, sid, spelling)` |
| Whole-axis selector `..` | `None` within the index selector tuple |
| Transpose | `_e.transpose(value, sid)` |
| Contraction `@` | `_e.dot` |
| Array literal | `_e.array(items, sid)` |
| Set and set operations | `_e.set_`, `_e.union`, `_e.intersect`, `_e.setminus`, `_e.member`, `_e.subseteq` |
| Range or infinite interval | `_e.range(start, second, end, sid)`; infinite endpoints produce a non-iterable interval |

`\arr(...)` rewrites to an array node during parsing. Set construction
deduplicates through numeric-tier equality. A numeric index head multiplies;
a non-numeric, non-indexable head fails.

Collection indexing normalizes range selectors to finite, 1-based Python ranges
using the axis length. Tensor selection retains range axes and removes integer
axes; array slicing preserves the array kind. Open ranges never iterate infinitely.

Tensor arithmetic uses `tensor.map1` and `map2` through the numeric helpers.
Folds, product fallback and function calls share that broadcasting behavior.
Ranges store endpoints and a step without materializing their contents; iteration
computes each next value through numeric operations.

## Binders

Folds and limits compile their bodies into the unit's definitions table, then
emit `_e.fold(...)` or `_e.limit(...)`. Each term or probe runs in a fresh child
frame with parent read-through and local writes. Accumulation and convergence
checks remain in `runtime.py`. See [convergence](numerics.md#convergence).

## Graph sampling

`Graph` lowers to `_e.graphs(...)` with per-target source-span IDs, axis metadata,
shared bound and options. Each target retains its expression/callable mode. Expression targets compile once into the definitions table; every
sample uses a fresh child frame. Callable targets evaluate once and each sample
uses the existing application path. `syntax.free_names` determines expression
mode during parsing, respecting lexical binders and excluding quoted syntax.

`runtime.py` validates inputs and widens real values. The sampler in `graph.py`
operates on floats supplied by that seam and returns immutable graph data.
`NumericDomainError` is a `NumError` subtype; `EvalError.domain` preserves its
category through wrapping so mathematical failures become gaps while other
errors retain their spans.

## Outputs and unexpected errors

Each top-level statement has a generated line number and a corresponding span.
Unexpected exceptions map back through that table. A bare string statement
lowers to `pass`, preserving the line mapping without producing output.

Outputs accumulate in statement order. The REPL prints the last output;
script mode echoes every statement and stops at the first failure.

## Set-builders

Generators and guards compile once as ordered clauses. Each domain evaluates
with earlier bindings, and each guard filters its current branch before later
domains evaluate. The result expression sees every bound name; bindings stay
local and results deduplicate in first-seen order.

## Quantities

Unit names use ordinary protected-name lookup; `\per` lowers as division.
Numeric helpers check dimensions before operating on canonical magnitudes.
Calculus binds dimensioned probes and checks sample dimensions; matrix helpers
factor out a shared dimension before calling numeric backends.
