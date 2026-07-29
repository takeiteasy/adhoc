"""
Tree-walking evaluator for phase-0 `ad`. Disposable: phase 4 replaces this with an
interaction-net engine (see `docs/architecture.md`). All arithmetic goes through `Num`.
"""
module Eval

using ..AST
using ..Num

export Env, EvalError, EvalResult, BindResult, CheckResult, BareResult, run!, eval_expr

const Env = Dict{Char,Num.AdNum}

struct EvalError <: Exception
    msg::String
end
Base.showerror(io::IO, e::EvalError) = print(io, "ERROR! $(e.msg)")

abstract type EvalResult end
"`x = e` / `x := e` binding (or rebinding)."
struct BindResult <: EvalResult
    name::Char
    value::Num.AdNum
end
"`x = e` re-check against an already-bound `x`. A printed form only -- no boolean type yet."
struct CheckResult <: EvalResult
    matches::Bool
end
"A bare expression statement."
struct BareResult <: EvalResult
    value::Num.AdNum
end

function parse_literal(text::AbstractString)::Num.AdNum
    if occursin('.', text)
        return parse(Float64, text)
    end
    return parse(BigInt, text)
end

eval_expr(env::Env, node::AST.NumLit) = parse_literal(node.value)

function eval_expr(env::Env, node::AST.Var)
    haskey(env, node.name) && return env[node.name]
    throw(EvalError("`$(node.name)` does not exist!"))
end

function eval_expr(env::Env, node::AST.BackslashRef)
    throw(EvalError("`\\$(node.name)` is not bound (phase 0 defines no builtins yet)"))
end

function eval_expr(env::Env, node::AST.UnOp)
    return Num.nneg(eval_expr(env, node.operand))
end

function eval_expr(env::Env, node::AST.BinOp)
    lhs = eval_expr(env, node.lhs)
    rhs = eval_expr(env, node.rhs)
    node.op == :+ && return Num.nadd(lhs, rhs)
    node.op == :- && return Num.nsub(lhs, rhs)
    node.op == :* && return Num.nmul(lhs, rhs)
    node.op == :/ && return Num.ndiv(lhs, rhs)
    node.op == :^ && return Num.npow(lhs, rhs)
    error("internal error: unknown operator $(node.op)")
end

function run!(env::Env, node::AST.Assign)::EvalResult
    value = eval_expr(env, node.value)
    if node.force
        haskey(env, node.name) || throw(EvalError("`$(node.name)` does not exist!"))
        env[node.name] = value
        return BindResult(node.name, value)
    end
    if haskey(env, node.name)
        return CheckResult(Num.neq(env[node.name], value))
    end
    env[node.name] = value
    return BindResult(node.name, value)
end

function run!(env::Env, node::AST.Seq)::EvalResult
    result = nothing
    for stmt in node.statements
        result = run!(env, stmt)
    end
    result === nothing && throw(EvalError("empty statement sequence"))
    return result
end

# Fallback: anything else is a bare expression.
run!(env::Env, node::AST.Node)::EvalResult = BareResult(eval_expr(env, node))

end # module
