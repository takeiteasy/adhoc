"""
AST for phase-0 `ad`. Deliberately small — later phases add node types; phase 4 compiles
these to an interaction net rather than changing this shape. See `docs/architecture.md`.
"""
module AST

export Node, NumLit, Var, BackslashRef, BinOp, UnOp, Assign, Seq

abstract type Node end

struct NumLit <: Node
    value::String   # raw literal text; parsed to a Num.AdNum during eval
end

struct Var <: Node
    name::Char
end

"""
Reference to a `\\`-name (e.g. `\\pi`). Phase 0 seeds the lexer's name table but binds none
of them, so evaluating one of these always raises an unbound-name error -- see docs/language.md.
"""
struct BackslashRef <: Node
    name::String
end

struct BinOp <: Node
    op::Symbol       # :+, :-, :*, :/, :^
    lhs::Node
    rhs::Node
end

struct UnOp <: Node
    op::Symbol       # :-
    operand::Node
end

"`force` distinguishes `:=` (true) from `=` (false, assign-or-check)."
struct Assign <: Node
    name::Char
    force::Bool
    value::Node
end

struct Seq <: Node
    statements::Vector{Node}
end

end # module
