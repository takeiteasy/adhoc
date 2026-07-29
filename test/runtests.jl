using Test

include(joinpath(@__DIR__, "..", "src", "Adhoc.jl"))
using .Adhoc

@testset "Adhoc phase 0" begin
    include("test_num.jl")
    include("test_lexer.jl")
    include("test_parser.jl")
    include("test_eval.jl")
end
