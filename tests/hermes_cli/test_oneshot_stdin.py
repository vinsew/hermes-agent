"""`hermes -z -` reads the prompt from stdin.

A prompt passed as one argv string is capped by the kernel at 128 KiB (MAX_ARG_STRLEN): a script
handing the model a long report pack fails with E2BIG before Hermes even starts. ``-`` is the usual
"read stdin" convention; a literal ``-z -`` prompt was never useful.
"""
from __future__ import annotations

import io
import sys
from types import SimpleNamespace

import pytest

import hermes_cli.main as main_mod


@pytest.fixture
def captured(monkeypatch):
    seen = {}
    monkeypatch.setattr(main_mod, "_confirm_startup_expensive_model_override", lambda args: None)
    monkeypatch.setattr(main_mod, "_resolve_chat_session_args", lambda args, use_tui=False: None)
    monkeypatch.setattr(main_mod, "_run_and_exit_oneshot", lambda prompt, **kw: seen.update(prompt=prompt, **kw))
    return seen


def _args(prompt, resume=None):
    return SimpleNamespace(oneshot=prompt, model=None, provider=None, toolsets=None, skills=None, usage_file=None,
                           resume=resume, reasoning="none")


def _stdin(data: bytes):
    return io.TextIOWrapper(io.BytesIO(data), encoding="ascii")  # a locale-less cron/systemd stdin


def test_dash_reads_the_prompt_from_stdin(captured, monkeypatch):
    big = "长" * 200_000  # ~600 KB: far past what one argv string can carry
    monkeypatch.setattr(sys, "stdin", _stdin(big.encode()))
    main_mod._run_oneshot_from_args(_args("-"))
    assert captured["prompt"] == big and captured["reasoning"] == "none"


def test_an_empty_stdin_prompt_is_refused(captured, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _stdin(b"  \n"))
    with pytest.raises(SystemExit) as exc:
        main_mod._run_oneshot_from_args(_args("-"))
    assert exc.value.code == 2 and "stdin" in capsys.readouterr().err and "prompt" not in captured


def test_an_ordinary_prompt_is_passed_through(captured):
    main_mod._run_oneshot_from_args(_args("hello"))
    assert captured["prompt"] == "hello"


def test_stdin_is_read_as_utf8_whatever_the_locale_and_kept_verbatim(captured, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _stdin("你好，小龙\n".encode() + b"\xff"))
    main_mod._run_oneshot_from_args(_args("-"))
    assert captured["prompt"] == "你好，小龙\n\ufffd"  # bad bytes replaced, trailing newline kept


def test_stdin_prompt_and_resume_go_together(captured, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _stdin("继续".encode()))
    main_mod._run_oneshot_from_args(_args("-", resume="abc"))
    assert captured["prompt"] == "继续" and captured["resume"] == "abc"
