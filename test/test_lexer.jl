using Test
using Adhoc.Lexer

@testset "lexer" begin
    @testset "numbers" begin
        toks = tokenize("3 12.34")
        @test toks[1] == Token(:number, "3", 1)
        @test toks[2].kind == :number
        @test toks[2].text == "12.34"
        @test toks[end].kind == :eof
    end

    @testset "identifiers, ascii and unicode" begin
        toks = tokenize("ab π")
        @test [t.kind for t in toks[1:3]] == [:ident, :ident, :ident]
        @test toks[1].text == "a"
        @test toks[2].text == "b"
        @test toks[3].text == "π"
    end

    @testset "backslash names" begin
        toks = tokenize("\\pi + \\sin(x)")
        @test toks[1] == Token(:backslash, "pi", 1)
        kinds = [t.kind for t in toks]
        @test :backslash in kinds
        @test count(==(:backslash), kinds) == 2
    end

    @testset "unknown backslash name errors" begin
        @test_throws Lexer.LexError tokenize("\\notaname")
    end

    @testset "comments are discarded" begin
        toks = tokenize("1 -- comment\n+ 2")
        @test [t.kind for t in toks] == [:number, :plus, :number, :eof]
    end

    @testset "operators" begin
        toks = tokenize("+ - * / ^ = := ( ) ;")
        @test [t.kind for t in toks[1:end-1]] ==
              [:plus, :minus, :star, :slash, :caret, :eq, :coloneq, :lparen, :rparen, :semi]
    end

    @testset "unexpected character errors" begin
        @test_throws Lexer.LexError tokenize("1 & 2")
    end
end
