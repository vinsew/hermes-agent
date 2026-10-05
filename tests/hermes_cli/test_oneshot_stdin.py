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
    # v0.22.3+ hands -z to the gateway launcher; capture what reaches it instead of talking to a gateway.
    import hermes_cli.gateway_chat_startup as startup
    seen = {}

    def launch(args):
        seen.update(prompt=args.oneshot, reasoning=args.reasoning, resume=args.resume)
        return 0

    monkeypatch.setattr(startup, "launch_gateway_chat", launch)
    return seen


def _run(args):
    with pytest.raises(SystemExit) as exc:  # the transport launcher never returns
        main_mod._run_oneshot_from_args(args)
    return exc.value.code


def _args(prompt, resume=None):
    return SimpleNamespace(oneshot=prompt, model=None, provider=None, toolsets=None, skills=None, usage_file=None,
                           resume=resume, reasoning="none")


def _stdin(data: bytes):
    return io.TextIOWrapper(io.BytesIO(data), encoding="ascii")  # a locale-less cron/systemd stdin


def test_dash_reads_the_prompt_from_stdin(captured, monkeypatch):
    big = "长" * 200_000  # ~600 KB: far past what one argv string can carry
    monkeypatch.setattr(sys, "stdin", _stdin(big.encode()))
    assert _run(_args("-")) == 0
    assert captured["prompt"] == big and captured["reasoning"] == "none"


def test_an_empty_stdin_prompt_is_refused(captured, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _stdin(b"  \n"))
    assert _run(_args("-")) == 2 and "stdin" in capsys.readouterr().err and "prompt" not in captured


def test_an_ordinary_prompt_is_passed_through(captured):
    assert _run(_args("hello")) == 0
    assert captured["prompt"] == "hello"


def test_stdin_is_read_as_utf8_whatever_the_locale_and_kept_verbatim(captured, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _stdin("你好，小龙\n".encode() + b"\xff"))
    assert _run(_args("-")) == 0
    assert captured["prompt"] == "你好，小龙\n\ufffd"  # bad bytes replaced, trailing newline kept


def test_stdin_prompt_and_resume_go_together(captured, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _stdin("继续".encode()))
    assert _run(_args("-", resume="abc")) == 0
    assert captured["prompt"] == "继续" and captured["resume"] == "abc"
