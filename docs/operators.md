# Custom infix operators

`\infix(N)` defines a two-argument function and gives it infix syntax. Higher
precedence numbers bind tighter. A name and its paired spelling share one function.

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
| Punctuation | `\infix(11) <+>(a,b) = a+b` |
| Name with one paired spelling | `\infix(11) \blend, <+>(a,b) = a+b` |

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
| Punctuation | One contiguous run of `+ - * / ^ % @ < > & ~`, excluding reserved spellings |
| Paired declaration | One name and one glyph or punctuation spelling; both refer to the same function |

Letters, delimiters, built-in operators and `≡` are reserved. Previously
declared operator spellings are rejected. `\alias` and `\dual` cannot extend
a custom operator; use the paired declaration.

## Punctuation matching

The longest declared spelling matches at each punctuation position. Without a
match, built-in tokenization applies: `2*-3` means `2 * (-3)` unless `*-` is
declared. Whitespace separates tokens; `< + >` is distinct from `<+>`.

```text
\infix(11) ~(a,b) = a-b
\infix(11) ~~(a,b) = a+b
10~~3~2                 -- 11: ~~ matches before ~
```

| Reserved syntax | Rule |
|---|---|
| Built-in punctuation | `+ - * / ^ % @ < > <= >=` cannot be declared |
| Comments and lambda arrows | A spelling cannot contain `--` or `->` |
| Other syntax punctuation | `! = . : ?`, quotes, delimiters, commas, backticks, backslashes and placeholders are excluded |
| Strings and comments | Operator matching does not run inside either |

Unused single characters `&` and `~` are valid spellings. Declarations read the
whole punctuation spelling, so declaring a longer spelling after its prefix
works. A spelling affects its own function body and subsequent statements.

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

## Sections

Parenthesized sections fix one operand of any declared operator. They use the
same partial application as an explicit hole call.

```text
\infix(11) \blend, <+>(a,b) = a-b
(2 <+>)(3)                  -- -1: <+>(2,·)(3)
(<+> 2)(3)                  -- 1: <+>(·,2)(3)
(\blend 2)(3)               -- 1: the paired name works too
\map((<+> 2), ⟨1,2,3⟩)      -- ⟨-1, 0, 1⟩
```

| Rule | Example |
|---|---|
| Tighter operations fit inside an operand | `(<+> 2*3)(10)` returns `4` at level 11 |
| Group a looser left operand | At level 12, write `((1+2) <+>)` |
| Ordinary calls take priority before `(`, with or without spaces | `(<+> (2,3))` is a two-argument call |
| Use a hole call for a grouped right operand | `<+>(·,(1+2))` fixes `1+2` |
| Left sections preserve custom left association | `(10 <+> 3 <+>)(2)` returns `5` |
| Quotes display the hole call | `\expr((<+> 2))` displays `\expr(<+>(·, 2))` |

A right section reads its fixed operand as the declared operator's right-hand
side. Looser operations require the explicit hole form with grouping. Left
sections accept a tighter operand or a left-associated custom chain; looser
operations and mixed non-associative chains require parentheses.

The function and fixed operand evaluate when the section is created. Calling
the partial fills its one remaining argument. Built-in sections retain their
prefix exceptions: `(- 2)` is negation, and radicals are ordinary calls.

## Scope and function values

Declarations appear at top level, outside functions, groups, and quotes. They
affect their own body and subsequent statements. A trailing operator continues
onto the next line; a leading operator starts a new statement.

The REPL retains declarations across submissions. Each script and imported
module parses independently. Imports bring in function bindings, with ordinary
calls such as `\blend(2,3)`, but have [independent operator syntax](#limitations).[^registry]

A failed, incomplete, or cancelled parse registers nothing. After a successful
parse, syntax stays registered even if evaluation fails; an operator whose
function definition did not execute reports an unbound name when called.

Operators are ordinary function values: `f = \blend`, `f = ⊕`, `⊕(2,3)`, and
`\blend(·,2)` follow normal function behavior. Quoted infix expressions and
reflected bodies display as ordinary calls, retaining the written operator
spelling.

## Limitations

- Imports carry function bindings, but do not export infix declarations or paired spellings.
- Each paired declaration has one alternate spelling; aliases cannot add further spellings.

[^registry]: The Python APIs `parse_program`, `compile_source`, and `run_source`
    accept `operators=`. Pass the same dictionary across calls to preserve syntax;
    it maps written spellings to `(canonical_name, precedence)` pairs. Omit it for
    independent source units. Publication follows the same parse-success rule as
    `aliases=`. The lexer API `tokenize(source, operators=spellings)` accepts an
    iterable of declared spellings for longest-match punctuation tokenization.
