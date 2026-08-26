"""Recursive-descent / precedence-climbing parser over the token stream, matching the
precedence table in docs/grammar.md:

    program     ::= statement (";" statement)* ;
    statement   ::= func-def | string | identifier ("=" | ":=") expr | expr ;
    expr        ::= additive ;
    additive    ::= multiplicative (("+" | "-") multiplicative)* ;
    multiplicative ::= juxtaposed (("*" | "/") juxtaposed)* ;
    juxtaposed  ::= unary unary* ;          -- implicit multiplication
    unary       ::= "-" unary | power ;
    power       ::= postfix ("^" unary)? ;  -- right-associative
    postfix     ::= atom ("(" args ")")* ;  -- trailers attach only to name-ish heads
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

Spans are tagged at each node's *construction* site, not on the way out of each parse
call: the `(expr)` branch of atoms returns the inner node unchanged, and tagging on unwind
would clobber that inner node's own (narrower) span with the paren-inclusive one.
"""

from .lexer import (
    Backslash,
    ColonEq,
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
    FuncDef,
    IfExpr,
    Node,
    NumLit,
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

    # statement ::= func-def | string | identifier ("=" | ":=") expr | expr ;
    def statement(self) -> Node:
        tok = self.peek()
        if isinstance(tok, Str):
            # A string alone is a statement — ignored like a comment (docs/grammar.md).
            self.advance()
            return StrLit(text=tok.text, span=tok.span)
        if isinstance(tok, (Ident, Backslash)):
            if isinstance(self.peek2(), (Eq, ColonEq)):
                ident_tok = self.advance()
                force = isinstance(self.advance(), ColonEq)
                value = self.expr()
                span = ident_tok.span.to(value.span)
                return Assign(name=ident_tok.ch, force=force, value=value, span=span)
            if isinstance(self.peek2(), LParen):
                saved = self.pos
                defn = self._func_def_or_none()
                if defn is not None:
                    return defn
                self.pos = saved  # not the def shape after all — reparse as an application
        return self.expr()

    # func-def ::= identifier "(" params? ")" ("=" | ":=") expr ;
    # Speculative: parse the head shape, and only commit when an `=`/`:=` follows the
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
        if not isinstance(self.peek(), (Eq, ColonEq)):
            return None
        force = isinstance(self.advance(), ColonEq)
        body_stmts = [self.statement()]
        while isinstance(self.peek(), Semi):
            self.advance()
            if isinstance(self.peek(), Eof):
                break
            body_stmts.append(self.statement())
        body = body_stmts[0] if len(body_stmts) == 1 else Seq(
            statements=tuple(body_stmts), span=body_stmts[0].span.to(body_stmts[-1].span)
        )
        span = ident_tok.span.to(body.span)
        name = ident_tok.ch if isinstance(ident_tok, Ident) else ident_tok.name
        return FuncDef(name=name, params=tuple(params), force=force, body=body, span=span)

    def expr(self) -> Node:
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

    def postfix(self) -> Node:
        node = self.atom()
        while isinstance(node, _Parser._NAMEISH) and isinstance(self.peek(), LParen):
            self.advance()
            args: list[Node] = []
            if not isinstance(self.peek(), RParen):  # `f()` — zero-arg calls are legal
                args.append(self.call_arg())
                while isinstance(self.peek(), Comma):
                    self.advance()
                    args.append(self.call_arg())
            rparen = self.expect(RParen, "`)`")
            node = Call(head=node, args=tuple(args), span=node.span.to(rparen.span))
            if (
                isinstance(node.head, BackslashRef)
                and node.head.name == "py"
                and len(node.args) != 1
            ):
                raise ParseError("`\\py` takes exactly one argument", node.span)
            if isinstance(node.head, BackslashRef) and node.head.name == "if":
                if len(node.args) not in (2, 3):
                    raise ParseError("`\\if` takes two or three arguments", node.span)
                node = IfExpr(node.span, node.args[0], node.args[1],
                              node.args[2] if len(node.args) == 3 else None)
        return node

    # args ::= expr | string — a string may be a whole argument (the `\py` case) but
    # never an operand inside one: `"a" + 1` stays a parse error at the quote.
    def call_arg(self) -> Node:
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
