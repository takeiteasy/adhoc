"""Recursive-descent / precedence-climbing parser over the token stream, matching the
precedence table in docs/grammar.md:

    program     ::= statement (";" statement)* ;
    statement   ::= func-def | let-stmt | string | name "=" expr | expr ;
    expr        ::= ternary ;
    ternary     ::= range ("?" ternary ":" ternary)? ;   -- the lazy conditional
    additive    ::= multiplicative (("+" | "-") multiplicative)* ;
    multiplicative ::= juxtaposed (("*" | "/") juxtaposed)* ;
    juxtaposed  ::= unary unary* ;          -- implicit multiplication
    unary       ::= "-" unary | power ;
    radical     ::= "√" unary ;   -- prefix spelling of \\sqrt(...): `√2^2` is √(2²),
                                  -- `2^√2` works, `√2 3` is `(√2)*3`
    power       ::= postfix ("^" unary)? ;  -- right-associative
    postfix     ::= atom ("(" args ")")* ;  -- trailers attach only to name-ish heads
    args        ::= (expr | string | kwarg) ("," ...)* ;   kwarg ::= name "=" value ;
    atom        ::= number | string | identifier | "\\"-name | "(" expr ")"
                  | "(" operator ")"   -- an operator value; also a whole call argument
                  | "(" operator operand ")" | "(" operand operator ")" ;   -- a section

`power`'s exponent recurses into `unary`, not `power` — that's what makes `2^-1` parse
(unary minus binds inside the exponent) and `2^3^2` right-associate. The base of `^` is a
postfix node, so `-2^2` is `-(2^2)` and `f(x)^2` squares the result. The radical `√` is
the one prefix operator: it sits at the unary level and rewrites to a `\\sqrt(...)`
application node, so evaluation is identical to the ASCII call form — `√2 3` is `(√2)*3`,
`√2^2` reads √(2²) like the overbar visually extends, and `√2√3` juxtaposes into
`√2*√3`.

Postfix application is *syntactically* name-headed: a `(…)` trailer attaches only when the
head so far is a name-ish node (`Var`, `BackslashRef`, or another `Call`). Number-headed
parens never apply — `2(x+1)` still parses as juxtaposed multiplication. Whether a parsed
call applies or falls back to multiplication is decided at evaluation (dynamic
juxtaposition, docs/grammar.md). Strings are values: one alone may still be a statement
(echoed to nobody, comment-like) and one is a whole call argument; inside expressions they
are ordinary atoms — `"a" + "b"` concatenates, and a string reaching any other operator
fails as the usual typed "strings are not numbers" at evaluation. The function
definition shape `f(x) = body` is recognized at statement level and parsed into `FuncDef`;
function bodies may contain semicolon-separated statements. `\\let name = expr` is the
fresh-only spelling of an assignment; `\\let f(params) = body` reuses the top-level
function-definition path.

Two builtin heads are *special forms* (DESIGN.md, "equality and =" case 3): their first
argument is a binding, not an application argument. `\\sum`/`\\prod`/`Σ`/`Π` parse
`(i=a..b)` into a range and rewrite to `Fold`; `\\lim(x=a)` rewrites to `Limit`. In both,
the body extends greedily over the rest of the current expression, up to the enclosing
delimiter — parenthesize to end it earlier. Recognition commits on the `(ident =` shape
alone (bare `=` cannot occur inside a general expression); any other use of those heads
goes through ordinary application parsing.

**Newlines are statement separators, everywhere.** The lexer emits a `Newline` token
per line break, inside parentheses and out. The parser skips newline runs wherever an
*operand* is expected — a statement or expression continues onto the next line
mid-expression (`1 +` NL `2` is one sum, an argument may start on the line after its
`,`) — but where an expression is complete, a newline separates statements. A
**parenthesized group** is therefore the multi-line statement form:
`( statement (sep statement)* )` with newline runs or a single `;` as separators
produces the same `Seq` node at top level (no scope of its own) and is legal anywhere
an expression is — def bodies, lambda bodies, ternary branches. A **lambda**
`\λ(params) body` (ASCII `\fn(params) body`) parses into `Lambda`; its body follows
the same greedy rule as fold/limit bodies (a parenthesized group bounds it
explicitly), and a parenthesized lambda is a name-ish head so `(\fn(x) x)(5)`
applies.

Spans are tagged at each node's *construction* site, not on the way out of each parse
call: the `(expr)` branch of atoms returns the inner node unchanged, and tagging on unwind
would clobber that inner node's own (narrower) span with the paren-inclusive one.
"""

from contextlib import contextmanager
from dataclasses import replace

from .lexer import (
    At,
    Backtick,
    Backslash,
    Colon,
    Comma,
    Bang,
    Caret,
    NthRoot,
    DoubleBang,
    Superscript,
    Eq,
    Eof,
    Ident,
    LAngle,
    LBrace,
    LBracket,
    LexError,
    LParen,
    Less,
    LessEq,
    Minus,
    Newline,
    Number,
    Placeholder,
    Plus,
    Prime,
    Question,
    RAngle,
    Radical,
    RBrace,
    RBracket,
    RParen,
    Semi,
    InfixOp,
    Slash,
    Star,
    Str,
    Token,
    Greater,
    GreaterEq,
    HashBracket,
    DotDot,
    UnterminatedString,
    tokenize,
)
from .runtime import PRELUDE, RESERVED_NAMES
from .span import Span
from .syntax import (
    is_short_name,
    ArrayLit,
    Assign,
    BackslashRef,
    BinOp,
    BinOperator,
    Call,
    Compare,
    CompareOperator,
    Fold,
    FuncDef,
    Hole,
    IfExpr,
    Import,
    Index,
    KwArg,
    Lambda,
    Limit,
    Node,
    NoOp,
    NumLit,
    OP_SYMBOLS,
    OpRef,
    PyImport,
    Quote,
    Eval,
    Range,
    Seq,
    SetLit,
    StrLit,
    TensorLit,
    Transpose,
    PowCall,
    UnOp,
    UnaryOperator,
    Var,
)


class ParseError(Exception):
    def __init__(self, msg: str, span: Span):
        super().__init__(msg)
        self.msg = msg
        self.span = span


class IncompleteInput(ParseError):
    """The unexpected token was EOF — callers (the REPL) offer a continuation prompt
    rather than reporting a hard error. A subtype in spirit: code that only cares about
    "parsing failed" can catch ParseError and get the same msg/span fields."""


_ATOM_STARTERS = (Number, Ident, Backslash, Backtick, LParen, LBracket, LAngle, LBrace,
                  HashBracket, Str, Radical, NthRoot)

_NO_HOLE_FORMS = frozenset({"py", "arr", "eval"})

# Backslash names that are infix operators, never atoms: they end a juxtaposition run
# and cannot be bound or used as values.
_OPENERS = (LBracket, HashBracket, LBrace, LAngle)
_CLOSERS = (RBracket, RBrace, RAngle)

# Operators that can stand as function values, by token (`(+)`, or a whole call
# argument like `\\fold(+, xs)`); infix-only spellings go through `_infix_name`.
_SYMBOL_OPERATORS = {Bang: "fact", DoubleBang: "dfact", Plus: "add", Minus: "sub", Star: "mul", Slash: "div", Caret: "pow",
                     Less: "lt", LessEq: "le", Greater: "gt", GreaterEq: "ge"}
_INFIX_OPERATORS = {"contract": "dot", "cup": "union", "cap": "intersect",
                    "setminus": "setminus", "circ": "compose", "in": "member",
                    "subseteq": "subseteq", "neq": "ne", "approx": "approx", "notin": "notmember",
                    "subset": "subset", "supseteq": "supseteq", "supset": "supset"}

