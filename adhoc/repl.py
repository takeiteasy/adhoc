"""REPL driver. Binary-side glue over the library: prompt, history, multi-line
continuation, error recovery.

Multi-line continuation: `> ` when nothing is pending, `. ` while continuing. An
`IncompleteInput` parse buffers the line for the next round (joined with `\\n`); ad's
whitespace is insignificant, so nothing else could ever close an unclosed continuation —
hence a **blank line cancels** the pending statement rather than being swallowed as
whitespace.

History lives at `$ADHOC_HISTORY` (default `~/.adhoc_history`) and is only touched on an
interactive terminal; piped stdin (scripts feeding the REPL, tests) goes through plain
reads so the prompt sequence stays observable in transcripts.
"""

import os
import sys

from .compiler import compile_program
from .driver import execute
from .lexer import Eof, LexError, tokenize
from .output import print_eval_error, print_parse_error
from .parser import ALIAS_SEED, IncompleteInput, ParseError, parse_program
from .runtime import EvalError

_EOF = object()
_INTERRUPTED = object()


def _history_path() -> str:
    if p := os.environ.get("ADHOC_HISTORY"):
        return p
    home = os.environ.get("HOME", ".")
    return os.path.join(home, ".adhoc_history")


def _is_empty_source(source: str) -> bool:
    """A blank line, or a line that lexes down to nothing but `--comment` text — i.e.
    only the EOF token comes out of tokenizing it."""
    try:
        toks = tokenize(source)
    except LexError:
        return False
    return len(toks) == 1 and isinstance(toks[0], Eof)


def _read(prompt: str):
    """One input line. input() prints the prompt to stdout and flushes either way, which
    is exactly the observable behavior the Rust Stdin reader had; importing readline
    upgrades it to in-process editing/history when interactive."""
    try:
        return input(prompt)
    except EOFError:
        return _EOF
    except KeyboardInterrupt:
        return _INTERRUPTED


def run_repl(emit_py: bool = False) -> int:
    hist_path = _history_path()
    interactive = sys.stdin.isatty()
    readline = None
    if interactive:
        try:
            import readline as _readline

            readline = _readline
            try:
                readline.read_history_file(hist_path)
            except OSError:
                pass
        except ImportError:
            pass

    env: dict = {}
    consts: set = set()  # user-declared constant names, protected for the session
    modules: dict = {}  # session import registry: `\import` evaluates each file once
    aliases: dict = dict(ALIAS_SEED)  # session alias map; `\alias`/`\dual` extend it
    pending = ""

    while True:
        prompt = ". " if pending else "> "
        got = _read(prompt)

        if got is _EOF:
            if pending:
                # Re-parse the buffered statement so its (still incomplete) diagnostic
                # renders instead of exiting silently mid-statement.
                try:
                    parse_program(pending, aliases, consts)
                except ParseError as e:
                    print_parse_error(pending, e)
            print()
            break

        if got is _INTERRUPTED:
            pending = ""
            continue

        line = got
        if pending and line.strip() == "":
            pending = ""
            print("-- input cancelled")
            continue
        if not pending and line.strip() == "":
            continue

        source = f"{pending}\n{line}" if pending else line

        if not pending and _is_empty_source(source):
            continue

        try:
            node = parse_program(source, aliases, consts)
        except IncompleteInput:
            pending = source
            continue
        except ParseError as e:
            pending = ""
            print_parse_error(source, e)
            continue

        pending = ""
        compiled = compile_program(node)
        if emit_py:
            print(compiled.source, file=sys.stderr)
        try:
            outs = execute(compiled, env, consts, modules)
        except EvalError as e:
            print_eval_error(source, e)
            continue

        if interactive and readline is not None:
            try:
                readline.add_history(line)
            except Exception:
                pass
        # A statement can produce no output (a lone string is a comment-like no-op) —
        # nothing to echo then, not even an empty `< ` line.
        if not outs:
            continue
        print(f"< {outs[-1]}")

    if interactive and readline is not None:
        try:
            readline.write_history_file(hist_path)
        except OSError:
            pass
    return 0
