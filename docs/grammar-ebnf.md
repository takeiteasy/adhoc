# Formal grammar (EBNF)

These productions describe the parser syntax. See the [grammar reference](grammar.md)
for lexical rules, precedence, examples and evaluation semantics.

```
program    ::= statement (sep statement)* sep? ;
sep        ::= newline-run | ";" ;    -- a ";" after a newline run is one separator too
statement  ::= func-def
             | let-stmt
             | import-stmt
             | pyimport-stmt
             | spelling-directive
             | infix-stmt
             | string
             | name "=" expr
             | expr ;
let-stmt    ::= "\let" name "=" expr
             | "\let" name "(" params? ")" "=" statement (";" statement)* ;
import-stmt   ::= "\import" "(" string (":" member ("," member)*)? ")" ;
pyimport-stmt ::= "\pyimport" "(" string ":" member ("," member)* ")" ;
member        ::= identifier | "\"-name ;
spelling-directive ::= alias-stmt | dual-stmt ;
alias-stmt  ::= "\alias" name "," single-char ("," single-char)* ;
dual-stmt   ::= "\dual" name "," single-char params? "=" statement (";" statement)* ;
single-char ::= identifier ;                (* aliases are one-character letters *)
name        ::= identifier | "\"-name ;
infix-stmt  ::= "\infix" "(" integer ")" infix-head
                "(" name "," name ")" "=" statement (";" statement)* ;
infix-head ::= "\"-name ("," operator-symbol)? | operator-symbol ;
operator-symbol ::= unused-mathematical-symbol | punctuation-operator ;
punctuation-operator ::= unreserved-run-of-"+-*/^%@<>&~" ;
declared-custom-operator ::= registered-backslash-name | registered-operator-symbol ;

expr       ::= ternary ;
ternary    ::= iff ("?" ternary ":" ternary)? ;   (* right-associative *)
iff        ::= implies (("↔" | "\\iff") implies)? ;      (* non-associative *)
implies    ::= or (("→" | "\\implies") implies)? ;       (* right-associative *)
or         ::= and (("∨" | "\\or") and)* ;
and        ::= not (("∧" | "\\and") not)* ;
not        ::= ("¬" | "\\not") not | range ;
range      ::= comparison (".." comparison? | "," comparison ".." comparison?)? ;
                                           (* the "," form is not read inside lists *)
comparison ::= angle (cmp-op angle)? | angle ("≡" | "\\equiv" | "==") angle congruence-suffix | angle ("∈" | "\\in" | "∉" | "\\notin") range-tail ;
congruence-suffix ::= "(" ("mod" | "\\mod") expr ")" ;
range-tail ::= additive (".." additive? | "," additive ".." additive?) ;   (* membership only *)
cmp-op     ::= "=" | "<" | ">" | "<=" | "≤" | ">=" | "≥" | "≠" | "\\neq" | "≈" | "\\approx"
             | "∈" | "\\in" | "∉" | "\\notin" | "⊆" | "\\subseteq" | "⊂" | "\\subset"
             | "⊇" | "\\supseteq" | "⊃" | "\\supset" ;
angle      ::= additive (("∠" | "\\angle") additive)? ;   (* polar form r∠θ *)
additive   ::= multiplicative (("+" | "-" | "∪" | "\\cup" | "∖" | "\\setminus") multiplicative)* ;
multiplicative
           ::= juxtaposed (("*" | "/" | "\\per" | "@" | "\\contract" | "×" | "\\times" | "⊗" | "\\otimes" | "∩" | "\\cap" | "∘" | "\\circ" | "%" | "\\mod") juxtaposed)* ;
juxtaposed ::= unary unary* ;              (* implicit multiplication *)
unary      ::= "-" unary | power ;
radical    ::= "√" unary ;                 (* prefix spelling of \sqrt(...) *)
nth-root   ::= ("∛" | "∜") unary ;         (* prefix spelling of \root(x, 3) / \root(x, 4) *)
power      ::= postfix ("^" unary)? ;      (* right-associative *)
postfix    ::= atom trailer* ;             (* application — see below *)
trailer    ::= "(" args? ")" | "[" selector ("," selector)* "]" | "'" | "ᵀ" | "!" | "‼" | "!!" | superscript
             | superscript "(" args? ")" ;   (* function power, on a name head only *)
selector   ::= ".." | expr ;                (* bare .. selects a whole axis *)
superscript ::= (superscript-glyph)+ ;         (* sugar for "^" with the run read as an expression *)
args       ::= arg ("," arg)* ;
arg        ::= expr | string | kwarg | hole | operator ;   (* holes and operators only as a whole argument *)
hole       ::= "·" | "⋅" | "_" ;
operator   ::= "+" | "-" | "*" | "/" | "^" | "@" | "×" | "⊗" | "∘" | "∪" | "∩" | "∖" | "<" | ">" | "<="
             | ">=" | "≤" | "≥" | "≠" | "≈" | "∈" | "∉" | "⊆" | "⊂" | "⊇" | "⊃" | "√" | "∛" | "∜"
             | "!" | "‼" | "\\contract" | "\\times" | "\\otimes" | "\\circ" | "\\cup" | "\\cap" | "\\setminus" | "\\in"
             | "\\notin" | "\\subseteq" | "\\subset" | "\\supseteq" | "\\supset" | "\\neq" | "\\approx" | declared-custom-operator ;
kwarg      ::= (identifier | "\"-name) "=" (expr | string) ;
func-def   ::= name "(" params? ")" "=" statement (";" statement)* ;
params     ::= name ("," name)* ;
atom       ::= number | string | identifier | "\"-name | "(" expr ")" | "(" sequence ")"
              | "(" operator ")" | "(" operator operand ")" | "(" operand operator ")"
              | lambda | arrow-lambda | radical | delimited | quote | tensor | array | set | piecewise | builder ;
delimited  ::= "⌊" expr "⌋" | "⌈" expr "⌉" | "|" expr "|" | "‖" expr "‖" ;
tensor     ::= "[" expr ("," expr)* "]"
             | "[" expr ("," expr)* (";" expr ("," expr)*)* ";"? "]" ;
set        ::= "{" (expr ("," expr)*)? "}" ;
piecewise  ::= "{" (expr ":" expr sep)* (expr ":" expr | expr) sep? "}" ;
builder    ::= "{" name "∈" expr "|" guards "}" | "{" expr "|" generator ("," clause)* "}" ;
generator  ::= name "∈" expr ;
clause     ::= generator | expr ;
guards     ::= expr ("," expr)* ;
array      ::= ("⟨" | "#[") (expr ("," expr)*)? ("⟩" | "]")
             | "\\arr" "(" (expr ("," expr)*)? ")" ;
quote      ::= ("\\expr" | "`") "(" expr ")"
             | ("\\expr" | "`") "(" equation ")"
             | ("\\expr" | "`") "(" "(" sequence ")" ")" ;
