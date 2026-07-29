using Test
using Adhoc.AST
using Adhoc.Eval

@testset "eval: AST-level, no parser involved" begin
    @testset "literals and arithmetic" begin
        env = Eval.Env()
        node = AST.BinOp(:+, AST.NumLit("1"), AST.BinOp(:*, AST.NumLit("2"), AST.NumLit("3")))
        @test Eval.eval_expr(env, node) == 7
    end

    @testset "unbound variable reference errors with the expected message" begin
        env = Eval.Env()
        try
            Eval.eval_expr(env, AST.Var('q'))
            @test false  # unreachable
        catch e
            @test e isa Eval.EvalError
            @test occursin("`q` does not exist!", e.msg)
        end
    end

    @testset "force-reassign of an unbound name errors" begin
        env = Eval.Env()
        node = AST.Assign('y', true, AST.NumLit("5"))
        @test_throws Eval.EvalError Eval.run!(env, node)
    end

    @testset "= binds when unbound, checks when bound" begin
        env = Eval.Env()
        r1 = Eval.run!(env, AST.Assign('x', false, AST.NumLit("3")))
        @test r1 isa Eval.BindResult
        @test r1.value == 3

        r2 = Eval.run!(env, AST.Assign('x', false, AST.NumLit("3")))
        @test r2 isa Eval.CheckResult
        @test r2.matches == true

        r3 = Eval.run!(env, AST.Assign('x', false, AST.NumLit("4")))
        @test r3 isa Eval.CheckResult
        @test r3.matches == false
    end

    @testset ":= rebinds when bound" begin
        env = Eval.Env('x' => BigInt(3))
        r = Eval.run!(env, AST.Assign('x', true, AST.NumLit("4")))
        @test r isa Eval.BindResult
        @test env['x'] == 4
    end

    @testset "Seq threads env and returns the last result" begin
        env = Eval.Env()
        node = AST.Seq([
            AST.Assign('a', false, AST.NumLit("2")),
            AST.Assign('b', false, AST.NumLit("3")),
            AST.BinOp(:*, AST.Var('a'), AST.Var('b')),
        ])
        r = Eval.run!(env, node)
        @test r isa Eval.BareResult
        @test r.value == 6
        @test env['a'] == 2 && env['b'] == 3
    end

    @testset "referencing a backslash name errors (unbound in phase 0)" begin
        env = Eval.Env()
        @test_throws Eval.EvalError Eval.eval_expr(env, AST.BackslashRef("pi"))
    end
end
