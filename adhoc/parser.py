"""Recursive-descent / precedence-climbing parser over the token stream, matching the
precedence table in docs/grammar.md:

    program     ::= statement (";" statement)* ;
    statement   ::= identifier ("=" | ":=") expr | expr ;
    expr        ::= additive ;
    additive    ::= multiplicative (("+" | "-") multiplicative)* ;
    multiplicative ::= juxtaposed (("*" | "/") juxtaposed)* ;
    juxtaposed  ::= unary unary* ;          -- implicit multiplication
    unary       ::= "-" unary | power ;
    power       ::= atom ("^" unary)? ;     -- right-associative
    atom        ::= number | identifier | "\\"-name | "(" expr ")" ;

`power`'s exponent recurses into `unary`, not `power` — that's what makes `2^-1` parse
(unary minus binds inside the exponent) and `2^3^2` right-associate. The base of `^` is a
bare atom, so `-2^2` is `-(2^2)`.

Spans are tagged at each node's *construction* site, not on the way out of each parse
call: the `(expr)` branch of atoms returns the inner node unchanged, and tagging on unwind
would clobber that inner node's own (narrower) span with the paren-inclusive one.
"""

from .lexer import (
    Backslash,
    ColonEq,
    Caret,
    Eq,
    Eof,
    Ident,
    LexError,
    LParen,
    Minus,
    Number,
    Plus,
    RParen,
    Semi,
    Slash,
    Star,
    Token,
    tokenize,
)
from .span import Span
from .syntax import Assign, BackslashRef, BinOp, BinOperator, Node, NumLit, Seq, UnOp, UnaryOperator, Var


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

    # statement ::= identifier ("=" | ":=") expr | expr ;
    def statement(self) -> Node:
        if isinstance(self.peek(), Ident):
            if isinstance(self.peek2(), (Eq, ColonEq)):
                ident_tok = self.advance()
                force = isinstance(self.advance(), ColonEq)
                value = self.expr()
                span = ident_tok.span.to(value.span)
                return Assign(name=ident_tok.ch, force=force, value=value, span=span)
        return self.expr()

    def expr(self) -> Node:
        return self.additive()

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

    # power ::= atom ("^" unary)? ; right-associative; exponent recurses into `unary`.
    def power(self) -> Node:
        base = self.atom()
        if isinstance(self.peek(), Caret):
            self.advance()
            exp = self.unary()
            return BinOp(op=BinOperator.POW, lhs=base, rhs=exp, span=base.span.to(exp.span))
        return base

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
                inner = self.expr()
                self.expect(RParen, "`)`")
                # Deliberately not retagged with the paren-inclusive span — see module docstring.
                return inner
            case _:
                raise self.error_at_current(f"unexpected token {tok.describe}")


def parse_program(src: str) -> Node:
    """Tokenize and parse a complete program from source text."""
    try:
        tokens = tokenize(src)
    except LexError as e:
        raise ParseError(e.msg, e.span) from e
    parser = _Parser(tokens)
    return parser.program()
