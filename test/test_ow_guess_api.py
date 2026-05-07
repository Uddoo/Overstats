from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


REPO_ROOT = Path(__file__).resolve().parents[1]
PARENT_DIR = REPO_ROOT.parent
for candidate in (PARENT_DIR, REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    import overstats.src.server as server_module
    from overstats.src.modules.errors import ModuleError
except ModuleNotFoundError:
    import src.server as server_module
    from src.modules.errors import ModuleError


class OWGuessRouteTests(unittest.TestCase):
    def test_route_returns_text_image_and_audio_replies(self) -> None:
        original_load_query_tool = server_module.load_query_tool
        original_ensure_query_tool_assets = server_module.ensure_query_tool_assets
        original_request_metrics_recorder = server_module.RequestMetricsRecorder
        original_sync_service = server_module.OWHeroLeaderboardSyncService
        original_ow_guess_module = server_module.ow_guess_module
        original_client_recorder = server_module.dashen_api_client.request_metrics_recorder

        server_module.load_query_tool = lambda: {}
        server_module.ensure_query_tool_assets = lambda _config: {
            "checked": 0,
            "cached": 0,
            "downloaded": 0,
            "failed": 0,
            "asset_dir": ".",
        }
        server_module.RequestMetricsRecorder = _StubRequestMetricsRecorder
        server_module.OWHeroLeaderboardSyncService = _StubSyncService
        server_module.ow_guess_module = _StubOWGuessModule()

        server = None
        thread = None
        try:
            config = server_module.APIConfig(
                host="127.0.0.1",
                port=0,
                use_stream_response=False,
                dashen_max_concurrent_requests=1,
                dashen_max_accepted_requests=4,
            )
            server = server_module.create_server(config)
            thread = threading.Thread(target=server.serve_forever, name="test-ow-guess-server", daemon=True)
            thread.start()
            time.sleep(0.1)

            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            opener = build_opener(ProxyHandler({}))

            text_payload = _post_json(opener, base_url, {"question_type": "hero_description"})
            self.assertTrue(text_payload["ok"])
            self.assertEqual(text_payload["question_type"], "hero_description")
            self.assertEqual(text_payload["recommended_wait_seconds"], 60)
            self.assertEqual(text_payload["replies"][0]["type"], "text")

            image_payload = _post_json(opener, base_url, {"questionType": "hero_icon"})
            self.assertTrue(image_payload["ok"])
            self.assertEqual(image_payload["question_type"], "hero_icon")
            self.assertEqual(image_payload["replies"][1]["type"], "image")
            self.assertEqual(image_payload["replies"][1]["media_type"], "image/png")

            audio_payload = _post_json(opener, base_url, {"question_type": "ult_voice"})
            self.assertTrue(audio_payload["ok"])
            self.assertEqual(audio_payload["question_type"], "ult_voice")
            self.assertEqual(audio_payload["replies"][1]["type"], "audio")
            self.assertIn(audio_payload["replies"][1]["media_type"], {"audio/ogg", "audio/mpeg"})
        finally:
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    pass
                try:
                    server.server_close()
                except Exception:
                    pass
            if thread is not None:
                thread.join(timeout=2)
            server_module.load_query_tool = original_load_query_tool
            server_module.ensure_query_tool_assets = original_ensure_query_tool_assets
            server_module.RequestMetricsRecorder = original_request_metrics_recorder
            server_module.OWHeroLeaderboardSyncService = original_sync_service
            server_module.ow_guess_module = original_ow_guess_module
            server_module.dashen_api_client.request_metrics_recorder = original_client_recorder

    def test_route_returns_clear_error_for_unavailable_type(self) -> None:
        original_load_query_tool = server_module.load_query_tool
        original_ensure_query_tool_assets = server_module.ensure_query_tool_assets
        original_request_metrics_recorder = server_module.RequestMetricsRecorder
        original_sync_service = server_module.OWHeroLeaderboardSyncService
        original_ow_guess_module = server_module.ow_guess_module
        original_client_recorder = server_module.dashen_api_client.request_metrics_recorder

        server_module.load_query_tool = lambda: {}
        server_module.ensure_query_tool_assets = lambda _config: {
            "checked": 0,
            "cached": 0,
            "downloaded": 0,
            "failed": 0,
            "asset_dir": ".",
        }
        server_module.RequestMetricsRecorder = _StubRequestMetricsRecorder
        server_module.OWHeroLeaderboardSyncService = _StubSyncService
        server_module.ow_guess_module = _FailingOWGuessModule()

        server = None
        thread = None
        try:
            config = server_module.APIConfig(
                host="127.0.0.1",
                port=0,
                use_stream_response=False,
                dashen_max_concurrent_requests=1,
                dashen_max_accepted_requests=4,
            )
            server = server_module.create_server(config)
            thread = threading.Thread(target=server.serve_forever, name="test-ow-guess-server-fail", daemon=True)
            thread.start()
            time.sleep(0.1)

            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            opener = build_opener(ProxyHandler({}))
            body = json.dumps({"question_type": "hero_conversation"}).encode("utf-8")
            request = Request(
                base_url + "/api/v2/ow-guess/replies",
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as ctx:
                opener.open(request, timeout=10)

            error_payload = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(error_payload["error"], "ow_guess_type_unavailable")
        finally:
            if server is not None:
                try:
                    server.shutdown()
                except Exception:
                    pass
                try:
                    server.server_close()
                except Exception:
                    pass
            if thread is not None:
                thread.join(timeout=2)
            server_module.load_query_tool = original_load_query_tool
            server_module.ensure_query_tool_assets = original_ensure_query_tool_assets
            server_module.RequestMetricsRecorder = original_request_metrics_recorder
            server_module.OWHeroLeaderboardSyncService = original_sync_service
            server_module.ow_guess_module = original_ow_guess_module
            server_module.dashen_api_client.request_metrics_recorder = original_client_recorder


def _post_json(opener, base_url: str, payload: dict) -> dict:  # noqa: ANN001
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        base_url + "/api/v2/ow-guess/replies",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with opener.open(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


class _StubRequestMetricsRecorder:
    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def enqueue(self, url, source_type, success):  # noqa: ANN001
        return None


class _StubSyncService:
    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _StubOWGuessOutput:
    def __init__(self, *, question_type: str, media_kind: str) -> None:
        self.question_type = question_type
        self.media_kind = media_kind

    def to_dict(self) -> dict:
        replies = [
            {"type": "text", "data": "请根据题面作答"},
        ]
        if self.media_kind == "image":
            replies.append(
                {
                    "type": "image",
                    "media_type": "image/png",
                    "base64": base64.b64encode(b"png-data").decode("ascii"),
                }
            )
        if self.media_kind == "audio":
            replies.append(
                {
                    "type": "audio",
                    "media_type": "audio/ogg",
                    "base64": base64.b64encode(b"ogg-data").decode("ascii"),
                }
            )
        return {
            "ok": True,
            "generated_at": "2026-05-07 12:00:00",
            "question_type": self.question_type,
            "question_type_id": 11 if self.question_type == "hero_description" else 2 if self.question_type == "hero_icon" else 6,
            "question_type_label": "描述猜英雄" if self.question_type == "hero_description" else "英雄图标" if self.question_type == "hero_icon" else "终极语音",
            "question_id": f"stub.{self.question_type}",
            "difficulty": 3,
            "recommended_wait_seconds": 60 if self.question_type == "hero_description" else 30,
            "question": {
                "prompt_text": "请根据题面作答",
                "media_kind": self.media_kind,
                "hint_steps": [{"order": 1, "text": "第一条线索", "recommended_delay_seconds": 10}] if self.question_type == "hero_description" else [],
            },
            "answer": {
                "canonical": "安娜",
                "aliases": ["安娜", "Ana"],
            },
            "replies": replies,
        }


class _StubOWGuessModule:
    async def query_guess_replies(self, query):  # noqa: ANN001
        question_type = str(getattr(query, "question_type", "") or "")
        if question_type == "hero_description":
            return _StubOWGuessOutput(question_type="hero_description", media_kind="text")
        if question_type == "hero_icon":
            return _StubOWGuessOutput(question_type="hero_icon", media_kind="image")
        return _StubOWGuessOutput(question_type="ult_voice", media_kind="audio")


class _FailingOWGuessModule:
    async def query_guess_replies(self, query):  # noqa: ANN001
        raise ModuleError(
            error="ow_guess_type_unavailable",
            message=f"Question type is not available yet: {getattr(query, 'question_type', '')}",
            status_code=400,
            details={"question_type": getattr(query, "question_type", "")},
        )


if __name__ == "__main__":
    unittest.main()
