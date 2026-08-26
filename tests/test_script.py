"""Binary-level script-mode tests, run via `adhoc run` (ports of tests/script.rs, plus
--emit-py coverage)."""

import os
import subprocess
import sys


def run_cli(args, stdin="", env_extra=None):
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "adhoc", *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def test_script_runs_statement_by_statement_with_repl_style_output(tmp_path):
    path = tmp_path / "ok.ad"
    path.write_text("x = 1 + 2;\n7\n")
    r = run_cli(["run", str(path)])
    assert r.returncode == 0
    assert r.stdout == "< x = 3\n< = 7\n"


def test_script_error_renders_with_line_gutter_and_exits_nonzero(tmp_path):
    path = tmp_path / "err.ad"
    path.write_text("x = 1;\ny := 2\n")
    r = run_cli(["run", str(path)])
    assert r.returncode != 0
    # Multi-line source -> the `N: ` gutter is present, and the error stops the run after
    # the first (successful) statement rather than continuing past it.
    assert "< x = 1" in r.stdout
    assert "2: y := 2" in r.stdout
    assert "< y =" not in r.stdout


def test_script_parse_error_is_hard_no_continuation(tmp_path):
    path = tmp_path / "incomplete.ad"
    path.write_text("(1 + 2")
    r = run_cli(["run", str(path)])
    assert r.returncode != 0
    assert "ERROR" in r.stdout
    assert ". " not in r.stdout  # no continuation prompt exists for files


def test_run_without_path_prints_usage(tmp_path):
    r = run_cli(["run"])
    assert r.returncode != 0
    assert "usage: adhoc run <script.ad>" in r.stderr


def test_emit_py_flag_dumps_generated_source_to_stderr(tmp_path):
    path = tmp_path / "emit.ad"
    path.write_text("1 + 2\n")
    r = run_cli(["--emit-py", "run", str(path)])
    assert r.returncode == 0
    assert "_e.out(_e.add(1, 2," in r.stderr
    assert r.stdout == "< = 3\n"