equation   ::= expr "=" expr | "(" equation ")" ;
eval       ::= "\\eval" "(" expr ("," kwarg)* ")" ;
sequence   ::= statement (sep statement)* sep? ;
lambda     ::= ("\λ" | "\fn") "(" params? ")" expr ;
arrow-lambda ::= (name | "(" params? ")") ("↦" | "->" | "\mapsto") expr ;
```

Statement heads `name =` and `name(params) =` take priority over expression
equality; a call argument beginning `name =` takes priority as a named argument.
Their right-hand sides are expressions, including equality.

Parentheses select `expr` unless a statement separator follows a complete
expression or the head is an explicit statement form such as `\let`.
Newlines after operators continue the expression. Comparison operators,
including equality, do not chain without parentheses.

An explicit equation quote's single outer `=` separates two full `expr`
productions; it is not consumed as an ordinary comparison. Equality nested
inside either side uses comparison precedence. See
[quotes and evaluation](grammar.md#quotes-and-evaluation).

Declared custom spellings participate in the infix production at their declared
precedence and in both section productions. A custom spelling followed by `(`
parses as an ordinary call, regardless of spaces; use an explicit hole call for
a grouped right-section operand. See [custom operator sections](operators.md#sections).

## Special forms

These forms bind a name rather than accepting an ordinary first argument.

```
fold       ::= ("\sum" | "\prod" | "Σ" | "Π") "(" ident ("=" | "∈") expr ")" expr ;
quantifier ::= ("\forall" | "∀" | "\exists" | "∃") "(" ident ("=" | "∈") expr ")" expr ;
limit      ::= "\lim" "(" ident "=" expr ")" expr ;
diff       ::= ("\diff" | "∂") "(" ident "=" expr ("," expr)? ")" expr ;
integral   ::= ("\int" | "∫") "(" ident "=" expr ")" expr ;
```
