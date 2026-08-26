"""Shared diagnostic-printing helpers for the REPL and script-mode drivers. Both funnel
through `diagnostic.render`, which is what keeps REPL and script error output in the same
shape. Errors print to *stdout* (they are part of a session's transcript), matching the
Rust output.rs."""

import sys

from .diagnostic import render
from .parser import ParseError
from .runtime import EvalError

LABEL = "ERROR!"


def render_parse_error(source: str, e: ParseError) -> str:
    return render(source, LABEL, e.msg, e.span)


def render_eval_error(source: str, e: EvalError) -> str:
    if e.span is not None:
        return render(source, LABEL, e.msg, e.span)
    return f"< {LABEL} {e.msg}\n"


def print_parse_error(source: str, e: ParseError) -> None:
    sys.stdout.write(render_parse_error(source, e))


def print_eval_error(source: str, e: EvalError) -> None:
    sys.stdout.write(render_eval_error(source, e))
