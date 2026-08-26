"""Compile/exec driver: the Python replacement for interp.rs's tree walker.

`compile_source` runs the frontend then the lowering; `execute` pairs a Compiled unit
with a user environment dict (the engine mutates exactly that dict — variables persist
across calls by sharing it), injects itself as exec globals, and returns the formatted
per-statement output lines in order. EvalError propagates with its span attached;
anything unexpected is mapped back through the line table defensively.
"""

import traceback

from .compiler import Compiled, compile_program
from .parser import parse_program
from .runtime import Engine, EvalError
from .span import Span


def compile_source(src: str) -> Compiled:
    """Frontend + lowering in one step: source text → executable unit."""
    return compile_program(parse_program(src))


def execute(compiled: Compiled, env: dict) -> list[str]:
    """Run a compiled unit against `env`, returning one formatted string per statement."""
    g: dict = {}
    g["_e"] = Engine(env, compiled.spans, compiled.definitions)
    try:
        exec(compiled.code, g)  # noqa: S102 - generated from our own AST only
    except EvalError as e:
        # Script mode echoes every statement that succeeded before the failure, exactly
        # like main.rs's run_and_echo streaming — carry them out on the error.
        e.partial = list(g["_e"].outputs)
        raise
    except Exception as e:
        raise _map_unexpected(e, compiled) from e
    return g["_e"].outputs


def _map_unexpected(e: Exception, compiled: Compiled) -> EvalError:
    """An exception that escaped the engine is a lowering bug; still report it at the
    narrowest span the traceback can name rather than losing the location entirely."""
    lineno = None
    for frame in traceback.extract_tb(e.__traceback__):
        if frame.filename == "<adhoc>":
            lineno = frame.lineno
    span = compiled.line_spans.get(lineno) if lineno is not None else None
    msg = f"internal error: {type(e).__name__}: {e}"
    return EvalError(msg, span)


def run_source(src: str, env: dict | None = None) -> list[str]:
    """Convenience for callers that just want text in, strings out."""
    if env is None:
        env = {}
    return execute(compile_source(src), env)
