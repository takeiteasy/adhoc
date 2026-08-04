"""
Lexer for phase-0 `ad`. Whitespace-insensitive, unicode-aware. See `docs/grammar.md`.
"""
module Lexer

export Token, tokenize, LexError

struct LexError <: Exception
    msg::String
    pos::Int
end
Base.showerror(io::IO, e::LexError) = print(io, "LEX ERROR at column $(e.pos): $(e.msg)")

"""
`kind` is one of: :number, :ident, :backslash, :plus, :minus, :star, :slash, :caret,
:eq, :coloneq, :lparen, :rparen, :semi, :eof.

`text` holds the literal text (number as written, the single identifier character, or the
bare name after `\\` for :backslash tokens).
"""
struct Token
    kind::Symbol
    text::String
    pos::Int
end

# The complete set of `\`-names the language knows about (see docs/grammar.md and
# docs/language.md). Phase 0 binds none of them, but seeding the full table now means a
# `\`-token always lexes cleanly and fails, if at all, at eval time as an unbound name --
# not at the lexer as an unknown token. Unrecognized `\`-names remain a lex error, which is
# what catches typos.
const KNOWN_BACKSLASH_NAMES = Set([
    "pi", "sum", "prod", "sqrt", "cup", "cap", "in", "subseteq", "setminus", "circ",
    "lim", "const", "arr", "expr", "if", "otherwise", "sin", "cos", "tan", "ln",
    "solve", "simplify", "expand", "factor", "eval", "body", "map", "fold", "filter",
    "graph", "infix", "and", "or", "not",
])

function tokenize(src::AbstractString)::Vector{Token}
    chars = collect(src)
    n = length(chars)
    i = 1
    tokens = Token[]

    isidentchar(c::Char) = isletter(c)

    while i <= n
        c = chars[i]

        if isspace(c)
            i += 1
            continue
        end

        if c == '-' && i < n && chars[i+1] == '-'
            # line comment: skip to newline or EOF
            while i <= n && chars[i] != '\n'
                i += 1
            end
            continue
        end

        pos = i

        if isdigit(c)
            j = i
            while j <= n && isdigit(chars[j])
                j += 1
            end
            if j <= n && chars[j] == '.' && j + 1 <= n && isdigit(chars[j+1])
                j += 1
                while j <= n && isdigit(chars[j])
                    j += 1
                end
            end
            push!(tokens, Token(:number, String(chars[i:j-1]), pos))
            i = j
            continue
        end

        if c == '\\'
            j = i + 1
            while j <= n && isletter(chars[j])
                j += 1
            end
            name = String(chars[i+1:j-1])
            isempty(name) && throw(LexError("bare `\\` with no name following", pos))
            name in KNOWN_BACKSLASH_NAMES ||
                throw(LexError("unknown \\-name `\\$name`", pos))
            push!(tokens, Token(:backslash, name, pos))
            i = j
            continue
        end

        if isidentchar(c)
            push!(tokens, Token(:ident, string(c), pos))
            i += 1
            continue
        end

        if c == ':' && i < n && chars[i+1] == '='
            push!(tokens, Token(:coloneq, ":=", pos))
            i += 2
            continue
        end

        kind = c == '+' ? :plus :
               c == '-' ? :minus :
               c == '*' ? :star :
               c == '/' ? :slash :
               c == '^' ? :caret :
               c == '=' ? :eq :
               c == '(' ? :lparen :
               c == ')' ? :rparen :
               c == ';' ? :semi :
               nothing

        if kind === nothing
            throw(LexError("unexpected character `$c`", pos))
        end

        push!(tokens, Token(kind, string(c), pos))
        i += 1
    end

    push!(tokens, Token(:eof, "", n + 1))
    return tokens
end

end # module
