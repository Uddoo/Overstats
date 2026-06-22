from __future__ import annotations

import asyncio
from dataclasses import dataclass
import unittest

from src.modules.dashen_auth.service import (
    DashenAuthService,
    mask_secret,
)


@dataclass(frozen=True)
class Account:
    name: str
    role_id: int
    token: str


@dataclass(frozen=True)
class Config:
    accounts: tuple[Account, ...]


class DashenAuthServiceTest(unittest.TestCase):
    def test_missing_accounts(self) -> None:
        service = DashenAuthService(config_loader=lambda: Config(accounts=()))

        self.assertEqual(service.status()["state"], "credentials_missing")

    def test_placeholder_account(self) -> None:
        service = DashenAuthService(
            config_loader=lambda: Config(
                accounts=(Account(name="primary", role_id=123456789, token="replace-with-your-token"),)
            )
        )

        status = service.status()

        self.assertEqual(status["state"], "credentials_placeholder")
        self.assertFalse(status["accounts"][0]["configured"])
        self.assertNotIn("replace-with-your-token", str(status))

    def test_configured_account_masks_token(self) -> None:
        service = DashenAuthService(
            config_loader=lambda: Config(accounts=(Account(name="primary", role_id=42, token="abcdef1234567890"),))
        )

        status = service.status()

        self.assertEqual(status["state"], "credentials_unverified")
        self.assertEqual(status["accounts"][0]["token_preview"], "abcd...7890")
        self.assertNotIn("abcdef1234567890", str(status))

    def test_mask_secret_short_values(self) -> None:
        self.assertEqual(mask_secret("abc"), "***")
        self.assertEqual(mask_secret(""), "")

    def test_config_loader_error_does_not_leak_exception_message(self) -> None:
        secret = "abcdef1234567890"

        def config_loader() -> Config:
            raise RuntimeError(f"failed to load Dashen token {secret}")

        service = DashenAuthService(config_loader=config_loader)

        result = service.status()

        self.assertEqual(result["state"], "credentials_missing")
        self.assertEqual(result["error"], "dashen_auth_config_error")
        self.assertEqual(result["details"]["exception"], "RuntimeError")
        self.assertNotIn(secret, str(result))

    def test_probe_ready_for_non_auth_payload(self) -> None:
        async def probe_runner() -> dict[str, object]:
            return {"code": 0, "data": {}}

        service = DashenAuthService(
            config_loader=lambda: Config(accounts=(Account(name="primary", role_id=42, token="abcdef1234567890"),)),
            probe_runner=probe_runner,
        )

        result = asyncio.run(service.probe())

        self.assertEqual(result["state"], "credentials_ready")

    def test_probe_invalid_for_auth_failure_payload(self) -> None:
        async def probe_runner() -> dict[str, object]:
            return {"code": 403, "msg": "token expired"}

        service = DashenAuthService(
            config_loader=lambda: Config(accounts=(Account(name="primary", role_id=42, token="abcdef1234567890"),)),
            probe_runner=probe_runner,
        )

        result = asyncio.run(service.probe())

        self.assertEqual(result["state"], "credentials_invalid")
        self.assertEqual(result["error"], "dashen_auth_invalid")

    def test_probe_exception_does_not_leak_exception_message(self) -> None:
        secret = "abcdef1234567890"

        async def probe_runner() -> dict[str, object]:
            raise RuntimeError(f"upstream rejected credential {secret}")

        service = DashenAuthService(
            config_loader=lambda: Config(accounts=(Account(name="primary", role_id=42, token="zyxwvu9876543210"),)),
            probe_runner=probe_runner,
        )

        result = asyncio.run(service.probe())

        self.assertEqual(result["state"], "upstream_limited_or_unavailable")
        self.assertEqual(result["error"], "dashen_upstream_unavailable")
        self.assertEqual(result["details"]["exception"], "RuntimeError")
        self.assertNotIn(secret, str(result))


if __name__ == "__main__":
    unittest.main()
