using Test
using Adhoc.Parser
using Adhoc.AST
using Adhoc.Eval

# Helper: parse + evaluate a single line in a fresh (or supplied) environment,
# returning the underlying Num value regardless of result kind.
function ev(env::Eval.Env, src::AbstractString)
    r = Eval.run!(env, Parser.parse_program(src))
    r isa Eval.BindResult && return r.value
    r isa Eval.CheckResult && return r.matches
    r isa Eval.BareResult && return r.value
    error("unreachable")
end
ev(src::AbstractString) = ev(Eval.Env(), src)

@testset "parser + eval: precedence" begin
    @test ev("1 + 2 * 3") == 7
    @test ev("(1 + 2) * 3") == 9
    @test ev("-2^2") == -4
    @test ev("2^-1") == 1 // 2
    @test ev("2^3^2") == 512
    env = Eval.Env('x' => BigInt(4))
    @test ev(env, "1/2x") == 1 // 8      # 1/(2x), not (1/2)x
    @test ev(Eval.Env('x' => BigInt(4)), "2x^2") == 32  # 2*(x^2), not (2x)^2
end

@testset "parser + eval: assignment semantics" begin
    env = Eval.Env()
    @test ev(env, "x = 1 + 2") == 3
    @test env['x'] == 3

    @test ev(env, "x = 4") == false      # bound + mismatched value -> compare, false
    @test ev(env, "x = 3") == true       # bound + matching value -> compare, true

    @test ev(env, "x := 4") == 4
    @test env['x'] == 4

    @test_throws Eval.EvalError ev(env, "y := 5")
end

@testset "parser + eval: DESIGN.md worked examples" begin
    @test ev("1 + 2 * 3") == 7
    @test ev("(1 + 2) * 3") == 9
    env = Eval.Env()
    @test ev(env, "x = 1 + 2") == 3
    @test ev(env, "x = 4") == false
    @test ev(env, "x := 4") == 4
    @test_throws Eval.EvalError ev(env, "y := 5")
    @test ev("1/3 + 1/3 + 1/3") == 1
end

@testset "backslash names lex and reference, but are unbound in phase 0" begin
    ast = Parser.parse_program("\\pi")
    @test ast isa AST.BackslashRef
    @test_throws Eval.EvalError ev("\\pi")
    @test_throws Lexer.LexError Parser.parse_program("\\pih")
end

@testset "parse errors" begin
    @test_throws Parser.ParseError Parser.parse_program("1 +")
    @test_throws Parser.ParseError Parser.parse_program("(1 + 2")
end
