"""
The numeric seam. `src/eval.jl` never calls Julia's `+`/`*`/... directly on a value that
came from user input — only through the functions here. See `docs/numerics.md`.

Phase-0 backing is `Int`/`BigInt`, `Rational{BigInt}`, and `Float64`. Later phases (symbolic
closed forms, algebraic numbers, RRA) add cases to these functions without touching anything
above this file.
"""
module Num

export AdNum, nadd, nsub, nmul, ndiv, npow, nneg, neq, nshow

const AdNum = Union{BigInt,Rational{BigInt},Float64}

# --- normalization -----------------------------------------------------------

"Collapse an integral rational back to BigInt; widen plain Int to BigInt."
normalize(x::Rational{BigInt}) = denominator(x) == 1 ? numerator(x) : x
normalize(x::BigInt) = x
normalize(x::Integer) = BigInt(x)
normalize(x::Float64) = x
normalize(x::Rational) = normalize(Rational{BigInt}(x))

# --- arithmetic ---------------------------------------------------------------

nadd(a::AdNum, b::AdNum) = normalize(a + b)
nsub(a::AdNum, b::AdNum) = normalize(a - b)
nmul(a::AdNum, b::AdNum) = normalize(a * b)

function ndiv(a::AdNum, b::AdNum)
    if a isa Float64 || b isa Float64
        return Float64(a) / Float64(b)
    end
    iszero(b) && error("division by zero")
    return normalize(Rational{BigInt}(a) // Rational{BigInt}(b))
end

function npow(a::AdNum, b::AdNum)
    if b isa Integer || (b isa Rational && denominator(b) == 1)
        n = b isa Rational ? numerator(b) : BigInt(b)
        if a isa Float64
            return a^Float64(n)
        end
        n >= 0 && return normalize(a^n)
        # negative integer exponent on an exact value: invert then raise
        return ndiv(BigInt(1), normalize(a^(-n)))
    end
    return Float64(a)^Float64(b)
end

nneg(a::AdNum) = normalize(-a)

"Equality for the assignment `x = e` re-check. Exact for BigInt/Rational, approximate float compare."
function neq(a::AdNum, b::AdNum)
    if a isa Float64 || b isa Float64
        return Float64(a) == Float64(b)
    end
    return Rational{BigInt}(a) == Rational{BigInt}(b)
end

"""
Display form. Exact rationals print as `a/b` -- `normalize` already collapses an integral
rational back to BigInt, so this only ever fires for a genuinely non-integer exact value.
Decimal display is reserved for the RRA tier (phase 3), not used here. See docs/numerics.md.
"""
function nshow(a::BigInt)
    return string(a)
end
function nshow(a::Rational{BigInt})
    return string(numerator(a)) * "/" * string(denominator(a))
end
function nshow(a::Float64)
    return string(a)
end

end # module
