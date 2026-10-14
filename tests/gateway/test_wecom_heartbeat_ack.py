"""Heartbeat acknowledgements must remain quiet unless rejected."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from gateway.config import PlatformConfig

class TestHeartbeatAck:
    """The server answers each heartbeat with no cmd and the ping's req_id: that is the ack, not an
    unrouted message (it was logged at INFO every 30 s, ~2,900 lines a day)."""

    @pytest.mark.asyncio
    async def test_ping_ack_is_not_logged_as_unrouted(self, caplog):
        from plugins.platforms.wecom.adapter import WeComAdapter

        adapter = WeComAdapter(PlatformConfig(enabled=True))
        adapter._on_message = AsyncMock()
        with caplog.at_level("INFO"):
            await adapter._dispatch_payload({"headers": {"req_id": "ping-8b698dd0b6ad4d6a"}, "errcode": 0})
        assert "Unrouted" not in caplog.text and not caplog.records
        adapter._on_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_ping_ack_is_a_warning(self, caplog):
        from plugins.platforms.wecom.adapter import WeComAdapter

        adapter = WeComAdapter(PlatformConfig(enabled=True))
        with caplog.at_level("INFO"):
            await adapter._dispatch_payload({"headers": {"req_id": "ping-1"}, "errcode": 846609, "errmsg": "bad"})
        assert any(r.levelname == "WARNING" and "846609" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_other_unrouted_payloads_are_still_logged(self, caplog):
        from plugins.platforms.wecom.adapter import WeComAdapter

        adapter = WeComAdapter(PlatformConfig(enabled=True))
        with caplog.at_level("INFO"):
            await adapter._dispatch_payload({"headers": {"req_id": "req-9"}, "body": {"x": 1}})
        assert "Unrouted" in caplog.text

    @pytest.mark.asyncio
    async def test_ack_errcode_as_text_or_in_the_body(self, caplog):
        from plugins.platforms.wecom.adapter import WeComAdapter

        adapter = WeComAdapter(PlatformConfig(enabled=True))
        with caplog.at_level("INFO"):
            await adapter._dispatch_payload({"headers": {"req_id": "ping-1"}, "errcode": "0"})
            await adapter._dispatch_payload({"headers": {"req_id": "ping-2"}, "body": {"errcode": 0}})
        assert not caplog.records
        with caplog.at_level("INFO"):
            await adapter._dispatch_payload({"headers": {"req_id": "ping-3"}, "body": {"errcode": 40001}})
        assert any(r.levelname == "WARNING" and "40001" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_a_pending_response_with_a_ping_id_still_reaches_its_waiter(self):
        from plugins.platforms.wecom.adapter import WeComAdapter

        adapter = WeComAdapter(PlatformConfig(enabled=True))
        waiter = asyncio.get_running_loop().create_future()
        adapter._pending_responses["ping-7"] = waiter
        payload = {"headers": {"req_id": "ping-7"}, "errcode": 0}
        await adapter._dispatch_payload(payload)
        assert waiter.done() and waiter.result() is payload

    @pytest.mark.asyncio
    async def test_a_ping_id_with_a_cmd_is_not_treated_as_the_ack(self):
        from plugins.platforms.wecom.adapter import WeComAdapter

        adapter = WeComAdapter(PlatformConfig(enabled=True))
        adapter._on_message = AsyncMock()
        await adapter._dispatch_payload({"cmd": "aibot_msg_callback", "headers": {"req_id": "ping-8"}, "body": {}})
        adapter._on_message.assert_awaited_once()
