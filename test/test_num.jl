using Test
using Adhoc.Num

@testset "Num seam" begin
    @testset "exact rational arithmetic" begin
        third = Num.ndiv(BigInt(1), BigInt(3))
        s = Num.nadd(Num.nadd(third, third), third)
        @test s == BigInt(1)           # collapses to an exact integer, no float drift
        @test s isa BigInt
    end

    @testset "integer division collapses when exact" begin
        @test Num.ndiv(BigInt(6), BigInt(3)) == BigInt(2)
        @test Num.ndiv(BigInt(6), BigInt(3)) isa BigInt
        @test Num.ndiv(BigInt(1), BigInt(2)) == 1 // 2
    end

    @testset "npow keeps rationals exact for integer exponents" begin
        @test Num.npow(BigInt(2), BigInt(10)) == BigInt(1024)
        @test Num.npow(Rational{BigInt}(1, 2), BigInt(2)) == Rational{BigInt}(1, 4)
        @test Num.npow(BigInt(2), BigInt(-1)) == Rational{BigInt}(1, 2)
    end

    @testset "division by zero errors" begin
        @test_throws ErrorException Num.ndiv(BigInt(1), BigInt(0))
    end

    @testset "neq" begin
        @test Num.neq(BigInt(4), Rational{BigInt}(8, 2))
        @test !Num.neq(BigInt(4), BigInt(5))
    end
end
