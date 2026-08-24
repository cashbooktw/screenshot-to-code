from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from routes.generate_code import (
    PipelineContext,
    WebSocketCommunicator,
    WebSocketSetupMiddleware,
)


@pytest.mark.asyncio
async def test_websocket_setup_rejects_non_local_browser_origin() -> None:
    websocket = MagicMock()
    websocket.headers = {"origin": "https://attacker.example"}
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    next_func = AsyncMock()

    await WebSocketSetupMiddleware().process(
        PipelineContext(websocket=cast(Any, websocket)), next_func
    )

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008)
    next_func.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_setup_allows_local_browser_origin() -> None:
    websocket = MagicMock()
    websocket.headers = {"origin": "http://127.0.0.1:5173"}
    websocket.accept = AsyncMock()
    websocket.close = AsyncMock()
    next_func = AsyncMock()

    await WebSocketSetupMiddleware().process(
        PipelineContext(websocket=cast(Any, websocket)), next_func
    )

    websocket.accept.assert_awaited_once()
    next_func.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_message_ignores_already_completed_websocket() -> None:
    websocket = MagicMock()
    websocket.send_json = AsyncMock(
        side_effect=RuntimeError(
            "Unexpected ASGI message 'websocket.send', after sending "
            "'websocket.close' or response already completed."
        )
    )
    communicator = WebSocketCommunicator(cast(Any, websocket))

    await communicator.send_message("status", "Generating", 0)

    assert communicator.is_closed is True
    websocket.send_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_receive_params_marks_websocket_closed_on_disconnect() -> None:
    websocket = MagicMock()
    websocket.receive_json = AsyncMock(side_effect=WebSocketDisconnect(1006))
    communicator = WebSocketCommunicator(cast(Any, websocket))

    with pytest.raises(WebSocketDisconnect):
        await communicator.receive_params()

    assert communicator.is_closed is True


@pytest.mark.asyncio
async def test_wait_for_disconnect_consumes_until_close_message() -> None:
    websocket = MagicMock()
    websocket.receive = AsyncMock(
        side_effect=[
            {"type": "websocket.receive", "text": "ignored"},
            {"type": "websocket.disconnect", "code": 4001},
        ]
    )
    communicator = WebSocketCommunicator(cast(Any, websocket))

    await communicator.wait_for_disconnect()

    assert communicator.is_closed is True
    assert websocket.receive.await_count == 2


@pytest.mark.asyncio
async def test_close_ignores_already_completed_websocket() -> None:
    websocket = MagicMock()
    websocket.close = AsyncMock(
        side_effect=RuntimeError(
            "Unexpected ASGI message 'websocket.close', after sending "
            "'websocket.close' or response already completed."
        )
    )
    communicator = WebSocketCommunicator(cast(Any, websocket))

    await communicator.close()

    assert communicator.is_closed is True
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_throw_error_ignores_already_completed_websocket() -> None:
    websocket = MagicMock()
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock(
        side_effect=RuntimeError(
            "Unexpected ASGI message 'websocket.close', after sending "
            "'websocket.close' or response already completed."
        )
    )
    communicator = WebSocketCommunicator(cast(Any, websocket))

    await communicator.throw_error("Generation failed")

    assert communicator.is_closed is True
    websocket.send_json.assert_awaited_once()
    websocket.close.assert_awaited_once()
