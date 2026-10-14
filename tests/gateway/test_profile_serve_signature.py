"""#111105: the profile re-scan watcher must rebuild adapters after a config.yaml replacement
that keeps mtime and size (``cp -p``, ``rsync -t``, a timestamp-pinning writer)."""
import os
import shutil

import pytest

from gateway.run_profile_reconcile import profile_serve_signature
from tests.waiting import wait_for_ctime_tick


def test_profile_serve_signature_changes_on_replacement_with_pinned_mtime(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("x" * 64, encoding="utf-8")
    before = profile_serve_signature(tmp_path)
    assert profile_serve_signature(tmp_path) == before  # unchanged file: stable
    st = cfg.stat()
    wait_for_ctime_tick(tmp_path, st.st_ctime_ns)
    other = tmp_path / "other"
    other.write_text("y" * 64, encoding="utf-8")
    shutil.copy2(other, cfg)
    os.utime(cfg, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert (cfg.stat().st_mtime_ns, cfg.stat().st_size) == (st.st_mtime_ns, st.st_size)
    assert profile_serve_signature(tmp_path) != before


@pytest.mark.parametrize("name", ["config.yaml", ".env"])
def test_profile_signature_detects_content_when_all_stat_fields_match(tmp_path, monkeypatch, name):
    monkeypatch.setattr("gateway.run_profile_reconcile.file_signature", lambda _st: (1, 64, 1, 1))
    path = tmp_path / name
    path.write_text("a" * 64, encoding="utf-8")
    before = profile_serve_signature(tmp_path)
    assert profile_serve_signature(tmp_path) == before
    path.write_text("b" * 64, encoding="utf-8")
    assert profile_serve_signature(tmp_path) != before
