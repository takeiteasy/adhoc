"""Recursive-descent / precedence-climbing parser over the token stream, matching the
precedence table in docs/grammar.md:

    program     ::= statement (";" statement)* ;
    statement   ::= func-def | string | identifier "=" expr | expr ;
    expr        ::= additive ;
    additive    ::= multiplicative (("+" | "-") multiplicative)* ;
    multiplicative ::= juxtaposed (("*" | "/") juxtaposed)* ;
    juxtaposed  ::= unary unary* ;          -- implicit multiplication
    unary       ::= "-" unary | power ;
    power       ::= postfix ("^" unary)? ;  -- right-associative
    postfix     ::= atom ("(" args ")")* ;  -- trailers attach only to name-ish heads
    args        ::= (expr | string | kwarg) ("," ...)* ;   kwarg ::= name "=" value ;
    atom        ::= number | identifier | "\\"-name | "(" expr ")" ;

`power`'s exponent recurses into `unary`, not `power` — that's what makes `2^-1` parse
(unary minus binds inside the exponent) and `2^3^2` right-associate. The base of `^` is a
postfix node, so `-2^2` is `-(2^2)` and `f(x)^2` squares the result.

Postfix application is *syntactically* name-headed: a `(…)` trailer attaches only when the
head so far is a name-ish node (`Var`, `BackslashRef`, or another `Call`). Number-headed
parens never apply — `2(x+1)` still parses as juxtaposed multiplication. Whether a parsed
call applies or falls back to multiplication is decided at evaluation (dynamic
juxtaposition, docs/grammar.md). Strings are literals, not values:
one alone may be a statement (ignored, comment-like) and one may be a whole call argument,
but anywhere else in an expression it is a parse error at the opening quote. The function
definition shape `f(x) = body` is recognized at statement level and parsed into `FuncDef`;
function bodies may contain semicolon-separated statements.

Two builtin heads are *special forms* (DESIGN.md, "equality and =" case 3): their first
argument is a binding, not an application argument. `\\sum`/`\\prod`/`Σ`/`Π` parse
`(i=a..b)` into a range and rewrite to `Fold`; `\\lim(x=a)` rewrites to `Limit`. In both,
the body extends greedily over the rest of the current expression, up to the enclosing
delimiter — parenthesize to end it earlier. Recognition commits on the `(ident =` shape
alone (bare `=` cannot occur inside a general expression); any other use of those heads
goes through ordinary application parsing.

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
    IdenticalTo,
    LexError,
    LParen,
    Less,
    LessEq,
    Minus,
    Number,
    Plus,
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
from .span import Span
from .syntax import (
    Assign,
    BackslashRef,
    BinOp,
    BinOperator,
    Call,
    Compare,
    CompareOperator,
    ConstAssign,
    Fold,
    FuncDef,
    IfExpr,
    Import,
    KwArg,
    Limit,
    Node,
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


_ATOM_STARTERS = (Number, Ident, Backslash, LParen)


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

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

    def error_at_current(self, msg: str) -> ParseError:
        tok = self.peek()
        if isinstance(tok, Eof):
            return IncompleteInput(msg, tok.span)
        return ParseError(msg, tok.span)

    def expect(self, cls: type, what: str) -> Token:
        if isinstance(self.peek(), cls):
            return self.advance()
        found = self.peek().describe
        raise self.error_at_current(f"expected {what}, found {found}")

    def _is_atom_starter(self) -> bool:
        return isinstance(self.peek(), _ATOM_STARTERS)

    # program ::= statement (";" statement)* ;
    def program(self) -> Node:
        statements = [self.statement()]
        while isinstance(self.peek(), Semi):
            self.advance()
            if isinstance(self.peek(), Eof):
                break
            statements.append(self.statement())
        if not isinstance(self.peek(), Eof):
            found = self.peek().describe
            raise self.error_at_current(f"unexpected token {found}")
        if len(statements) == 1:
            return statements[0]
        span = statements[0].span.to(statements[-1].span)
        return Seq(statements=tuple(statements), span=span)

    # statement ::= func-def | const-stmt | string
    #             | identifier "=" expr | expr ;
    def statement(self) -> Node:
        tok = self.peek()
        if isinstance(tok, Str):
            # A string alone is a statement — ignored like a comment (docs/grammar.md).
            self.advance()
            return StrLit(text=tok.text, span=tok.span)
        if isinstance(tok, Backslash) and tok.name == "const":
            return self._const_statement()
        if (
            isinstance(tok, Backslash)
            and tok.name in ("import", "pyimport")
            and isinstance(self.peek2(), LParen)
        ):
            return self._import_statement(tok)
        if isinstance(tok, (Ident, Backslash)):
            if isinstance(self.peek2(), IdenticalTo):
                ident_tok = self.advance()
                self.advance()  # ≡
                value = self.expr()
                name = ident_tok.ch if isinstance(ident_tok, Ident) else ident_tok.name
                return ConstAssign(name=name, value=value,
                                   span=ident_tok.span.to(value.span))
            if isinstance(self.peek2(), Eq):
                ident_tok = self.advance()
                self.advance()  # `=` — bind-or-check, there is no force spelling
                value = self.expr()
                span = ident_tok.span.to(value.span)
                name = ident_tok.ch if isinstance(ident_tok, Ident) else ident_tok.name
                return Assign(name=name, value=value, span=span)
            if isinstance(self.peek2(), LParen):
                saved = self.pos
                defn = self._func_def_or_none()
                if defn is not None:
                    return defn
                self.pos = saved  # not the def shape after all — reparse as an application
        return self.expr()

    # const-stmt ::= "\const" name "=" expr
    #              | "\const" name "(" params? ")" "=" statement (";" statement)* ;
    # Committed form (unlike the speculative plain func-def): once `\const` names a
    # binding, anything but `=` or a parameter list is a genuine parse error.
    def _const_statement(self) -> Node:
        const_tok = self.advance()  # the `\const` token
        if not isinstance(self.peek(), (Ident, Backslash)):
            raise self.error_at_current("expected a name after `\\const`")
        ident_tok = self.advance()
        name = ident_tok.ch if isinstance(ident_tok, Ident) else ident_tok.name
        if isinstance(self.peek(), LParen):
            self.advance()
            params = self._func_params()
            self.expect(Eq, "`=`")
            body = self._func_body()
            return FuncDef(name=name, params=params, body=body, const=True,
                           span=const_tok.span.to(body.span))
        self.expect(Eq, "`=`")
        value = self.expr()
        return ConstAssign(name=name, value=value, span=const_tok.span.to(value.span))

    # import-stmt ::= "\\import" "(" string (":" member ("," member)*)? ")" ;
    # pyimport-stmt ::= "\\pyimport" "(" string ":" member ("," member)* ")" ;
    # Statement-level only: an import binds names and produces no output, so it has
    # no value — in expression position the head stays an ordinary unbound name and
    # fails at evaluation with a usage message (the `\py`/`\if` pattern). Member
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
                    members.append(tok.ch if isinstance(tok, Ident) else tok.name)
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

    def _func_params(self) -> tuple[str, ...]:
        params: list[str] = []
        while True:
            tok = self.peek()
            if isinstance(tok, Ident):
                params.append(tok.ch)
                self.advance()
            elif isinstance(tok, RParen):
                break
            else:
                raise self.error_at_current(
                    f"expected a parameter name, found {tok.describe}")
            if isinstance(self.peek(), Comma):
                self.advance()
            else:
                break
        self.expect(RParen, "`)`")
        return tuple(params)

    def _func_body(self) -> Node:
        body_stmts = [self.statement()]
        while isinstance(self.peek(), Semi):
            self.advance()
            if isinstance(self.peek(), Eof):
                break
            body_stmts.append(self.statement())
        if len(body_stmts) == 1:
            return body_stmts[0]
        return Seq(statements=tuple(body_stmts),
                   span=body_stmts[0].span.to(body_stmts[-1].span))

    # func-def ::= identifier "(" params? ")" "=" statement (";" statement)* ;
    # Speculative: parse the head shape, and only commit when an `=` follows the
    # closing paren; anything else restores the position so `f(x)` reparses as an
    # application. Parameter validity is enforced only once committed.
    def _func_def_or_none(self) -> FuncDef | None:
        ident_tok = self.advance()
        self.advance()  # LParen — caller verified peek2
        params: list[str] = []
        while True:
            tok = self.peek()
            if isinstance(tok, Ident):
                params.append(tok.ch)
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
        name = ident_tok.ch if isinstance(ident_tok, Ident) else ident_tok.name
        return FuncDef(name=name, params=tuple(params), body=body, span=span)

    def expr(self) -> Node:
        return self.range_expr()

    # Range commas are only consumed when they introduce a following `..`, preserving
    # ordinary call argument commas such as `f(1, 2)`.
    def range_expr(self) -> Node:
        start = self.comparison()
        second = None
        if isinstance(self.peek(), Comma):
            saved = self.pos
            self.advance()
            candidate = self.comparison()
            if not isinstance(self.peek(), DotDot):
                self.pos = saved
            else:
                second = candidate
        if not isinstance(self.peek(), DotDot):
            return start
        dotdot = self.advance()
        end = None if isinstance(self.peek(), (Comma, RParen, Semi, Eof)) else self.comparison()
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
    # so `a - b` always parses as subtraction, never as `a * (-b)`.
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
    # Call), so `f(x)` applies while `2(x+1)` falls through to juxtaposition.
    _NAMEISH = (Var, BackslashRef, Call)

    # Special forms recognized in postfix position (DESIGN.md "equality and =", case 3):
    # a closed list of builtins whose first argument is a binding, not a general
    # equality expression. `\sum`≡`Σ`, `\prod`≡`Π`; `\lim` has no unicode spelling.
    _FOLD_HEADS = {("sum", None): BinOperator.ADD, ("prod", None): BinOperator.MUL,
                   (None, "Σ"): BinOperator.ADD, (None, "Π"): BinOperator.MUL}
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
            args: tuple[Node, ...] = ()
            kwargs: tuple[KwArg, ...] = ()
            if not isinstance(self.peek(), RParen):  # `f()` — zero-arg calls are legal
                items: list[Node] = [self.call_arg()]
                while isinstance(self.peek(), Comma):
                    self.advance()
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
            if isinstance(node.head, BackslashRef) and node.head.name == "if":
                if node.kwargs or len(node.args) not in (2, 3):
                    raise ParseError("`\\if` takes two or three arguments", node.span)
                node = IfExpr(node.span, node.args[0], node.args[1],
                              node.args[2] if len(node.args) == 3 else None)
        return node

    def _fold_head(self, node: Node) -> BinOperator | None:
        """The fold operator when `node` is a fold head, else None."""
        if isinstance(node, BackslashRef) and (node.name, None) in _Parser._FOLD_HEADS:
            return _Parser._FOLD_HEADS[(node.name, None)]
        if isinstance(node, Var) and (None, node.ch) in _Parser._FOLD_HEADS:
            return _Parser._FOLD_HEADS[(None, node.ch)]
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
        """The `(ident =` shape that commits the special form."""
        return (
            isinstance(self.look(1), Ident)
            and isinstance(self.look(2), Eq)
        )

    def _special_form(self, head: Node, fold_op: BinOperator | None) -> Node:
        label = self._LIMIT_LABEL if fold_op is None else self._form_label(head)
        self.advance()  # LParen — caller verified
        var = self.advance().ch
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
            case Var(ch=ch):
                return ch
            case _:
                return "?"

    # args ::= (expr | string | kwarg) ("," ...)* — a string may be a whole argument
    # (the `\py` case) but never an operand inside one: `"a" + 1` stays a parse error
    # at the quote. A kwarg is `name=value`; the `=` seen directly after a name token
    # commits it, and bare `=` cannot occur inside a general expression, so nothing
    # else can want that shape. Multi-character names take the `\` sigil (`\dpi=300`).
    def call_arg(self) -> Node:
        tok = self.peek()
        if isinstance(tok, (Ident, Backslash)) and isinstance(self.look(1), Eq):
            name_tok = self.advance()
            self.advance()  # `=`
            value = self.call_value()
            name = name_tok.ch if isinstance(name_tok, Ident) else name_tok.name
            return KwArg(name=name, value=value, span=name_tok.span.to(value.span))
        return self.call_value()

    def call_value(self) -> Node:
        if isinstance(self.peek(), Str):
            tok = self.advance()
            return StrLit(text=tok.text, span=tok.span)
        return self.expr()

    # atom ::= number | identifier | "\"-name | "(" expr ")" ;
    def atom(self) -> Node:
        tok = self.peek()
        match tok:
            case Number():
                self.advance()
                return NumLit(text=tok.text, span=tok.span)
            case Ident():
                self.advance()
                return Var(ch=tok.ch, span=tok.span)
            case Backslash():
                self.advance()
                return BackslashRef(name=tok.name, span=tok.span)
            case LParen():
                self.advance()
                items = [self.statement()]
                while isinstance(self.peek(), Semi):
                    semi = self.advance()
                    if isinstance(self.peek(), RParen):
                        raise ParseError("expected `)`, found `;`", semi.span)
                    items.append(self.statement())
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
                # Deliberately not retagged with the paren-inclusive span — see module docstring.
                return inner
            case _:
                raise self.error_at_current(f"unexpected token {tok.describe}")


def parse_program(src: str) -> Node:
    """Tokenize and parse a complete program from source text."""
    try:
        tokens = tokenize(src)
    except UnterminatedString as e:
        # An open quote at EOF is incomplete input, not a dead end — the REPL offers a
        # continuation prompt exactly like an unclosed parenthesis.
        raise IncompleteInput(e.msg, e.span) from e
    except LexError as e:
        raise ParseError(e.msg, e.span) from e
    parser = _Parser(tokens)
    return parser.program()
