"""Binary-level REPL tests, driven through piped stdin/stdout. Piped (non-TTY) stdin goes
through plain reads, which is what makes the prompt sequence observable — see repl.py."""

import os
import subprocess
import sys


def run_repl(input_text: str, tmp_path) -> subprocess.CompletedProcess:
    env = {**os.environ, "ADHOC_HISTORY": str(tmp_path / "history")}
    return subprocess.run(
        [sys.executable, "-m", "adhoc"],
        input=input_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_continuation_prompt_sequence(tmp_path):
    # `(1 + 2` is incomplete -> `. ` continuation prompt; a blank line then cancels it,
    # returning to `> `. Ordering assertions, searching forward from the last match, so
    # they're about sequence rather than exact byte layout around the prompts.
    out = run_repl("(1 + 2\n\n", tmp_path).stdout
    first = out.find("> ")
    second = out[first + 2 :].find(". ") + first + 2
    third = out[second + 2 :].find("> ") + second + 2
    assert first < second < third
    assert "-- input cancelled" in out


def test_semicolon_terminated_statements_do_not_continue(tmp_path):
    out = run_repl("1;\n2;\n", tmp_path).stdout
    assert "< = 1" in out
    assert "< = 2" in out
    # Neither `1;` nor `2;` should ever show a continuation prompt.
    assert ". " not in out


def test_eof_mid_statement_reports_diagnostic(tmp_path):
    out = run_repl("(1 + 2", tmp_path).stdout
    assert "ERROR" in out


def test_division_by_zero_recovers_instead_of_crashing(tmp_path):
    # The old HEAD regression this closes: an untyped exception escaping the evaluator's
    # catch killed the loop. Here it renders a caret and keeps going.
    out = run_repl("1/0\n1 + 1\n", tmp_path).stdout
    assert "division by zero" in out
    assert "^~~" in out
    assert "< = 2" in out


def test_blank_line_when_fresh_is_silent(tmp_path):
    out = run_repl("\n\n2\n", tmp_path).stdout
    assert "-- input cancelled" not in out
    assert "< = 2" in out


def test_comment_only_line_is_skipped(tmp_path):
    out = run_repl("-- just a comment\n3\n", tmp_path).stdout
    assert "< = 3" in out
