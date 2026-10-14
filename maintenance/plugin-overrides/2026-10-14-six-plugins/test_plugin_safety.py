"""Behavioral admission checks for the six explicitly requested plugins."""
import argparse
import importlib.util
import multiprocessing
import os
import stat
import sys
import time
from pathlib import Path

import pytest

INPUTS = Path(__file__).resolve().parents[2] / 'plugin-audit-inputs'


def load_plugin(name):
    root = INPUTS / name
    module_name = 'audit_' + name.replace('-', '_') + '_' + str(time.time_ns())
    spec = importlib.util.spec_from_file_location(module_name, root / '__init__.py',
                                                 submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class Config:
    def __init__(self, **values):
        self.values = values

    def get_config(self, key, default=None):
        return self.values.get(key, default)


def history_fixture(tmp_path):
    m = load_plugin('memory-rewind')
    home, data = tmp_path / 'home', tmp_path / 'state'
    (home / 'memories').mkdir(parents=True)
    (home / 'memories/MEMORY.md').write_text('PRIVATE_OLD_SENTINEL')
    rev = m.take_snapshot(home, data, m.TrackingOptions(track_skills=False), ['baseline'])
    (home / 'memories/MEMORY.md').write_text('PRIVATE_NEW_SENTINEL')
    return m, home, data, rev


def test_memory_chat_never_returns_knowledge_body(tmp_path):
    m, home, data, rev = history_fixture(tmp_path)
    from importlib import import_module
    chat = import_module(m.__name__ + '.chat')
    result = chat.render_history(rev + ' memory', home, data, m.TrackingOptions())
    assert 'PRIVATE_OLD_SENTINEL' not in result
    assert 'MEMORY.md' in result


@pytest.mark.parametrize('command', ['restore', 'forget'])
def test_memory_mutation_requires_explicit_operator_gate(tmp_path, monkeypatch, command):
    m, home, data, rev = history_fixture(tmp_path)
    monkeypatch.setattr(m, 'resolve_home', lambda: home)
    monkeypatch.setattr(m, 'resolve_data_dir', lambda: data)
    from importlib import import_module
    cli = import_module(m.__name__ + '.cli')
    args = argparse.Namespace(mrw_command=command, rev=rev, target='memory', yes=True, dry_run=False)
    assert cli.run_cli(args, Config()) != 0
    assert (home / 'memories/MEMORY.md').read_text() == 'PRIVATE_NEW_SENTINEL'
    assert (data / 'history.git/HEAD').is_file()


def test_memory_history_budget_pauses_recording_without_touching_source(tmp_path, monkeypatch):
    m = load_plugin('memory-rewind')
    home, data = tmp_path / 'home', tmp_path / 'state'
    (home / 'memories').mkdir(parents=True)
    content = os.urandom(2 * 1024 * 1024)
    (home / 'memories/MEMORY.md').write_bytes(content)
    monkeypatch.setattr(m, 'resolve_home', lambda: home)
    monkeypatch.setattr(m, 'resolve_data_dir', lambda: data)
    m._record_baseline(Config(max_file_kb=4096, max_history_mb=1), 'test baseline')
    assert not (data / 'history.git/HEAD').exists()
    assert (home / 'memories/MEMORY.md').read_bytes() == content


def test_private_history_directory(tmp_path):
    _m, _home, data, _rev = history_fixture(tmp_path)
    assert stat.S_IMODE(data.stat().st_mode) & 0o077 == 0


def test_context_profile_routing_and_utf8_metadata(tmp_path, monkeypatch):
    a, b = tmp_path / 'A', tmp_path / 'B'
    monkeypatch.setenv('HERMES_HOME', str(a))
    m = load_plugin('context-audit')
    active = [a]
    monkeypatch.setattr(m, '_hermes_home', lambda: active[0])
    m.on_pre_tool_call(tool_name='read_file', args={'q': 'SECRET_ARGS'}, session_id='same', tool_call_id='same')
    m.on_post_tool_call(tool_name='read_file', result='中文', session_id='same', tool_call_id='same')
    da = m.get_db()
    active[0] = b
    db = m.get_db()
    assert db.path != da.path
    assert db.summary(0)['tool_calls'] == 0
    active[0] = a
    assert m.get_db().summary(0)['tool_calls'] == 1
    assert da._conn.execute('select result_bytes from tool_calls').fetchone()[0] == len('中文'.encode())
    assert b'SECRET_ARGS' not in Path(da.path).read_bytes()


def test_context_retention_and_private_state(tmp_path, monkeypatch):
    m = load_plugin('context-audit')
    monkeypatch.setattr(m, 'MAX_ROWS_PER_TABLE', 20, raising=False)
    monkeypatch.setattr(m, 'PRUNE_EVERY_WRITES', 1, raising=False)
    path = tmp_path / 'state/audit.db'
    db = m.AuditDB(str(path))
    for i in range(40):
        db.add_tool_call('read_file', 10, ts=time.time(), tool_call_id=str(i))
    assert db.summary(0)['tool_calls'] <= 20
    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0


def _load_ledger(file):
    spec = importlib.util.spec_from_file_location('ledger_child_' + str(time.time_ns()), file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trim_writer(file, path, ready, release):
    m = _load_ledger(file)
    m.MAX_BYTES = 1000
    original = m.os.replace
    def paused_replace(src, dst):
        ready.set()
        if not release.wait(5):
            raise TimeoutError('test coordination failed')
        original(src, dst)
    m.os.replace = paused_replace
    m.append(Path(path), {'writer': 'trim'})


def _later_writer(file, path, started):
    m = _load_ledger(file)
    m.MAX_BYTES = 1000
    started.set()
    m.append(Path(path), {'writer': 'LATEST_SENTINEL'})


@pytest.mark.parametrize('name', ['aux-ledger', 'error-ledger', 'approval-ledger'])
def test_ledger_trim_does_not_erase_concurrent_writer(tmp_path, name):
    ctx = multiprocessing.get_context('fork')
    file = str(INPUTS / name / 'ledger.py')
    path = tmp_path / 'rows.jsonl'
    path.write_text('{"padding":"' + ('x' * 1200) + '"}\n')
    ready, release, started = ctx.Event(), ctx.Event(), ctx.Event()
    a = ctx.Process(target=_trim_writer, args=(file, str(path), ready, release))
    b = ctx.Process(target=_later_writer, args=(file, str(path), started))
    try:
        a.start()
        assert ready.wait(5)
        b.start()
        assert started.wait(5)
        time.sleep(0.1)
        release.set()
        a.join(5); b.join(5)
        assert a.exitcode == b.exitcode == 0
        assert 'LATEST_SENTINEL' in path.read_text()
    finally:
        release.set()
        for p in (a, b):
            if p.pid and p.is_alive():
                p.terminate(); p.join(5)


@pytest.mark.parametrize('name', ['aux-ledger', 'error-ledger', 'approval-ledger'])
def test_ledger_bounds_bytes_and_private_file(tmp_path, name):
    m = _load_ledger(str(INPUTS / name / 'ledger.py'))
    m.MAX_BYTES = 5000
    path = tmp_path / 'state/rows.jsonl'
    path.parent.mkdir()
    for i in range(20):
        m.append(path, {'id': i, 'model': 'x' * 900})
    assert path.stat().st_size <= m.MAX_BYTES
    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(path.parent.stat().st_mode) & 0o077 == 0


@pytest.mark.parametrize('name,handler', [('aux-ledger','_handle_aux'),('error-ledger','_handle_errors'),('approval-ledger','_handle_approval_log')])
def test_chat_clear_default_denied_preserves_rows(tmp_path, monkeypatch, name, handler):
    m=load_plugin(name)
    path=tmp_path/name/'test.jsonl'
    m.ledger.append(path, {'model':'sentinel','ts':time.time()})
    before=path.read_bytes()
    monkeypatch.setattr(m,'_ledger_path',lambda:path)
    assert 'authorization' in getattr(m,handler)('clear')
    assert path.read_bytes()==before
    m.ledger.append(path, {'model':'next','ts':time.time()})
    assert len(m.ledger.read(path))==2
