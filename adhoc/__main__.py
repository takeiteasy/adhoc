"""Entry point for the `adhoc` binary. Two modes per DESIGN.md's execution-modes section:

    adhoc                 -- REPL
    adhoc run script.ad   -- script mode: same grammar fed a whole file, one `< ...`
                             echo per top-level statement, stopping at the first failure

`--emit-py` (anywhere in argv) prints each executed unit's generated Python source to
stderr before running it — the lowering's debug window.
"""

import argparse
import sys

from . import __version__


def _run_script(path: str, emit_py: bool) -> int:
    """Script mode shares the REPL's grammar and output rendering, but the driver is
    deliberately different, not reused: the whole file is one source (so a caret's
    line-number gutter is meaningful), an unterminated statement at EOF is just a hard
    parse error — there is no continuation prompt to offer a file — and a blank line
    between statements carries no meaning."""
    from adhoc.compiler import compile_program
    from adhoc.driver import execute
    from adhoc.output import print_eval_error, print_parse_error
    from adhoc.parser import ParseError, parse_program
    from adhoc.runtime import EvalError

    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        # Match the Rust driver's io::Error display: `strerror (os error N)`.
        detail = e.strerror or str(e)
        if e.errno is not None:
            detail = f"{detail} (os error {e.errno})"
        print(f"adhoc: cannot read `{path}`: {detail}", file=sys.stderr)
        return 1

    try:
        node = parse_program(source)
    except ParseError as e:
        print_parse_error(source, e)
        return 1

    compiled = compile_program(node)
    if emit_py:
        print(compiled.source, file=sys.stderr)

    env: dict = {}
    try:
        outs = execute(compiled, env)
    except EvalError as e:
        for line in getattr(e, "partial", []):
            print(f"< {line}")
        print_eval_error(source, e)
        return 1

    for line in outs:
        print(f"< {line}")
    return 0


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    emit_py = "--emit-py" in raw
    args = [a for a in raw if a != "--emit-py"]

    parser = argparse.ArgumentParser(
        prog="adhoc",
        description="ad — a math-notation calculator language",
    )
    parser.add_argument("--version", action="version", version=f"adhoc {__version__}")
    parser.add_argument("cmd", nargs="?")
    parser.add_argument("file", nargs="?")
    ns = parser.parse_args(args)

    if ns.cmd is None:
        from .repl import run_repl

        return run_repl(emit_py=emit_py)

    if ns.cmd == "run":
        if ns.file is None:
            print("usage: adhoc run <script.ad>", file=sys.stderr)
            return 1
        return _run_script(ns.file, emit_py=emit_py)

    print(f"adhoc: unrecognized argument `{ns.cmd}`", file=sys.stderr)
    print("usage: adhoc | adhoc run <script.ad>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
