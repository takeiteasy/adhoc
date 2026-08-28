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


def test_unterminated_string_continues_then_completes_silently(tmp_path):
    # An open quote behaves like an open paren: `. ` continuation, and the completed
    # bare-string statement echoes nothing (strings are comment-like literals).
    out = run_repl('"abc\ndef"\n1\n', tmp_path).stdout
    assert ". " in out
    assert "ERROR" not in out
    assert "< = 1" in out
    assert '"abc' not in out.replace('> "', "").replace('. "', "")


def test_unterminated_string_blank_line_cancels(tmp_path):
    out = run_repl('"abc\n\n1\n', tmp_path).stdout
    assert "-- input cancelled" in out
    assert "< = 1" in out


def test_bare_string_statement_echoes_nothing(tmp_path):
    out = run_repl('"just a note"\n2\n', tmp_path).stdout
    assert "< = 2" in out
    assert "< = \"just a note\"" not in out


def test_alias_declared_in_repl_persists_across_inputs(tmp_path):
    # The session alias map rides alongside env/consts/modules: a `\alias` on one
    # line normalizes spellings on every later line.
    out = run_repl("\\alias \\sum, σ\nσ(i=1..3) i\n", tmp_path).stdout
    assert "ERROR" not in out
    assert "< = 6" in out


def test_dual_persists_and_reads_through_both_spellings(tmp_path):
    out = run_repl("\\dual \\alpha, α = 3.14\nα\n\\alpha\n", tmp_path).stdout
    assert "ERROR" not in out
    assert "< = 3.14" in out
    assert out.count("= 3.14") == 3  # definition echo + both reads


def test_alias_survives_incomplete_then_completed_input(tmp_path):
    # A declaration straddling the continuation prompt still lands once complete,
    # and the failed partial never committed a half-declaration.
    out = run_repl("\\alias \\sum,\nσ\nσ(i=1..2) i\n", tmp_path).stdout
    assert ". " in out  # the partial line offered a continuation
    assert "< = 3" in out
