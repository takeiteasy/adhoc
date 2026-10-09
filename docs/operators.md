# Custom infix operators

`\infix(N)` defines a two-argument function and gives it infix syntax. Higher
precedence numbers bind tighter. A name and its paired glyph share one function.

```text
\infix(11) \blend, ⊕(a,b) = a+b
2 ⊕ 3*4                 -- 14: multiplication binds tighter
\blend(2,3)             -- 5: ordinary function call
f = ⊕                   -- the same function as \blend
\map(f(·,2), ⟨1,2⟩)     -- ⟨3, 4⟩
```

## Declarations

| Form | Example |
|---|---|
| Backslash name | `\infix(11) \blend(a,b) = a+b` |
| Mathematical glyph | `\infix(11) ⊕(a,b) = a+b` |
| Name with one paired glyph | `\infix(11) \blend, ⊕(a,b) = a+b` |

Use a literal integer precedence and exactly two distinct parameter names. The
body follows ordinary function rules: parameters and local bindings stay local,
recursion works, and semicolon-separated statements form a body. Both operands
evaluate before the function runs. Built-in logical operators keep their lazy
behavior.

### Allowed spellings

| Spelling | Requirement |
|---|---|
| Glyph | One unused non-ASCII Unicode mathematical symbol (`Sm`) |
| Backslash name | Unprotected, without an existing alias or operator declaration |
| Paired declaration | One name and one glyph; both refer to the same function |

Letters, delimiters, built-in operators and `≡` are reserved. Previously
declared operator spellings are rejected. `\alias` and `\dual` cannot extend
a custom operator; use the paired declaration.

## Precedence and grouping

| Allowed level | Built-ins at that level |
|---|---|
| 3 | `↔` |
| 4 | `→` |
| 5 | `∨` |
| 6 | `∧` |
| 9 | Comparisons and membership |
| 10 | `∠` |
| 11 | `+`, `-`, `∪`, `∖` |
| 12 | `*`, `/`, tensor operations, `%`, `∩`, `∘` |
| 15 | `^` |

Custom operators associate left: `a ⊕ b ⊕ c` means `(a ⊕ b) ⊕ c`. Built-ins
retain their own association. At level 15, `2 ⊕ 3^2` groups as `(2 ⊕ 3)^2`,
whereas `2^3 ⊕ 2` groups as `2^(3 ⊕ 2)`. Chains involving a non-associative
built-in at the same level require parentheses: at level 9, write `(a ⊕ b) < c`.
See the [full precedence table](grammar.md#precedence-table).

## Scope and function values

Declarations appear at top level, outside functions, groups, and quotes. They
affect their own body and subsequent statements. A trailing operator continues
onto the next line; a leading operator starts a new statement.

The REPL retains declarations across submissions. Each script and imported
module parses independently. Imports bring in function bindings, with ordinary
calls such as `\blend(2,3)`, but do not export infix syntax or paired glyphs.[^registry]

A failed, incomplete, or cancelled parse registers nothing. After a successful
parse, syntax stays registered even if evaluation fails; an operator whose
function definition did not execute reports an unbound name when called.

Operators are ordinary function values: `f = \blend`, `f = ⊕`, `⊕(2,3)`, and
`\blend(·,2)` follow normal function behavior. Quoted infix expressions and
reflected bodies display as ordinary calls, retaining the written operator
spelling.

## Limitations

- Punctuation sequences such as `<+>` are deferred —
  [#124](https://todo.sr.ht/~takeiteasy/adhoc/124).
- Custom operator sections such as `(⊕ 2)` and `(2 ⊕)` are deferred; use
  `⊕(·,2)` and `⊕(2,·)` — [#125](https://todo.sr.ht/~takeiteasy/adhoc/125).

[^registry]: The Python APIs `parse_program`, `compile_source`, and `run_source`
    accept `operators=`. Pass the same dictionary across calls to preserve syntax;
    it maps written spellings to `(canonical_name, precedence)` pairs. Omit it for
    independent source units. Publication follows the same parse-success rule as
    `aliases=`.
