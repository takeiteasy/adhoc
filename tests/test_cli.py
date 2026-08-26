import subprocess
import sys

import adhoc


def run_cli(*args, stdin=""):
    return subprocess.run(
        [sys.executable, "-m", "adhoc", *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_version_flag():
    r = run_cli("--version")
    assert r.returncode == 0
    assert r.stdout.strip() == f"adhoc {adhoc.__version__}"


def test_no_args_starts_repl_and_exits_cleanly_on_eof():
    r = run_cli()
    assert r.returncode == 0
    assert r.stdout == "> \n"


def test_unrecognized_argument():
    r = run_cli("bogus")
    assert r.returncode != 0
    assert "unrecognized argument" in r.stderr
