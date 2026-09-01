"""Recursive-descent / precedence-climbing parser over the token stream, matching the
precedence table in docs/grammar.md:

    program     ::= statement (";" statement)* ;
    statement   ::= func-def | string | identifier "=" expr | expr ;
    expr        ::= ternary ;
    ternary     ::= range ("?" ternary ":" ternary)? ;   -- the lazy conditional
    additive    ::= multiplicative (("+" | "-") multiplicative)* ;
    multiplicative ::= juxtaposed (("*" | "/") juxtaposed)* ;
    juxtaposed  ::= unary unary* ;          -- implicit multiplication
    unary       ::= "-" unary | power ;
    radical     ::= "√" unary ;   -- prefix spelling of \\sqrt(...): `√2^2` is √(2²),
                                  -- `2^√2` works, `√2 3` is `(√2)·3`
    power       ::= postfix ("^" unary)? ;  -- right-associative
    postfix     ::= atom ("(" args ")")* ;  -- trailers attach only to name-ish heads
    args        ::= (expr | string | kwarg) ("," ...)* ;   kwarg ::= name "=" value ;
    atom        ::= number | string | identifier | "\\"-name | "(" expr ")" ;

`power`'s exponent recurses into `unary`, not `power` — that's what makes `2^-1` parse
(unary minus binds inside the exponent) and `2^3^2` right-associate. The base of `^` is a
postfix node, so `-2^2` is `-(2^2)` and `f(x)^2` squares the result. The radical `√` is
the one prefix operator: it sits at the unary level and rewrites to a `\\sqrt(...)`
application node, so evaluation is identical to the ASCII call form — `√2 3` is `(√2)·3`,
`√2^2` reads √(2²) like the overbar visually extends, and `√2√3` juxtaposes into
`√2·√3`.

Postfix application is *syntactically* name-headed: a `(…)` trailer attaches only when the
head so far is a name-ish node (`Var`, `BackslashRef`, or another `Call`). Number-headed
parens never apply — `2(x+1)` still parses as juxtaposed multiplication. Whether a parsed
call applies or falls back to multiplication is decided at evaluation (dynamic
juxtaposition, docs/grammar.md). Strings are values: one alone may still be a statement
(echoed to nobody, comment-like) and one is a whole call argument; inside expressions they
are ordinary atoms — `"a" + "b"` concatenates, and a string reaching any other operator
fails as the usual typed "strings are not numbers" at evaluation. The function
definition shape `f(x) = body` is recognized at statement level and parsed into `FuncDef`;
function bodies may contain semicolon-separated statements.

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

from .lexer import (
    Backslash,
    Colon,
    Comma,
    Caret,
    Eq,
    Eof,
    Ident,
    LexError,
    LParen,
    Less,
    LessEq,
    Minus,
    Newline,
    Number,
    Plus,
    Question,
    Radical,
    RParen,
    Semi,
    Slash,
    Star,
    Str,
    Token,
    Greater,
    GreaterEq,
    DotDot,
    UnterminatedString,
    tokenize,
)
from .runtime import PRELUDE
from .span import Span
from .syntax import (
    Assign,
    BackslashRef,
    BinOp,
    BinOperator,
    Call,
    Compare,
    CompareOperator,
    Fold,
    FuncDef,
    IfExpr,
    Import,
    KwArg,
    Lambda,
    Limit,
    Node,
    NoOp,
    NumLit,
    PyImport,
    Range,
    Seq,
    StrLit,
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


_ATOM_STARTERS = (Number, Ident, Backslash, LParen, Str, Radical)

# Lambda heads: the unicode spelling and the ASCII one. A `\`-name head followed by
# a parameter-list paren parses as an anonymous function (docs/grammar.md, `## Lambdas`);
# without the paren the head is an ordinary unbound name (the `\py` usage-error pattern).
_LAMBDA_HEADS = ("λ", "fn")

# Seed of the session alias map (short spelling → canonical name): the unicode
# fold heads and π, expressed as ordinary `\alias`-mechanism entries instead of
# hardcoded parser/prelude special cases (docs/grammar.md, `## Name aliases`).
ALIAS_SEED: dict[str, str] = {"Σ": "sum", "Π": "prod", "π": "pi"}


class _Parser:
    def __init__(self, tokens: list[Token], aliases: dict[str, str] | None = None):
        self.tokens = tokens
        self.pos = 0
        # Working alias map: the session's map (if given) layered over the seed.
        # `\alias`/`\dual` declarations mutate this dict; parse_program merges it
        # back into the caller's map only on a fully successful parse.
        self.aliases = dict(ALIAS_SEED)
        if aliases:
            self.aliases.update(aliases)
        # Names a spelling declaration may not repurpose: the prelude. It is the
        # only protected set — user bindings are immutable by the binding rule
        # itself, not by declaration.
        self.protected = frozenset(PRELUDE)
        # Statement nesting depth: `\alias`/`\dual` are top-level directives —
        # declaring one inside a function body or group would take effect at
        # parse time whether or not the body ever runs.
        self.depth = 0
        # Set by `_skip_newlines`, reset by statement lists around each
        # statement: "a line break was consumed since the last statement ended".
        self._nl = False

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
        return isinstance(self.peek(), _ATOM_STARTERS)

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
        if len(canonical) == 1:
            return Var(ch=canonical, span=span)
        return BackslashRef(name=canonical, span=span)

    # program ::= statement (sep statement)* ;
    # sep ::= newline run | ";" — newlines are whitespace-carved statement boundaries
    # at top level exactly like semicolons (a source may separate statements with
    # either); two adjacent `;` stay an error, blank lines are free.
    def program(self) -> Node:
        self._skip_newlines()
        statements = [self.statement()]
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
            statements.append(self.statement())
        if not isinstance(self.peek(), Eof):
            found = self.peek().describe
            raise self.error_at_current(f"unexpected token {found}")
        if len(statements) == 1:
            return statements[0]
        span = statements[0].span.to(statements[-1].span)
        return Seq(statements=tuple(statements), span=span)

    # statement ::= func-def | string
    #             | identifier "=" expr | expr ;
    # Statement heads are line-bound: the two-token looks aheads (peek2) see the
    # token immediately after the head, so a statement head and its syntax belong
    # on one line. Mid-statement, expression parsing continues across lines.
    def statement(self) -> Node:
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
                return Assign(name=name, value=value, span=span)
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
        if isinstance(self.peek(), Colon):
            self.advance()
            while True:
                tok = self.peek()
                if isinstance(tok, (Ident, Backslash)):
                    members.append(self._canonical(tok.ch) if isinstance(tok, Ident)
                                   else tok.name)
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
                   span=head.span.to(rparen.span))

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
        canonical_display = f"\\{canonical}" if len(canonical) > 1 else canonical
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
        if isinstance(self.peek(), LParen):
            self.advance()
            params = self._func_params()
        self.expect(Eq, "`=`")
        if params:
            body = self._func_body()
            return FuncDef(name=canonical, params=params, body=body,
                           span=head.span.to(body.span))
        value = self.expr()
        return Assign(name=canonical, value=value, span=head.span.to(value.span))

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

    def _func_params(self) -> tuple[str, ...]:
        # Newlines are whitespace where an operand is expected: the parameter list
        # may span lines (`f(\nx, y)`).
        self._skip_newlines()
        params: list[str] = []
        while True:
            tok = self.peek()
            if isinstance(tok, Ident):
                params.append(self._canonical(tok.ch))
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
        return tuple(params)

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

    # func-def ::= identifier "(" params? ")" "=" statement (";" statement)* ;
    # Speculative: parse the head shape, and only commit when an `=` follows the
    # closing paren; anything else restores the position so `f(x)` reparses as an
    # application. Parameter validity is enforced only once committed. Newlines are
    # whitespace where an operand is expected, so the parameter list may span lines.
    def _func_def_or_none(self) -> FuncDef | None:
        ident_tok = self.advance()
        self.advance()  # LParen — caller verified peek2
        self._skip_newlines()
        params: list[str] = []
        while True:
            tok = self.peek()
            if isinstance(tok, Ident):
                params.append(self._canonical(tok.ch))
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
        return FuncDef(name=name, params=tuple(params), body=body, span=span)

    # The statement list of a parenthesized group: statements separated by a newline
    # run or a single `;` (blank lines are free, `;;` an error, a trailing `;` before
    # `)` tolerated). The uniform newline rule, scoped to the group: where the last
    # statement's expression is complete, a newline separates — where it ends mid-
    # expression (`1 +`, a committed range `1..`) the statement continues. Imports
    # stay out (statements, not expressions — the group is an expression) and
    # `\alias`/`\dual` stay top-level (the depth guard).
    def _group_stmts(self) -> list[Node]:
        self._skip_newlines()
        self._nl = False
        items = [self.statement()]
        while True:
            sep = self._nl or isinstance(self.peek(), Newline)
            self._skip_newlines()
            if isinstance(self.peek(), Semi):
                sep = True
                self.advance()
                self._skip_newlines()
            if isinstance(self.peek(), RParen):
                break
            if not sep:
                raise self.error_at_current(
                    f"statements in a group are separated by a newline or `;`, "
                    f"found {self.peek().describe}")
            self._nl = False
            items.append(self.statement())
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
        params = self._func_params()
        if isinstance(self.peek(), Eq):
            raise ParseError(
                "a lambda takes a body, not `=`: \\fn(x) x^2 — name it with f(x) = body",
                head.span.to(self.peek().span))
        body = self.expr()
        return Lambda(params=params, body=body, span=head.span.to(body.span))

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

    # Range commas are only consumed when they introduce a following `..`, preserving
    # ordinary call argument commas such as `f(1, 2)`. Once a range delimiter is
    # committed (`..`, or the `,` of a stepped form) the expression continues across
    # line breaks — `1..` NL `5` is one range — but a bare newline before any range
    # delimiter is a statement boundary, never a continuation.
    def range_expr(self) -> Node:
        start = self.comparison()
        second = None
        if isinstance(self.peek(), Comma):
            saved = self.pos
            self.advance()
            self._skip_newlines()
            candidate = self.comparison()
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
        end = None if isinstance(self.peek(), (Comma, RParen, Semi, Eof)) \
            else self.comparison()
        return Range(start=start, second=second, end=end,
                     span=start.span.to((end or dotdot).span))

    def comparison(self) -> Node:
        lhs = self.additive()
        ops = {Less: CompareOperator.LT, LessEq: CompareOperator.LE,
               Greater: CompareOperator.GT, GreaterEq: CompareOperator.GE}
        if type(self.peek()) in ops:
            tok = self.advance()
            rhs = self.additive()
            return Compare(op=ops[type(tok)], lhs=lhs, rhs=rhs, span=lhs.span.to(rhs.span))
        return lhs

    # additive ::= multiplicative (("+" | "-") multiplicative)* ;
    def additive(self) -> Node:
        lhs = self.multiplicative()
        while True:
            if isinstance(self.peek(), Plus):
                op = BinOperator.ADD
            elif isinstance(self.peek(), Minus):
                op = BinOperator.SUB
            else:
                break
            self.advance()
            rhs = self.multiplicative()
            lhs = BinOp(op=op, lhs=lhs, rhs=rhs, span=lhs.span.to(rhs.span))
        return lhs

    # multiplicative ::= juxtaposed (("*" | "/") juxtaposed)* ;
    def multiplicative(self) -> Node:
        lhs = self.juxtaposed()
        while True:
            if isinstance(self.peek(), Star):
                op = BinOperator.MUL
            elif isinstance(self.peek(), Slash):
                op = BinOperator.DIV
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
    _NAMEISH = (Var, BackslashRef, Call, Lambda)

    # Special forms recognized in postfix position (DESIGN.md "equality and =", case 3):
    # a closed list of builtins whose first argument is a binding, not a general
    # equality expression. The unicode spellings `Σ`/`Π` are not listed: the alias
    # map normalizes them to `\sum`/`\prod` before this table is consulted (and a
    # user `\alias` onto those names gets the same treatment for free).
    _FOLD_HEADS = {("sum", None): BinOperator.ADD, ("prod", None): BinOperator.MUL}
    _LIMIT_LABEL = "\\lim"

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
                usage = ("\\lim(x=a) body" if fold_op is None
                         else "\\sum(i=a..b) body")
                raise ParseError(
                    f"{self._form_label(node)} takes a binder as its first "
                    f"argument: {usage}",
                    node.span.to(self.peek().span),
                )
            # Binder shape committed: bare `=` cannot occur in a general expression,
            # so from here on malformed binders are genuine parse errors.
            return self._special_form(node, fold_op)
        while isinstance(node, _Parser._NAMEISH) and isinstance(self.peek(), LParen):
            self.advance()
            self._skip_newlines()  # arguments may start on the line after `(`
            args: tuple[Node, ...] = ()
            kwargs: tuple[KwArg, ...] = ()
            if not isinstance(self.peek(), RParen):  # `f()` — zero-arg calls are legal
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
                                f"duplicate keyword argument `{item.name}`", item.span)
                        seen.add(item.name)
                args = tuple(i for i in items if not isinstance(i, KwArg))
                kwargs = tuple(i for i in items if isinstance(i, KwArg))
            rparen = self.expect(RParen, "`)`")
            node = Call(head=node, args=args, kwargs=kwargs,
                        span=node.span.to(rparen.span))
            if (
                isinstance(node.head, BackslashRef)
                and node.head.name == "py"
                and (len(node.args) != 1 or node.kwargs)
            ):
                raise ParseError("`\\py` takes exactly one argument", node.span)
        return node

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
        label = self._LIMIT_LABEL if fold_op is None else self._form_label(head)
        self.advance()  # LParen — caller verified
        self._skip_newlines()
        var = self._canonical(self.advance().ch)
        self.expect(Eq, "`=`")
        bound = self.expr()
        self.expect(RParen, "`)`")
        body = self.expr()
        span = head.span.to(body.span)
        if fold_op is not None:
            if not isinstance(bound, Range):
                raise ParseError(
                    f"{self._form_label(head)} needs a range to fold over: "
                    f"{self._form_label(head)}(i=1..10)",
                    bound.span,
                )
            return Fold(op=fold_op, var=var, rng=bound, body=body, span=span)
        return Limit(var=var, point=bound, body=body, span=span)

    def _form_label(self, head: Node) -> str:
        match head:
            case BackslashRef(name=name):
                return f"\\{name}"
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
        if isinstance(tok, (Ident, Backslash)) and isinstance(self.look(1), Eq):
            name_tok = self.advance()
            self.advance()  # `=`
            value = self.call_value()
            name = (self._canonical(name_tok.ch) if isinstance(name_tok, Ident)
                    else name_tok.name)
            return KwArg(name=name, value=value, span=name_tok.span.to(value.span))
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
                return self._name_node(tok.ch, tok.span)
            case Backslash():
                if tok.name in _LAMBDA_HEADS and isinstance(self.peek2(), LParen):
                    self.advance()
                    return self._lambda(tok)
                self.advance()
                return BackslashRef(name=tok.name, span=tok.span)
            case Radical():
                # `√` is the prefix spelling of `\sqrt(...)`: the operand parses at
                # the unary level (so `√2^2` reads √(2²), `2^√2` works, `√2·3` is
                # `(√2)·3`) and the node rewrites to the ordinary application —
                # evaluation is identical to the ASCII call form. A dangling `√`
                # at EOF is IncompleteInput via the operand's atom parse, exactly
                # like an unclosed parenthesis.
                rad = self.advance()
                operand = self.unary()
                return Call(head=BackslashRef(name="sqrt", span=rad.span),
                            args=(operand,), span=rad.span.to(operand.span))
            case LParen():
                self.advance()
                self.depth += 1
                try:
                    items = self._group_stmts()
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
    parser = _Parser(tokens, aliases)
    node = parser.program()
    if aliases is not None:
        aliases.update(parser.aliases)
    return node
