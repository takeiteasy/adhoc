"""
Precedence-climbing parser for phase-0 `ad`, over the grammar in `docs/grammar.md`.
"""
module Parser

using ..Lexer: Token, tokenize
using ..AST

export parse_program, ParseError

struct ParseError <: Exception
    msg::String
    pos::Int
end
Base.showerror(io::IO, e::ParseError) = print(io, "PARSE ERROR at column $(e.pos): $(e.msg)")

mutable struct TokenStream
    tokens::Vector{Token}
    pos::Int
end
TokenStream(tokens::Vector{Token}) = TokenStream(tokens, 1)

peek(ts::TokenStream, offset::Int=0) = ts.tokens[min(ts.pos + offset, length(ts.tokens))]

function consume!(ts::TokenStream)
    tok = peek(ts)
    ts.pos += 1
    return tok
end

function expect!(ts::TokenStream, kind::Symbol)
    tok = peek(ts)
    tok.kind == kind || throw(ParseError("expected $kind, got $(tok.kind) `$(tok.text)`", tok.pos))
    return consume!(ts)
end

# Tokens that can start an atom, and so continue a juxtaposition (implicit-multiply) chain.
# Deliberately excludes :minus -- "a - b" must parse as subtraction, not "a * (-b)".
const ATOM_STARTERS = (:number, :ident, :backslash, :lparen)

function parse_program(src::AbstractString)::AST.Node
    tokens = tokenize(src)
    ts = TokenStream(tokens)
    stmts = AST.Node[parse_statement!(ts)]
    while peek(ts).kind == :semi
        consume!(ts)
        peek(ts).kind == :eof && break
        push!(stmts, parse_statement!(ts))
    end
    tok = peek(ts)
    tok.kind == :eof || throw(ParseError("unexpected token `$(tok.text)`", tok.pos))
    return length(stmts) == 1 ? stmts[1] : AST.Seq(stmts)
end

function parse_statement!(ts::TokenStream)::AST.Node
    if peek(ts).kind == :ident && peek(ts, 1).kind in (:eq, :coloneq)
        name_tok = consume!(ts)
        op_tok = consume!(ts)
        value = parse_expr!(ts)
        return AST.Assign(name_tok.text[1], op_tok.kind == :coloneq, value)
    end
    return parse_expr!(ts)
end

function parse_expr!(ts::TokenStream)::AST.Node
    return parse_additive!(ts)
end

function parse_additive!(ts::TokenStream)::AST.Node
    node = parse_multiplicative!(ts)
    while peek(ts).kind in (:plus, :minus)
        op = consume!(ts).kind == :plus ? :+ : :-
        rhs = parse_multiplicative!(ts)
        node = AST.BinOp(op, node, rhs)
    end
    return node
end

function parse_multiplicative!(ts::TokenStream)::AST.Node
    node = parse_juxtaposed!(ts)
    while peek(ts).kind in (:star, :slash)
        op = consume!(ts).kind == :star ? :* : :/
        rhs = parse_juxtaposed!(ts)
        node = AST.BinOp(op, node, rhs)
    end
    return node
end

function parse_juxtaposed!(ts::TokenStream)::AST.Node
    node = parse_unary!(ts)
    while peek(ts).kind in ATOM_STARTERS
        rhs = parse_unary!(ts)
        node = AST.BinOp(:*, node, rhs)
    end
    return node
end

function parse_unary!(ts::TokenStream)::AST.Node
    if peek(ts).kind == :minus
        consume!(ts)
        return AST.UnOp(:-, parse_unary!(ts))
    end
    return parse_power!(ts)
end

function parse_power!(ts::TokenStream)::AST.Node
    base = parse_atom!(ts)
    if peek(ts).kind == :caret
        consume!(ts)
        exponent = parse_unary!(ts)   # right-assoc; allows `2^-1`, `2^3^2`
        return AST.BinOp(:^, base, exponent)
    end
    return base
end

function parse_atom!(ts::TokenStream)::AST.Node
    tok = peek(ts)
    if tok.kind == :number
        consume!(ts)
        return AST.NumLit(tok.text)
    elseif tok.kind == :ident
        consume!(ts)
        return AST.Var(tok.text[1])
    elseif tok.kind == :backslash
        consume!(ts)
        return AST.BackslashRef(tok.text)
    elseif tok.kind == :lparen
        consume!(ts)
        inner = parse_expr!(ts)
        expect!(ts, :rparen)
        return inner
    else
        throw(ParseError("unexpected token `$(tok.text)`", tok.pos))
    end
end

end # module
