"""Expired receive credentials must never leave a connected platform status."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms import weixin


@pytest.mark.parametrize('field', ['ret', 'errcode'])
def test_expired_receive_credentials_publish_fatal(tmp_path, monkeypatch, field):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    adapter = weixin.WeixinAdapter(PlatformConfig(enabled=True, token='test-token', extra={'account_id': 'test-account'}))
    adapter._poll_session = object()
    adapter._mark_connected()
    handler = AsyncMock()
    adapter.set_fatal_error_handler(handler)
    monkeypatch.setattr(weixin, '_get_updates', AsyncMock(return_value={field: -14}))
    asyncio.run(asyncio.wait_for(adapter._poll_loop(), timeout=2))
    status = json.loads((tmp_path / 'gateway_state.json').read_text())['platforms']['weixin']
    assert status['state'] == 'fatal'
    assert status['error_code'] == 'weixin_session_expired'
    assert not adapter.fatal_error_retryable
    assert not adapter._running
    handler.assert_awaited_once_with(adapter)


def test_ambiguous_stale_session_recovers_without_fatal(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    adapter = weixin.WeixinAdapter(PlatformConfig(enabled=True, token='test-token', extra={'account_id': 'test-account'}))
    adapter._poll_session = object()
    adapter._mark_connected()
    observed = []
    responses = iter([{'ret': -2, 'errmsg': 'unknown error'}, {}])

    async def get_updates(*args, **kwargs):
        observed.append(json.loads((tmp_path / 'gateway_state.json').read_text())['platforms']['weixin']['state'])
        try:
            return next(responses)
        except StopIteration:
            raise asyncio.CancelledError

    monkeypatch.setattr(weixin, '_get_updates', get_updates)
    monkeypatch.setattr(weixin.asyncio, 'sleep', AsyncMock())
    asyncio.run(adapter._poll_loop())
    assert observed == ['connected', 'retrying', 'connected']
    assert not adapter.has_fatal_error
