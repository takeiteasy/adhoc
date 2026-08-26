import subprocess
import sys

import adhoc


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "adhoc", *args],
        capture_output=True,
        text=True,
    )


def test_version_flag():
    r = run_cli("--version")
    assert r.returncode == 0
    assert r.stdout.strip() == f"adhoc {adhoc.__version__}"


def test_no_args_fails_until_repl_is_ported():
    r = run_cli()
    assert r.returncode != 0
    assert "not ported yet" in r.stderr
