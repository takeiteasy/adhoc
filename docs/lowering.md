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
| Application | `_e.app(head, args, kwargs, sid, spelling)` |
| Function definition | `_e.define`; separately compiled body |
| Ternary | `_e.if_expr` with lazy branch thunks |
| Python callable resolution | `_e.py`; results use the conversion matrix |

A callable head applies. A non-callable head with one positional argument and
no keywords multiplies; other non-callable calls fail at the call span.
Keyword arguments pass through to Python callables.

Calls create local frames with parent read-through. Body writes stay local;
recursion pre-binds the function in its call frame. Internal prelude and user
functions preserve booleans; external Python results use the
[conversion matrix](numerics.md#the-python-boundary-conversion-matrix).

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
| Range | `_e.range(start, second, end, sid)` |

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

## Outputs and unexpected errors

Each top-level statement has a generated line number and a corresponding span.
Unexpected exceptions map back through that table. A bare string statement
lowers to `pass`, preserving the line mapping without producing output.

Outputs accumulate in statement order. The REPL prints the last output;
script mode echoes every statement and stops at the first failure.
