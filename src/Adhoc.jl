module Adhoc

include("num.jl")
include("lexer.jl")
include("ast.jl")
include("parser.jl")
include("eval.jl")
include("repl.jl")

using .Repl: run_repl

export run_repl

function main(args::Vector{String}=String[])
    run_repl()
end

end # module
