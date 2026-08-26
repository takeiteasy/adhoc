"""Entry point for the `adhoc` binary.

Two modes, per DESIGN.md's execution-modes section:

    adhoc                 -- REPL (arrives with the REPL port, rewrite stage 4)
    adhoc run script.ad   -- script mode (same stage)

Only --version works today; the frontend stages of the rewrite
(docs/rewrite-plan.md) fill the rest in.
"""

import argparse

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="adhoc",
        description="ad — a math-notation calculator language",
    )
    parser.add_argument("--version", action="version", version=f"adhoc {__version__}")
    parser.parse_args(argv)
    parser.error("the REPL and script runner are not ported yet (see docs/rewrite-plan.md)")


if __name__ == "__main__":
    main()
