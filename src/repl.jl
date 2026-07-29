"""
REPL glue for phase-0 `ad`: `> ` prompt, `< `-prefixed output, per-line error recovery,
clean exit on EOF. Disposable, same as `src/eval.jl` -- see `docs/architecture.md`.
"""
module Repl

using ..Lexer
using ..Parser
using ..Eval
using ..Num

export run_repl

format_result(r::Eval.BindResult) = "$(r.name) = $(Num.nshow(r.value))"
format_result(r::Eval.CheckResult) = string(r.matches)
format_result(r::Eval.BareResult) = "= $(Num.nshow(r.value))"

function run_repl(io_in::IO=stdin, io_out::IO=stdout)
    env = Eval.Env()
    while !eof(io_in)
        print(io_out, "> ")
        flush(io_out)
        line = readline(io_in)
        isempty(strip(line)) && continue
        try
            tokens = Lexer.tokenize(line)
            length(tokens) == 1 && continue   # blank or comment-only line: nothing to do
            ast = Parser.parse_program(line)
            result = Eval.run!(env, ast)
            println(io_out, "< ", format_result(result))
        catch e
            if e isa Lexer.LexError || e isa Parser.ParseError || e isa Eval.EvalError
                println(io_out, "< ERROR! ", e.msg)
            else
                rethrow()
            end
        end
    end
    println(io_out)
end

end # module
