"""Transcript parity harness: the same scripts and piped REPL sessions through the Rust
reference binary and the Python implementation must produce byte-identical stdout,
stderr, and exit codes. This is the stage-4 gate for deleting the Rust tree.

Intentionally excluded from the corpus (documented divergences, docs/numerics.md):
float-overflow exponents — MPFR has an unbounded exponent range, the Python seam
saturates to signed infinity."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUST_BIN = REPO_ROOT / "target" / "debug" / "adhoc"

requires_rust = pytest.mark.skipif(
    not RUST_BIN.is_file(), reason="rust reference binary not built"
)

SCRIPTS = {
    # Newlines are ordinary whitespace in ad — statements in a file separate with `;`,
    # like they do on a REPL line. (One corpus case below deliberately omits them to pin
    # the juxtaposition-across-newlines behavior.)
    "ok": "x = 1 + 2;\n7\n",
    "err_mid": "x = 1;\ny := 2\n",
    "exact_rationals": "1/3 + 1/3 + 1/3;\n10/4\n",
    "floats": "0.5+0.5;\n2^-1\n",
    "bignum": "10^100;\n2^64\n",
    "unicode": "-- hello\nπ = 3;\nπ;\nπ := 4\n",
    "seq_line": "a = 1; b = 2; a+b\n",
    "precedence": "-2^2;\n2^-1;\n2^3^2;\n1/2*3\n",
    "newline_is_whitespace": "2\n3\n",
}

TRANSCRIPTS = [
    # prompts, bind/check/rebind, force-reassign error, continuation + cancel
    "1 + 2\nx = 3\nx = 4\nx := 9\ny := 2\n(1 + 2\n\n1;\n-- comment only\n\nπ\n1/0\n2^-1\n",
    # blank lines fresh, semicolons, float display, bignum, unicode identifier
    "\n\n0.5+0.5\n10^100\nαβ = 4\nαβ\n",
]


def _run(binary, args, stdin_text, tmp_path):
    env = {**os.environ, "ADHOC_HISTORY": str(tmp_path / "history")}
    return subprocess.run(
        [str(binary), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


@requires_rust
@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_script_parity(name, tmp_path):
    path = tmp_path / f"{name}.ad"
    path.write_text(SCRIPTS[name])
    py = _run(sys.executable, ["-m", "adhoc", "run", str(path)], "", tmp_path)
    rs = _run(RUST_BIN, ["run", str(path)], "", tmp_path)
    assert (py.stdout, py.stderr, py.returncode) == (rs.stdout, rs.stderr, rs.returncode)


@requires_rust
def test_script_missing_file_parity(tmp_path):
    missing = str(tmp_path / "nope.ad")
    py = _run(sys.executable, ["-m", "adhoc", "run", missing], "", tmp_path)
    rs = _run(RUST_BIN, ["run", missing], "", tmp_path)
    assert (py.stdout, py.stderr, py.returncode) == (rs.stdout, rs.stderr, rs.returncode)


@requires_rust
@pytest.mark.parametrize("idx", range(len(TRANSCRIPTS)))
def test_repl_transcript_parity(idx, tmp_path):
    transcript = TRANSCRIPTS[idx]
    py = _run(sys.executable, ["-m", "adhoc"], transcript, tmp_path)
    rs = _run(RUST_BIN, [], transcript, tmp_path)
    assert (py.stdout, py.stderr, py.returncode) == (rs.stdout, rs.stderr, rs.returncode)