# Operator key -> the parser level that reads its right-hand side, which is the extent of
# a section's operand: `(+ 1*2)` fixes `1*2`, `(* 1 + 2)` is a parse error.
_ADDITIVE_KEYS = frozenset({"add", "sub", "union", "setminus"})
_MULTIPLICATIVE_KEYS = frozenset({"mul", "div", "dot", "intersect", "compose"})
_COMPARE_KEYS = frozenset({"lt", "le", "gt", "ge", "member", "subseteq", "ne", "approx",
                          "notmember", "subset", "supseteq", "supset"})

_ADDITIVE_INFIX = {"cup": BinOperator.UNION, "setminus": BinOperator.SETMINUS}
_MULTIPLICATIVE_INFIX = {"contract": BinOperator.DOT, "cap": BinOperator.INTERSECT,
                         "circ": BinOperator.COMPOSE}
_COMPARE_INFIX = {"in": CompareOperator.IN, "subseteq": CompareOperator.SUBSETEQ,
                  "neq": CompareOperator.NE, "approx": CompareOperator.APPROX,
                  "notin": CompareOperator.NOTIN, "subset": CompareOperator.SUBSET,
                  "supseteq": CompareOperator.SUPSETEQ, "supset": CompareOperator.SUPSET}
_INFIX_NAMES = frozenset(_ADDITIVE_INFIX) | frozenset(_MULTIPLICATIVE_INFIX) | frozenset(_COMPARE_INFIX)

# Lambda heads: the unicode spelling and the ASCII one. A `\`-name head followed by
# a parameter-list paren parses as an anonymous function (docs/grammar.md, `## Lambdas`);
# without the paren the head is an ordinary unbound name (the `\py` usage-error pattern).
_LAMBDA_HEADS = ("λ", "fn")

# Seed of the session alias map (short spelling → canonical name): the unicode
# fold heads and π, expressed as ordinary `\alias`-mechanism entries instead of
# hardcoded parser/prelude special cases (docs/grammar.md, `## Name aliases`).
ALIAS_SEED: dict[str, str] = {"Σ": "sum", "Π": "prod", "π": "pi", "∅": "emptyset"}


def _spelling(tok: Ident | Backslash) -> str:
    if isinstance(tok, Ident):
        return tok.spelling or tok.ch
    return f"\\{tok.name}"


