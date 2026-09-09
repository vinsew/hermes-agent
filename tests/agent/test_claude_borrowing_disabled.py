"""The explicit isolation switch must prevent borrowed-source reads and refreshes."""
from agent import anthropic_credentials as ac


def test_disabled_claude_borrowing_never_reads_or_refreshes(monkeypatch, tmp_path):
    monkeypatch.setenv('HERMES_DISABLE_CLAUDE_CODE_CREDENTIALS', '1')
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(ac.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(ac, '_first_env', lambda *names: '')
    monkeypatch.setattr(ac, '_resolve_anthropic_pool_token', lambda **kwargs: None)
    events = []

    def keychain():
        events.append('keychain_read')
        return {'accessToken': 'fixture-expired', 'refreshToken': 'fixture-refresh', 'expiresAt': 1}

    def file_read():
        events.append('credential_file_read')
        return None

    def refresh(_creds):
        events.append('borrowed_refresh')
        return 'fixture-rotated'

    monkeypatch.setattr(ac, '_read_claude_code_credentials_from_keychain', keychain)
    monkeypatch.setattr(ac, '_read_claude_code_credentials_from_file', file_read)
    monkeypatch.setattr(ac, '_refresh_oauth_token', refresh)
    token = ac.resolve_anthropic_token()
    assert events == [], f'Isolation switch permitted borrowed credential actions: {events}'
    assert token is None


def test_disabled_direct_borrowed_refresh_resolve_and_write(monkeypatch, tmp_path):
    import pytest
    monkeypatch.setenv('HERMES_DISABLE_CLAUDE_CODE_CREDENTIALS', '1')
    monkeypatch.setattr(ac.Path, 'home', lambda: tmp_path)
    original = tmp_path / '.claude' / '.credentials.json'
    original.parent.mkdir()
    original.write_text('untouched fixture')
    def forbidden(*args, **kwargs):
        pytest.fail('Disabled borrowing reached credential IO or network')
    monkeypatch.setattr(ac, 'read_claude_code_credentials', forbidden)
    monkeypatch.setattr(ac, 'refresh_anthropic_oauth_pure', forbidden)
    creds = {'accessToken': 'fixture', 'refreshToken': 'fixture-refresh', 'expiresAt': 1}
    assert ac._resolve_claude_code_token_from_credentials(creds) is None
    assert ac._refresh_oauth_token(creds) is None
    with pytest.raises(PermissionError, match='disabled'):
        ac._write_claude_code_credentials('fixture-new', 'fixture-new-refresh', 100)
    assert original.read_text() == 'untouched fixture'


def _entry(source):
    from agent.credential_pool import PooledCredential, AUTH_TYPE_OAUTH
    return PooledCredential(provider='anthropic', id=source, label=source,
                            auth_type=AUTH_TYPE_OAUTH, priority=0, source=source,
                            access_token=f'fixture-{source}', refresh_token='fixture-refresh', expires_at_ms=1)


def test_disabled_stale_borrowed_pool_cannot_refresh(monkeypatch):
    import pytest
    from agent.credential_pool import CredentialPool
    monkeypatch.setenv('HERMES_DISABLE_CLAUDE_CODE_CREDENTIALS', '1')
    entry = _entry('claude_code')
    pool = CredentialPool('anthropic', [entry])
    def forbidden(*args, **kwargs):
        pytest.fail('Disabled borrowed pool touched its external source')
    monkeypatch.setattr(pool, '_sync_anthropic_entry_from_credentials_file', forbidden)
    monkeypatch.setattr(ac, 'refresh_anthropic_oauth_pure', forbidden)
    assert pool._refresh_entry(entry, force=True) is None
    assert pool._recover_failed_refresh(entry, RuntimeError('fixture')) is None
    with pytest.raises(PermissionError, match='disabled'):
        pool._refresh_anthropic(entry)


def test_disabled_seed_prunes_borrowed_without_losing_owned(monkeypatch):
    from agent import credential_pool as cp
    monkeypatch.setenv('HERMES_DISABLE_CLAUDE_CODE_CREDENTIALS', '1')
    monkeypatch.setattr('hermes_cli.auth.is_provider_explicitly_configured', lambda provider: False)
    borrowed, owned = _entry('claude_code'), _entry('hermes_pkce')
    seed = cp._Seeder('anthropic', [borrowed, owned])
    cp._seed_anthropic_singletons(seed)
    assert [entry.source for entry in seed.entries] == ['hermes_pkce']


def test_disabled_borrowing_keeps_owned_pool_resolution(monkeypatch):
    from agent import credential_pool as cp
    from types import SimpleNamespace
    monkeypatch.setenv('HERMES_DISABLE_CLAUDE_CODE_CREDENTIALS', '1')
    monkeypatch.setattr(ac, '_first_env', lambda *names: '')
    monkeypatch.setattr(cp, 'load_pool', lambda provider: SimpleNamespace(
        _available_entries=lambda **kwargs: ([_entry('claude_code'), _entry('hermes_pkce')], [])))
    monkeypatch.setattr(ac, 'is_rotation_consumed_uncommitted', lambda *a, **kw: False)
    assert ac.resolve_anthropic_token() == 'fixture-hermes_pkce'