class _Parser:
    def __init__(self, tokens: list[Token], aliases: dict[str, str] | None = None,
                 source: str = ""):
        self.tokens = tokens
        self.source = source
        self.pos = 0
        # Working alias map: the session's map (if given) layered over the seed.
        # `\alias`/`\dual` declarations mutate this dict; parse_program merges it
        # back into the caller's map only on a fully successful parse.
        self.aliases = dict(ALIAS_SEED)
        if aliases:
            self.aliases.update(aliases)
        # Names a spelling declaration may not repurpose: the prelude and reserved
        # statement forms.
        self.protected = frozenset(PRELUDE) | RESERVED_NAMES
        # Statement nesting depth: `\alias`/`\dual` are top-level directives —
        # declaring one inside a function body or group would take effect at
        # parse time whether or not the body ever runs.
        self.depth = 0
        # A group at the start of a top-level statement is flattened, so it admits
        # top-level `\let` function definitions; expression-position groups do not.
        self._statement_start = 0
        self._section_operand: Node | None = None
        self._top_level_statement = False
        # Set by `_skip_newlines`, reset by statement lists around each
        # statement: "a line break was consumed since the last statement ended".
        self._nl = False
        # True while parsing the items of a comma-separated list (call arguments,
        # tensor/array/set literals, index brackets): there `,` always separates
        # items, so `a, b..c` is never a stepped range (docs/grammar.md, `## Ranges`).
        self._in_list = False

    @contextmanager
    def _list_context(self, in_list: bool):
        saved, self._in_list = self._in_list, in_list
        try:
            yield
        finally:
            self._in_list = saved

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def peek2(self) -> Token:
        return self.tokens[min(self.pos + 1, len(self.tokens) - 1)]

    def look(self, k: int) -> Token:
        """The token `k` positions past the cursor; always defined (clamped to Eof)."""
        return self.tokens[min(self.pos + k, len(self.tokens) - 1)]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos + 1 < len(self.tokens):
            self.pos += 1
        return tok

    def _skip_newlines(self) -> None:
        """Consume a run of Newline tokens. Called where an *operand* is expected —
        a statement or expression continues onto the next line mid-expression — and
        at statement boundaries that treat a newline run as one separator. Operator
        positions deliberately do NOT skip: at a statement boundary the newline wins,
        so `x = 1` NL `+ 2` is two statements (the second an error), never a join.
        Sets `_nl` so statement lists (top level, groups) can tell that the
        statement's own tail consumed the line break (a committed range `1..` ends
        at the newline)."""
        while isinstance(self.peek(), Newline):
            self._nl = True
            self.advance()

    def error_at_current(self, msg: str) -> ParseError:
        tok = self.peek()
        if isinstance(tok, Eof):
            return IncompleteInput(msg, tok.span)
        return ParseError(msg, tok.span)

    def expect(self, cls: type, what: str) -> Token:
        # Lenient across line breaks: a delimiter may sit on the next line
        # (`c ? a NL : b`). Inside parentheses newlines are suppressed anyway, so
        # this only ever skips statement-level breaks.
        self._skip_newlines()
        if isinstance(self.peek(), cls):
            return self.advance()
        found = self.peek().describe
        raise self.error_at_current(f"expected {what}, found {found}")

    def _is_atom_starter(self) -> bool:
        tok = self.peek()
        if isinstance(tok, Backslash) and tok.name in _INFIX_NAMES:
            return False
        return isinstance(tok, _ATOM_STARTERS)

    # -- alias normalization (docs/grammar.md, `## Name aliases`) ---------------
    # A single-character spelling with an alias entry reads as its canonical name
    # everywhere a name is consumed: Σ IS \sum, π IS \pi, not two names that happen
    # to hold one value. `\`-names are already canonical and pass through.

    def _canonical(self, spelling: str) -> str:
        """The canonical name for a single-character spelling after alias
        resolution; backslash names are canonical by construction."""
        return self.aliases.get(spelling, spelling)

    def _name_node(self, spelling: str, span: Span) -> Node:
        """The read-side node for a name spelling post-normalization: a
        single-character canonical name is a Var, a multi-character one a
        BackslashRef — the language's own long/short name convention."""
        canonical = self._canonical(spelling)
        if is_short_name(canonical):
            return Var(ch=canonical, span=span, spelling=spelling)
        return BackslashRef(name=canonical, span=span, spelling=spelling)

    # program ::= statement (sep statement)* ;
    # sep ::= newline run | ";" — newlines are whitespace-carved statement boundaries
    # at top level exactly like semicolons (a source may separate statements with
    # either); two adjacent `;` stay an error, blank lines are free.
    def program(self) -> Node:
        self._skip_newlines()
        self._top_level_statement = True
        self._statement_start = self.pos
        statements = [self.statement(allow_let_function=True)]
        while True:
            sep = False
            while isinstance(self.peek(), Newline):
                self.advance()
                sep = True
            if isinstance(self.peek(), Semi):
                sep = True
                self.advance()
                self._skip_newlines()
            if not sep or isinstance(self.peek(), Eof):
                break
            self._statement_start = self.pos
            statements.append(self.statement(allow_let_function=True))
        if not isinstance(self.peek(), Eof):
            found = self.peek().describe
            raise self.error_at_current(f"unexpected token {found}")
        if len(statements) == 1:
            return statements[0]
        span = statements[0].span.to(statements[-1].span)
        return Seq(statements=tuple(statements), span=span)

    # statement ::= func-def | let-stmt | string
    #             | name "=" expr | expr ;
    # Statement heads are line-bound: the two-token looks aheads (peek2) see the
    # token immediately after the head, so a statement head and its syntax belong
    # on one line. Mid-statement, expression parsing continues across lines.
    def statement(self, allow_let_function: bool = False) -> Node:
        tok = self.peek()
        if isinstance(tok, Str) and isinstance(self.peek2(), Semi | Eof | Newline):
            # A string alone is a statement — ignored like a comment (docs/grammar.md).
            # A string followed by anything else (`"a" + "b"`) is an ordinary
            # expression whose atom happens to be a string.
            self.advance()
            return StrLit(text=tok.text, span=tok.span)
        if (
            isinstance(tok, Backslash)
            and tok.name in ("import", "pyimport")
            and isinstance(self.peek2(), LParen)
        ):
            return self._import_statement(tok)
        if (
            isinstance(tok, Backslash)
            and tok.name in ("alias", "dual")
            and isinstance(self.peek2(), (Ident, Backslash))
        ):
            return self._spelling_statement(tok.name)
        if isinstance(tok, Backslash) and tok.name == "let":
            return self._let_statement(allow_let_function)
        if isinstance(tok, Backslash):
            # `\fn(params)` is a lambda — never a definition named `fn`
            # (`\fn(x) = …` dies inside the lambda parse on the stray `=`).
            if tok.name in _LAMBDA_HEADS and isinstance(self.peek2(), LParen):
                return self.expr()
        if isinstance(tok, (Ident, Backslash)):
            if isinstance(self.peek2(), Eq):
                ident_tok = self.advance()
                self.advance()  # `=` — declare-once-then-check, there is no other spelling
                value = self.expr()
                span = ident_tok.span.to(value.span)
                name = (self._canonical(ident_tok.ch) if isinstance(ident_tok, Ident)
                        else ident_tok.name)
                return Assign(name=name, value=value, span=span,
                              spelling=_spelling(ident_tok))
            if isinstance(self.peek2(), LParen):
                saved = self.pos
                defn = self._func_def_or_none()
                if defn is not None:
                    return defn
                self.pos = saved  # not the def shape after all — reparse as an application
        return self.expr()

    # import-stmt ::= "\\import" "(" string (":" member ("," member)*)? ")" ;
    # pyimport-stmt ::= "\\pyimport" "(" string ":" member ("," member)* ")" ;
    # Statement-level only: an import binds names and produces no output, so it has
    # no value — in expression position the head stays an ordinary unbound name and
    # fails at evaluation with a usage message (the `\py` pattern). Member
    # tokens are ordinary name spellings; the colon commits the member list, and
    # `\pyimport` requires it (there is no module value to bind).
    def _import_statement(self, head: Backslash) -> Node:
        self.advance()  # the `\import` / `\pyimport` token
        self.expect(LParen, "`(`")
        path_tok = self.peek()
        if not isinstance(path_tok, Str):
            what = "module" if head.name == "pyimport" else "ad file"
            raise self.error_at_current(
                f"expected a string literal naming the {what}, found {path_tok.describe}")
        self.advance()
        members: list[str] = []
        member_spellings: list[str] = []
        if isinstance(self.peek(), Colon):
            self.advance()
            while True:
                tok = self.peek()
                if isinstance(tok, (Ident, Backslash)):
                    members.append(self._canonical(tok.ch) if isinstance(tok, Ident)
                                   else tok.name)
                    member_spellings.append(_spelling(tok))
                    self.advance()
                else:
                    raise self.error_at_current(
                        f"expected a member name, found {tok.describe}")
                if isinstance(self.peek(), Comma):
                    self.advance()
                else:
                    break
        elif head.name == "pyimport":
            raise ParseError(
                '`\\pyimport` binds members by name: \\pyimport("math": \\sqrt, \\tau)',
                head.span.to(self.peek().span))
        rparen = self.expect(RParen, "`)`")
        cls = PyImport if head.name == "pyimport" else Import
        return cls(path=path_tok.text, members=tuple(members),
                   span=head.span.to(rparen.span), member_spellings=tuple(member_spellings))

    # spelling-directive ::= "\\alias" name ("," name)+
    #                      | "\\dual" name "," name params? "=" statement (";" statement)* ;
    # Top-level parse-time directives (docs/grammar.md, `## Name aliases`): `\alias`
    # declares short spellings for one canonical name, `\dual` declares the pair and
    # defines the canonical name in the same statement. The declaration mutates the
    # working alias map immediately — its effect starts with the next statement, so
    # a spelling cannot be used before it is declared. `\dual` reuses the ordinary
    # definition forms: the node binds the canonical name only; the short spelling
    # reads (and checks against, via the statement `=` rule) as the very same name
    # from then on.
    def _spelling_statement(self, kind: str) -> Node:
        head = self.advance()  # the `\alias` / `\dual` token
        if self.depth > 0:
            raise ParseError(
                f"`\\{kind}` is a top-level directive: it cannot appear inside a "
                "function body or parenthesized group", head.span)
        names = self._collect_name_list()
        if kind == "alias" and len(names) < 2:
            raise self.error_at_current(
                "`\\alias` declares a canonical name with at least one short "
                "spelling: \\alias \\sum, σ")
        if kind == "dual" and len(names) != 2:
            raise self.error_at_current(
                "`\\dual` pairs a canonical name with exactly one short spelling: "
                "\\dual \\alpha, α = 3.14")
        canonical_tok, canonical = names[0]
        if canonical == "let":
            raise ParseError(
                "`\\let` is a reserved statement form",
                canonical_tok.span,
            )
        if canonical in _INFIX_NAMES:
            raise ParseError(
                f"`\\{canonical}` is an infix operator and cannot be aliased",
                canonical_tok.span)
        canonical_display = canonical if is_short_name(canonical) else f"\\{canonical}"
        for short_tok, short in names[1:]:
            if not isinstance(short_tok, Ident):
                raise ParseError(
                    "short spellings are single-character names: "
                    f"\\{kind} {canonical_display}, σ — not {short_tok.describe}",
                    short_tok.span)
            if short == canonical:
                raise ParseError(f"`{short}` already names itself", short_tok.span)
            if short in self.protected:
                raise ParseError(f"`{short}` is protected", short_tok.span)
            existing = self.aliases.get(short)
            if existing is not None and existing != canonical:
                raise ParseError(
                    f"`{short}` is already an alias of `{existing}`", short_tok.span)
            self.aliases[short] = canonical
        end = names[-1][0]
        if kind == "alias":
            return NoOp(span=head.span.to(end.span))
        # `\dual`: the definition tail after the pair. A parameter list makes it a
        # function definition with the ordinary greedy `;`-separated body; without
        # one it is a plain binding whose value is a single expression, exactly
        # like statement-level `=`.
        params: tuple[str, ...] = ()
        param_spellings: tuple[str, ...] = ()
        spelling = _spelling(end)
        if isinstance(self.peek(), LParen):
            self.advance()
            params, param_spellings = self._func_params()
        self.expect(Eq, "`=`")
        if params:
            body = self._func_body()
            return FuncDef(name=canonical, params=params, body=body,
                           span=head.span.to(body.span), spelling=spelling,
                           param_spellings=param_spellings)
        value = self.expr()
        return Assign(name=canonical, value=value, span=head.span.to(value.span),
                      spelling=spelling)

    def _let_statement(self, allow_let_function: bool) -> Node:
        head = self.advance()
        self._skip_newlines()
        name_tok = self.peek()
        if not isinstance(name_tok, (Ident, Backslash)):
            raise self.error_at_current(
                "`\\let` binds a fresh name: \\let name = expr")
        if isinstance(name_tok, Backslash) and name_tok.name == "let":
            raise ParseError(
                "`\\let` cannot bind its own keyword",
                head.span.to(name_tok.span),
            )
        self.advance()
        name = (self._canonical(name_tok.ch) if isinstance(name_tok, Ident)
                else name_tok.name)
        spelling = _spelling(name_tok)
        if isinstance(self.peek(), LParen):
            if not allow_let_function:
                raise ParseError(
                    "`\\let` function definitions are top-level: \\let f(x) = body",
                    head.span.to(name_tok.span),
                )
            self.advance()
            params, param_spellings = self._func_params()
            self.expect(Eq, "`=`")
            body = self._func_body()
            return FuncDef(name=name, params=params, body=body,
                           span=head.span.to(body.span), spelling=spelling,
                           param_spellings=param_spellings)
        self.expect(Eq, "`=`")
        value = self.expr()
        return Assign(name=name, value=value, fresh_only=True,
                      span=head.span.to(value.span), spelling=spelling)

    def _collect_name_list(self) -> list[tuple[Token, str]]:
        """Comma-separated name spellings (Ident or Backslash tokens) with their
        canonical-resolved names left raw — alias validation works on spellings.
        A trailing comma may end the line; the list continues across the break."""
        names: list[tuple[Token, str]] = []
        while True:
            self._skip_newlines()
            tok = self.peek()
            if not isinstance(tok, (Ident, Backslash)):
                raise self.error_at_current(f"expected a name, found {tok.describe}")
            names.append((tok, tok.ch if isinstance(tok, Ident) else tok.name))
            self.advance()
            if isinstance(self.peek(), Comma):
                self.advance()
            else:
                break
        return names

    def _func_params(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        # Newlines are whitespace where an operand is expected: the parameter list
        # may span lines (`f(\nx, y)`).
        self._skip_newlines()
        params: list[str] = []
        param_spellings: list[str] = []
        while True:
            tok = self.peek()
            if isinstance(tok, Ident | Backslash):
                params.append(self._canonical(tok.ch) if isinstance(tok, Ident) else tok.name)
                param_spellings.append(_spelling(tok))
                self.advance()
            elif isinstance(tok, RParen):
                break
            else:
                raise self.error_at_current(
                    f"expected a parameter name, found {tok.describe}")
            if isinstance(self.peek(), Comma):
                self.advance()
                self._skip_newlines()
            else:
                break
        self.expect(RParen, "`)`")
        return tuple(params), tuple(param_spellings)

    def _func_body(self) -> Node:
        self.depth += 1
        try:
            body_stmts = [self.statement()]
            while isinstance(self.peek(), Semi):
                self.advance()
                self._skip_newlines()
                if isinstance(self.peek(), Eof):
                    break
                body_stmts.append(self.statement())
        finally:
            self.depth -= 1
        if len(body_stmts) == 1:
            return body_stmts[0]
        return Seq(statements=tuple(body_stmts),
                   span=body_stmts[0].span.to(body_stmts[-1].span))

    # func-def ::= name "(" params? ")" "=" statement (";" statement)* ;
    # Speculative: parse the head shape, and only commit when an `=` follows the
    # closing paren; anything else restores the position so `f(x)` reparses as an
    # application. Parameter validity is enforced only once committed. Newlines are
    # whitespace where an operand is expected, so the parameter list may span lines.
    def _func_def_or_none(self) -> FuncDef | None:
        ident_tok = self.advance()
        self.advance()  # LParen — caller verified peek2
        self._skip_newlines()
        params: list[str] = []
        param_spellings: list[str] = []
        while True:
            tok = self.peek()
            if isinstance(tok, Ident | Backslash):
                params.append(self._canonical(tok.ch) if isinstance(tok, Ident) else tok.name)
                param_spellings.append(_spelling(tok))
                self.advance()
            elif isinstance(tok, RParen):
                break
            else:
                return None
            if isinstance(self.peek(), Comma):
                self.advance()
            else:
                break
        if not isinstance(self.peek(), RParen):
            return None
        close = self.advance()
        if not isinstance(self.peek(), Eq):
            return None
        self.advance()  # `=`
        body = self._func_body()
        span = ident_tok.span.to(body.span)
        name = (self._canonical(ident_tok.ch) if isinstance(ident_tok, Ident)
                else ident_tok.name)
        return FuncDef(name=name, params=tuple(params), body=body, span=span,
                       spelling=_spelling(ident_tok), param_spellings=tuple(param_spellings))

    # The statement list of a parenthesized group: statements separated by a newline
    # run or a single `;` (blank lines are free, `;;` an error, a trailing `;` before
    # `)` tolerated). The uniform newline rule, scoped to the group: where the last
    # statement's expression is complete, a newline separates — where it ends mid-
    # expression (`1 +`, a committed range `1..`) the statement continues. Imports
    # stay out (statements, not expressions — the group is an expression) and
    # `\alias`/`\dual` stay top-level (the depth guard).
    def _group_stmts(self, allow_let_function: bool = False) -> list[Node]:
        self._skip_newlines()
        self._nl = False
        items = [self.statement(allow_let_function=allow_let_function)]
        while True:
            sep = self._nl or isinstance(self.peek(), Newline)
            self._skip_newlines()
            if isinstance(self.peek(), Semi):
                sep = True
                self.advance()
                self._skip_newlines()
            if isinstance(self.peek(), RParen) or self._closes_section():
                break
            if not sep:
                raise self.error_at_current(
                    f"statements in a group are separated by a newline or `;`, "
                    f"found {self.peek().describe}")
            self._nl = False
            items.append(self.statement(allow_let_function=allow_let_function))
        return items

    # lambda ::= ("\λ" | "\fn") "(" params? ")" expr ;
    # The body extends greedily over the rest of the current expression — the
    # fold/limit rule: it ends at the enclosing delimiter (`,` `)` `;`, end of
    # input), so one-statement lambdas nest right-associatively without any
    # delimiter (`\fn(n) \fn(f) \fn(x) f(n(f)(x))`) and a parenthesized group gives
    # an explicit extent and multiple statements. Zero-argument form allowed,
    # matching `f()` legality.
    def _lambda(self, head: Backslash) -> Node:
        self.expect(LParen, "`(`")
        params, param_spellings = self._func_params()
        if isinstance(self.peek(), Eq):
            raise ParseError(
                "a lambda takes a body, not `=`: \\fn(x) x^2 — name it with f(x) = body",
                head.span.to(self.peek().span))
        body = self.expr()
        return Lambda(params=params, body=body, span=head.span.to(body.span),
                      param_spellings=param_spellings)

    def expr(self) -> Node:
        return self.ternary()

    # ternary ::= range ("?" ternary ":" ternary)? ; — the loosest expression level,
    # right-associative through the recursive branches (`a ? b : c ? d : e` is
    # `a ? b : (c ? d : e)`; a nested middle `a ? b ? c : d : e` closes at the first
    # free `:`). The lazy conditional: only the selected branch
    # evaluates — so the compiler/runtime need no new node. A missing `:` at EOF is
    # IncompleteInput (REPL continuation) via expect(); anywhere else it is a plain
    # parse error. `?`/`:` are not atom starters, so juxtaposition never eats them.
    def ternary(self) -> Node:
        cond = self.range_expr()
        if not isinstance(self.peek(), Question):
            return cond
        self.advance()  # `?`
        then_branch = self.ternary()
        self.expect(Colon, "`:`")
        otherwise = self.ternary()
        return IfExpr(condition=cond, then_branch=then_branch, otherwise=otherwise,
                      span=cond.span.to(otherwise.span))

    # The stepped form's comma is only consumed outside a list, and only when it
    # introduces a following `..`. Once a range delimiter is
    # committed (`..`, or the `,` of a stepped form) the expression continues across
    # line breaks — `1..` NL `5` is one range — but a bare newline before any range
    # delimiter is a statement boundary, never a continuation.
    def range_expr(self) -> Node:
        return self._range_from(self.comparison(), self.comparison)

    def _range_from(self, start: Node, bound) -> Node:
        second = None
        if isinstance(self.peek(), Comma) and not self._in_list:
            saved = self.pos
            self.advance()
            self._skip_newlines()
            candidate = bound()
            if not isinstance(self.peek(), DotDot):
                self.pos = saved
            else:
                second = candidate
        if not isinstance(self.peek(), DotDot):
            return start
        dotdot = self.advance()
        self._skip_newlines()
        # A closing delimiter terminates the range just like `,` `)` `;` and EOF —
        # `( r = 1.. )` is the infinite range, not a broken one.
        end = None if isinstance(self.peek(), (Comma, RParen, Semi, Eof)) else bound()
        return Range(start=start, second=second, end=end,
                     span=start.span.to((end or dotdot).span))

    # The canonical name of an infix-only spelling at the cursor, in either its
    # unicode or its `\\`-name form (`∪` and `\\cup` are both "cup").
    def _infix_name(self) -> str | None:
        tok = self.peek()
        if isinstance(tok, InfixOp):
            return tok.name
        if isinstance(tok, At):
            return "contract"
        if isinstance(tok, Backslash) and tok.name in _INFIX_NAMES:
            return tok.name
        return None

    def _operator_value(self, k: int = 0) -> Node | None:
        """The function value spelled by the operator token `k` ahead — an `OpRef`, or
        `\\sqrt` for the radical — else None."""
        tok = self.look(k)
        if isinstance(tok, Radical):
            return BackslashRef(name="sqrt", span=tok.span, spelling="√")
        if isinstance(tok, NthRoot):
            return Call(head=self._root_ref(tok),
                        args=(Hole(span=tok.span), NumLit(text=str(tok.index), span=tok.span)),
                        span=tok.span)
        key = _SYMBOL_OPERATORS.get(type(tok))
        if key is None:
            name = (tok.name if isinstance(tok, InfixOp) else "contract" if isinstance(tok, At)
                    else tok.name if isinstance(tok, Backslash) else None)
            key = _INFIX_OPERATORS.get(name)
        return None if key is None else OpRef(name=key, span=tok.span)

    @staticmethod
    def _root_ref(tok: NthRoot) -> BackslashRef:
        return BackslashRef(name="root", span=tok.span, spelling="\\root")

    def _closes_section(self, keys: frozenset[str] | None = None) -> bool:
        """The cursor is an operator (of `keys`, or any) directly before a `)`: the end of
        a left section, `(e op)`."""
        operator = self._operator_value()
        return (isinstance(operator, OpRef) and (keys is None or operator.name in keys)
                and isinstance(self.look(1), RParen))

    def _section(self, lhs: Node, keys: frozenset[str]) -> bool:
        """Stop an operand at a section's closing operator, remembering the operand so the
        enclosing group can check it was the whole expression."""
        if not self._closes_section(keys):
            return False
        self._section_operand = lhs
        return True

    # section ::= "(" operator operand ")" | "(" operand operator ")" ; the operand reads at
    # the level of the operator's own right-hand side, so a section is the hole form
    # `(op)(_, e)` / `(op)(e, _)` — `(- e)` stays negation.
    def _right_section(self, open_paren: Token) -> Node:
        self.advance()
        operator = self._operator_value()
        operand_level = (self.multiplicative if operator.name in _ADDITIVE_KEYS
                         else self.juxtaposed if operator.name in _MULTIPLICATIVE_KEYS
                         else self.unary if operator.name == "pow" else self.additive)
        self.advance()
        operand = operand_level()
        if operator.name in ("member", "notmember"):
            operand = self._range_from(operand, operand_level)
        if not isinstance(self.peek(), (RParen, Eof)):
            raise ParseError(
                f"a section's operand ends at `)`, found {self.peek().describe}; "
                f"parenthesize it: ({OP_SYMBOLS[operator.name]} (…))", self.peek().span)
        close = self.expect(RParen, "`)`")
        return Call(head=operator, args=(Hole(span=operator.span), operand),
                    span=open_paren.span.to(close.span))

    def _left_section(self, open_paren: Token, operand: Node, single: bool) -> Node:
        operator = self._operator_value()
        if not single or operand is not self._section_operand:
            raise ParseError(
                f"parenthesize the section's operand: ((…) {OP_SYMBOLS[operator.name]})",
                operator.span)
        self._section_operand = None
        self.advance()
        close = self.advance()
        return Call(head=operator, args=(operand, Hole(span=operator.span)),
                    span=open_paren.span.to(close.span))

    # comparison ::= additive (("<" | ">" | "<=" | ">=" | "∈" | "⊆") additive)? ;
    def comparison(self) -> Node:
        lhs = self.additive()
        if self._section(lhs, _COMPARE_KEYS):
            return lhs
        ops = {Less: CompareOperator.LT, LessEq: CompareOperator.LE,
               Greater: CompareOperator.GT, GreaterEq: CompareOperator.GE}
        if type(self.peek()) in ops:
            op = ops[type(self.advance())]
        elif self._infix_name() in _COMPARE_INFIX:
            op = _COMPARE_INFIX[self._infix_name()]
            self.advance()
        else:
            return lhs
        rhs = self.additive()
        if op in (CompareOperator.IN, CompareOperator.NOTIN):
            rhs = self._range_from(rhs, self.additive)
        return Compare(op=op, lhs=lhs, rhs=rhs, span=lhs.span.to(rhs.span))

    # additive ::= multiplicative (("+" | "-" | "∪" | "∖") multiplicative)* ;
    def additive(self) -> Node:
        lhs = self.multiplicative()
        while True:
            if self._section(lhs, _ADDITIVE_KEYS):
                break
            if isinstance(self.peek(), Plus):
                op = BinOperator.ADD
            elif isinstance(self.peek(), Minus):
                op = BinOperator.SUB
            elif self._infix_name() in _ADDITIVE_INFIX:
                op = _ADDITIVE_INFIX[self._infix_name()]
            else:
                break
            self.advance()
            rhs = self.multiplicative()
            lhs = BinOp(op=op, lhs=lhs, rhs=rhs, span=lhs.span.to(rhs.span))
        return lhs

    # multiplicative ::= juxtaposed (("*" | "/" | "@" | "∩") juxtaposed)* ;
    def multiplicative(self) -> Node:
        lhs = self.juxtaposed()
        while True:
            tok = self.peek()
            if self._section(lhs, _MULTIPLICATIVE_KEYS):
                break
            if isinstance(tok, Star):
                op = BinOperator.MUL
            elif isinstance(tok, Slash):
                op = BinOperator.DIV
            elif self._infix_name() in _MULTIPLICATIVE_INFIX:
                op = _MULTIPLICATIVE_INFIX[self._infix_name()]
            else:
                break
            self.advance()
            rhs = self.juxtaposed()
            lhs = BinOp(op=op, lhs=lhs, rhs=rhs, span=lhs.span.to(rhs.span))
        return lhs

    # juxtaposed ::= unary unary* ; — `-` is deliberately excluded from the starter set,
    # so `a - b` always parses as subtraction, never as `a * (-b)`. A Newline is not a
    # starter either: where an expression is complete, the line break separates
    # statements instead of multiplying through.
    def juxtaposed(self) -> Node:
        lhs = self.unary()
        while self._is_atom_starter():
            rhs = self.unary()
            lhs = BinOp(op=BinOperator.MUL, lhs=lhs, rhs=rhs, span=lhs.span.to(rhs.span))
        return lhs

    # unary ::= "-" unary | power ;
    def unary(self) -> Node:
        if isinstance(self.peek(), Minus):
            minus = self.advance()
            operand = self.unary()
            return UnOp(op=UnaryOperator.NEG, operand=operand, span=minus.span.to(operand.span))
        return self.power()

    # power ::= postfix ("^" unary)? ; right-associative; exponent recurses into `unary`.
    def power(self) -> Node:
        base = self.postfix()
        if self._section(base, frozenset({"pow"})):
            return base
        if isinstance(self.peek(), Caret):
            self.advance()
            exp = self.unary()
            return BinOp(op=BinOperator.POW, lhs=base, rhs=exp, span=base.span.to(exp.span))
        return base

    # postfix ::= atom ("(" args ")")* ;
    # Static application: a trailer attaches only to name-ish heads (Var/BackslashRef/
    # Call/Lambda), so `f(x)` applies while `2(x+1)` falls through to juxtaposition.
    # A parenthesized lambda in head position applies: `(\fn(x) x)(5)`. Unparenthesized,
    # the greedy body has already consumed any trailer (`\fn(x) x(5)` is a lambda whose
    # body is the call/product `x(5)`).
    _NAMEISH = (Var, BackslashRef, Call, Lambda, Eval, Index, OpRef)
    _INDEXABLE = _NAMEISH + (Transpose,)

    # Special forms recognized in postfix position (DESIGN.md "equality and =", case 3):
    # a closed list of builtins whose first argument is a binding, not a general
    # equality expression. The unicode spellings `Σ`/`Π` are not listed: the alias
    # map normalizes them to `\sum`/`\prod` before this table is consulted (and a
    # user `\alias` onto those names gets the same treatment for free).
    _FOLD_HEADS = {("sum", None): BinOperator.ADD, ("prod", None): BinOperator.MUL}
    _LIMIT_LABEL = "\\lim"

    # A `∘` node only reaches a trailer parenthesized (`(f ∘ g)(x)`); unparenthesized,
    # the trailer already bound to its right operand.
    @staticmethod
    def _is_call_head(node: Node) -> bool:
        return isinstance(node, _Parser._NAMEISH) or (
            isinstance(node, BinOp) and node.op is BinOperator.COMPOSE)

    def postfix(self) -> Node:
        node = self.atom()
        fold_op = self._fold_head(node)
        if (
            (fold_op is not None or self._limit_head(node))
            and isinstance(self.peek(), LParen)
        ):
            if not self._binder_shape_ahead():
                # Fold/limit heads are reserved special forms — any parenthesized use
                # that is not the binder shape is a usage error, not an application of
                # an unbound name.
                label = self._form_label(node)
                usage = (f"{label}(x=a) body" if fold_op is None
                         else f"{label}(i=a..b) body")
                raise ParseError(
                    f"{self._form_label(node)} takes a binder as its first "
                    f"argument: {usage}",
                    node.span.to(self.peek().span),
                )
            # Binder shape committed: bare `=` cannot occur in a general expression,
            # so from here on malformed binders are genuine parse errors.
            return self._special_form(node, fold_op)
        while True:
            if isinstance(node, _Parser._INDEXABLE) and isinstance(self.peek(), LBracket):
                node = self._index(node)
                continue
            if isinstance(self.peek(), Superscript):
                if isinstance(node, (Var, BackslashRef)) and isinstance(self.look(1), LParen):
                    tok = self.advance()
                    exponent = self._exponent(tok)
                    args, kwargs, rparen = self._call_arguments()
                    node = PowCall(head=node, exponent=exponent, args=args, kwargs=kwargs,
                                   span=node.span.to(rparen.span))
                    continue
                tok = self.advance()
                node = BinOp(op=BinOperator.POW, lhs=node, rhs=self._exponent(tok),
                             span=node.span.to(tok.span))
                continue
            if isinstance(self.peek(), (Bang, DoubleBang)):
                bang = self.advance()
                op = UnaryOperator.FACT if isinstance(bang, Bang) else UnaryOperator.DFACT
                node = UnOp(op=op, operand=node, span=node.span.to(bang.span))
                continue
            if isinstance(self.peek(), Prime):
                tick = self.advance()
                node = Transpose(operand=node, span=node.span.to(tick.span))
                continue
            if not (self._is_call_head(node) and isinstance(self.peek(), LParen)):
                break
            args, kwargs, rparen = self._call_arguments()
            node = Call(head=node, args=args, kwargs=kwargs,
                        span=node.span.to(rparen.span))
            if (isinstance(node.head, BackslashRef) and node.head.name in _NO_HOLE_FORMS
                    and any(isinstance(a, Hole) for a in node.args)):
                raise ParseError(
                    f"`{self._form_label(node.head)}` cannot take a `·` placeholder", node.span)
            if isinstance(node.head, BackslashRef) and node.head.name == "eval":
                if len(node.args) != 1:
                    raise ParseError("`\\eval` takes one expression value followed by bindings",
                                     node.span)
                node = Eval(value=node.args[0], bindings=node.kwargs, span=node.span)
            if isinstance(node, Call) and isinstance(node.head, BackslashRef) \
                    and node.head.name == "arr":
                if node.kwargs:
                    raise ParseError("`\\arr` takes positional values", node.span)
                node = ArrayLit(items=node.args, span=node.span)
            if (
                isinstance(node, Call)
                and isinstance(node.head, BackslashRef)
                and node.head.name == "py"
                and (len(node.args) != 1 or node.kwargs)
            ):
                raise ParseError(
                    f"`{self._form_label(node.head)}` takes exactly one argument", node.span)
        return node

    # call-args ::= "(" (arg ("," arg)*)? ")"
    def _call_arguments(self) -> tuple[tuple[Node, ...], tuple[KwArg, ...], Token]:
        self.advance()
        self._skip_newlines()  # arguments may start on the line after `(`
        args: tuple[Node, ...] = ()
        kwargs: tuple[KwArg, ...] = ()
        if not isinstance(self.peek(), RParen):  # `f()` — zero-arg calls are legal
            with self._list_context(True):
                items: list[Node] = [self.call_arg()]
                while isinstance(self.peek(), Comma):
                    self.advance()
                    self._skip_newlines()  # an argument may start on the line after `,`
                    items.append(self.call_arg())
            # Positionals and kwargs collect separately (their relative source
            # order carries no meaning); duplicate kwarg names are a parse error
            # rather than Python's silent last-one-wins.
            seen: set[str] = set()
            for item in items:
                if isinstance(item, KwArg):
                    if item.name in seen:
                        raise ParseError(
                            f"duplicate keyword argument `{item.spelling or item.name}`", item.span)
                    seen.add(item.name)
            args = tuple(i for i in items if not isinstance(i, KwArg))
            kwargs = tuple(i for i in items if isinstance(i, KwArg))
        return args, kwargs, self.expect(RParen, "`)`")

    # superscript ::= "²" | "⁻¹" | "ⁿ⁺¹" | ... — the run's ASCII form read as an expression.
    def _exponent(self, tok: Superscript) -> Node:
        sub = _Parser(list(tok.tokens), self.aliases, self.source)
        exponent = sub.expr()
        sub.expect(Eof, "end of superscript")
        return exponent

    # index ::= "[" expr ("," expr)* "]" — a trailer on name-ish heads and transposes.
    def _index(self, head: Node) -> Index:
        self.advance()  # `[`
        self._skip_newlines()
        with self._list_context(True):
            items = [self.expr()]
            self._skip_newlines()
            while isinstance(self.peek(), Comma):
                self.advance()
                self._skip_newlines()
                items.append(self.expr())
                self._skip_newlines()
        close = self.expect(RBracket, "`]`")
        self._nl = False
        return Index(head=head, items=tuple(items), span=head.span.to(close.span))

    # tensor ::= "[" expr ("," expr)* "]" | "[" row (";" row)* ";"? "]"
    # A `;` makes every item a scalar in a row of equal length; a trailing `;` keeps
    # a single row a matrix (`[1, 2;]` is 1x2, `[1, 2]` a vector).
    def _tensor_literal(self) -> TensorLit:
        opener = self.advance()  # `[`
        self._skip_newlines()
        if isinstance(self.peek(), RBracket):
            raise ParseError("empty tensor", opener.span.to(self.peek().span))
        items: list[Node] = []
        row_lengths: list[int] = []
        current = 0
        while True:
            with self._list_context(True):
                items.append(self.expr())
            current += 1
            self._skip_newlines()
            if isinstance(self.peek(), Comma):
                self.advance()
                self._skip_newlines()
            elif isinstance(self.peek(), Semi):
                self.advance()
                self._skip_newlines()
                row_lengths.append(current)
                current = 0
                if isinstance(self.peek(), RBracket):
                    break
            else:
                break
        close = self.expect(RBracket, "`]`")
        self._nl = False
        span = opener.span.to(close.span)
        if not row_lengths:
            return TensorLit(items=tuple(items), span=span)
        if current:
            row_lengths.append(current)
        if any(n != row_lengths[0] for n in row_lengths):
            raise ParseError("tensor rows have different lengths", span)
        return TensorLit(items=tuple(items), row_length=row_lengths[0], span=span)

    # set ::= "{" (expr ("," expr)*)? "}"
    def _set_literal(self) -> SetLit:
        opener = self.advance()
        self._skip_newlines()
        items: list[Node] = []
        if not isinstance(self.peek(), RBrace):
            with self._list_context(True):
                items.append(self.expr())
                self._skip_newlines()
                while isinstance(self.peek(), Comma):
                    self.advance()
                    self._skip_newlines()
                    items.append(self.expr())
                    self._skip_newlines()
        close = self.expect(RBrace, "`}`")
        self._nl = False
        return SetLit(items=tuple(items), span=opener.span.to(close.span))

    # array ::= "⟨" (expr ("," expr)*)? "⟩" | "#[" (expr ("," expr)*)? "]"
    def _array_literal(self, closer: type, closer_text: str) -> ArrayLit:
        opener = self.advance()
        self._skip_newlines()
        items: list[Node] = []
        if not isinstance(self.peek(), closer):
            with self._list_context(True):
                items.append(self.expr())
                self._skip_newlines()
                while isinstance(self.peek(), Comma):
                    self.advance()
                    self._skip_newlines()
                    items.append(self.expr())
                    self._skip_newlines()
        close = self.expect(closer, closer_text)
        self._nl = False
        return ArrayLit(items=tuple(items), span=opener.span.to(close.span))

    def _quote(self, head: Token) -> Quote:
        with self._list_context(False):
            return self._quote_body(head)

    def _quote_body(self, head: Token) -> Quote:
        self.expect(LParen, "`(`")
        group_end = None
        has_separator = False
        if isinstance(self.peek(), LParen):
            depth = 0
            brackets = 0
            for index in range(self.pos, len(self.tokens)):
                if isinstance(self.tokens[index], LParen):
                    depth += 1
                elif isinstance(self.tokens[index], RParen):
                    depth -= 1
                    if depth == 0:
                        group_end = index
                        break
                elif isinstance(self.tokens[index], _OPENERS):
                    brackets += 1
                elif isinstance(self.tokens[index], _CLOSERS):
                    brackets -= 1
                elif (depth == 1 and brackets == 0
                        and isinstance(self.tokens[index], (Semi, Newline))):
                    has_separator = True
        if (group_end is not None and has_separator
                and isinstance(self.tokens[group_end + 1], RParen)):
            self.advance()
            self.depth += 1
            try:
                statements = self._group_stmts()
            finally:
                self.depth -= 1
            self.expect(RParen, "`)`")
            self.expect(RParen, "`)`")
            body = Seq(statements=tuple(statements),
                       span=statements[0].span.to(statements[-1].span))
            return Quote(body=body, source=self.source, statement_body=True,
                         span=head.span.to(self.tokens[self.pos - 1].span))
        body = self.expr()
        self.expect(RParen, "`)`")
        if not self._quotable(body):
            raise ParseError("quotes contain one expression, not statements", body.span)
        return Quote(body=body, source=self.source, span=head.span.to(self.tokens[self.pos - 1].span))

    @staticmethod
    def _quotable(node: Node) -> bool:
        from dataclasses import fields

        if isinstance(node, (Assign, FuncDef, Seq, Import, PyImport, NoOp)):
            return False
        for field in fields(node):
            value = getattr(node, field.name)
            if isinstance(value, Node) and not _Parser._quotable(value):
                return False
            if isinstance(value, tuple) and any(isinstance(item, Node) and
                                                not _Parser._quotable(item) for item in value):
                return False
        return True

    def _fold_head(self, node: Node) -> BinOperator | None:
        """The fold operator when `node` is a fold head, else None. Heads are always
        BackslashRefs — single-character spellings normalize to their canonical
        multi-char names before this runs."""
        if isinstance(node, BackslashRef) and (node.name, None) in _Parser._FOLD_HEADS:
            return _Parser._FOLD_HEADS[(node.name, None)]
        return None

    def _limit_head(self, node: Node) -> bool:
        return isinstance(node, BackslashRef) and node.name == "lim"

    # special-form ::= fold | limit ;
    # fold  ::= ("\sum" | "\prod" | "Σ" | "Π") "(" ident "=" expr ")" expr ;
    # limit ::= "\lim" "(" ident "=" expr ")" expr ;
    # The body extends greedily over the rest of the current expression, up to
    # the enclosing delimiter (`,` `)` `;` or end of input); parenthesize to end it
    # earlier: `\sum(i=1..2) (i + 1) * 2` folds `i + 1`, then doubles the total.
    def _binder_shape_ahead(self) -> bool:
        """The `(ident =` shape that commits the special form. Newlines inside the
        paren are operand whitespace (`\\sum(\\ni = 1..2)`), so the lookahead skips
        them too."""
        k = 1
        while isinstance(self.look(k), Newline):
            k += 1
        if not isinstance(self.look(k), Ident):
            return False
        k += 1
        while isinstance(self.look(k), Newline):
            k += 1
        return isinstance(self.look(k), Eq)

    def _special_form(self, head: Node, fold_op: BinOperator | None) -> Node:
        label = self._form_label(head)
        self.advance()  # LParen — caller verified
        self._skip_newlines()
        var_tok = self.advance()
        var = self._canonical(var_tok.ch)
        self.expect(Eq, "`=`")
        with self._list_context(False):
            bound = self.expr()
        self.expect(RParen, "`)`")
        body = self.expr()
        span = head.span.to(body.span)
        if fold_op is not None:
            return Fold(op=fold_op, var=var, bound=bound, body=body, span=span,
                        spelling=label, var_spelling=_spelling(var_tok))
        return Limit(var=var, point=bound, body=body, span=span,
                     spelling=label, var_spelling=_spelling(var_tok))

    def _form_label(self, head: Node) -> str:
        match head:
            case BackslashRef(name=name, spelling=spelling):
                return spelling or f"\\{name}"
            case Var(ch=ch, spelling=spelling):
                return spelling or ch
            case _:
                return "?"

    # args ::= (expr | string | kwarg) ("," ...)* — a string is an ordinary atom now,
    # so `call_value` need only special-case it before the general expression (where it
    # would parse the same way). A kwarg is `name=value`; the `=` seen directly after a
    # name token commits it, and bare `=` cannot occur inside a general expression, so
    # nothing else can want that shape. Multi-character names take the `\` sigil
    # (`\dpi=300`).
    def call_arg(self) -> Node:
        tok = self.peek()
        if isinstance(tok, Placeholder):
            if not isinstance(self.look(1), (Comma, RParen)):
                raise ParseError(f"`{tok.ch}` is a placeholder for a whole call argument",
                                 tok.span)
            self.advance()
            return Hole(span=tok.span)
        if isinstance(tok, (Ident, Backslash)) and isinstance(self.look(1), Eq):
            name_tok = self.advance()
            self.advance()  # `=`
            value = self.call_value()
            name = (self._canonical(name_tok.ch) if isinstance(name_tok, Ident)
                    else name_tok.name)
            return KwArg(name=name, value=value, span=name_tok.span.to(value.span),
                         spelling=_spelling(name_tok))
        if isinstance(self.look(1), (Comma, RParen)):
            operator = self._operator_value()
            if operator is not None:
                self.advance()
                return operator
        return self.call_value()

    def call_value(self) -> Node:
        if isinstance(self.peek(), Str):
            tok = self.advance()
            return StrLit(text=tok.text, span=tok.span)
        return self.expr()

    # atom ::= number | string | identifier | "\"-name | "(" sequence ")"
    #          | lambda | radical ;
    def atom(self) -> Node:
        # An operand may start on the line after the operator that demands it
        # (`1 +` NL `2`): mid-expression, a newline never separates statements.
        self._skip_newlines()
        tok = self.peek()
        match tok:
            case Number():
                self.advance()
                return NumLit(text=tok.text, span=tok.span)
            case Str():
                self.advance()
                return StrLit(text=tok.text, span=tok.span)
            case Ident():
                self.advance()
                node = self._name_node(tok.ch, tok.span)
                if tok.spelling and isinstance(node, Var):
                    node = replace(node, spelling=tok.spelling)
                return node
            case LBracket():
                return self._tensor_literal()
            case LBrace():
                return self._set_literal()
            case LAngle():
                return self._array_literal(RAngle, "`⟩`")
            case HashBracket():
                return self._array_literal(RBracket, "`]`")
            case Backslash():
                if tok.name in _INFIX_NAMES:
                    raise ParseError(f"`\\{tok.name}` is an infix operator", tok.span)
                if tok.name == "expr" and isinstance(self.peek2(), LParen):
                    self.advance()
                    return self._quote(tok)
                if tok.name in _LAMBDA_HEADS and isinstance(self.peek2(), LParen):
                    self.advance()
                    return self._lambda(tok)
                self.advance()
                return BackslashRef(name=tok.name, span=tok.span, spelling=_spelling(tok))
            case Backtick():
                self.advance()
                return self._quote(tok)
            case Radical():
                # `√` is the prefix spelling of `\sqrt(...)`: the operand parses at
                # the unary level (so `√2^2` reads √(2²), `2^√2` works, `√2*3` is
                # `(√2)*3`) and the node rewrites to the ordinary application —
                # evaluation is identical to the ASCII call form. A dangling `√`
                # at EOF is IncompleteInput via the operand's atom parse, exactly
                # like an unclosed parenthesis.
                rad = self.advance()
                operand = self.unary()
                return Call(head=BackslashRef(name="sqrt", span=rad.span, spelling="√"),
                            args=(operand,), span=rad.span.to(operand.span))
            case NthRoot():
                # `∛x` / `∜x`: the operand parses at the unary level like `√`'s, and the
                # node is the ordinary `\\root(x, n)` call.
                rad = self.advance()
                operand = self.unary()
                return Call(head=self._root_ref(rad),
                            args=(operand, NumLit(text=str(rad.index), span=rad.span)),
                            span=rad.span.to(operand.span))
            case LParen() if (self.look(2).__class__ is RParen
                              and self._operator_value(1) is not None):
                self.advance()
                operator = self._operator_value()
                self.advance()
                close = self.advance()
                return replace(operator, span=tok.span.to(close.span))
            case LParen() if (self._operator_value(1) is not None
                              and not isinstance(self.look(1), (Minus, Radical, NthRoot, Bang, DoubleBang))):
                return self._right_section(tok)
            case LParen():
                group_top_level = (
                    self._top_level_statement and self.pos == self._statement_start
                )
                self.advance()
                self.depth += 1
                try:
                    with self._list_context(False):
                        items = self._group_stmts(
                            allow_let_function=group_top_level
                        )
                finally:
                    self.depth -= 1
                # Imports bind names and produce no output — they have no value, so
                # a parenthesized sequence group (an expression) cannot hold one.
                # Statement contexts (top level, function bodies) parse them fine.
                for item in items:
                    if isinstance(item, Import | PyImport):
                        raise ParseError(
                            "`\\import` and `\\pyimport` are statements, not expressions",
                            item.span)
                inner = items[0] if len(items) == 1 else Seq(
                    statements=tuple(items), span=items[0].span.to(items[-1].span)
                )
                if self._closes_section():
                    return self._left_section(tok, inner, len(items) == 1)
                self.expect(RParen, "`)`")
                # The group statement ends at its `)`: line breaks consumed inside
                # were its structure, not separators of the enclosing statement list.
                self._nl = False
                # Deliberately not retagged with the paren-inclusive span — see module docstring.
                return inner
            case _:
                raise self.error_at_current(f"unexpected token {tok.describe}")


def parse_program(src: str, aliases: dict[str, str] | None = None) -> Node:
    """Tokenize and parse a complete program from source text.

    `aliases` is the session alias map (short spelling → canonical name); the parse
    works on a copy seeded from it and `\\alias`/`\\dual` declarations merge back into
    the caller's dict only after a fully successful parse, so a failed or incomplete
    input leaves the session map untouched. `None` means a throwaway seed-only map —
    the right choice for scripts and imported modules, which do not inherit or export
    session aliases (docs/grammar.md, `## Name aliases`)."""
    try:
        tokens = tokenize(src)
    except UnterminatedString as e:
        # An open quote at EOF is incomplete input, not a dead end — the REPL offers a
        # continuation prompt exactly like an unclosed parenthesis.
        raise IncompleteInput(e.msg, e.span) from e
    except LexError as e:
        raise ParseError(e.msg, e.span) from e
    parser = _Parser(tokens, aliases, src)
    node = parser.program()
    if aliases is not None:
        aliases.update(parser.aliases)
    return node
