from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, Optional

try:
    from overstats.config import get_dashen_client_config
except ModuleNotFoundError:
    from config import get_dashen_client_config


PLACEHOLDER_TOKENS = {"replace-with-your-token", "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "token-a", "token-b"}
PROBE_BATTLE_TAG = "__overstats_probe__#0000"


def mask_secret(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"


def _account_field(account: Any, key: str, default: Any = "") -> Any:
    if isinstance(account, Mapping):
        return account.get(key, default)
    if is_dataclass(account):
        return asdict(account).get(key, default)
    return getattr(account, key, default)


def _iter_accounts(config: Any) -> Iterable[Any]:
    return tuple(getattr(config, "accounts", ()) or ())


def _is_placeholder_token(token: Any) -> bool:
    text = str(token or "").strip()
    return (not text) or text.lower() in PLACEHOLDER_TOKENS or text.lower().startswith("replace-with-your-")


def _is_placeholder_role_id(role_id: Any) -> bool:
    try:
        normalized = int(role_id)
    except (TypeError, ValueError):
        return True
    return normalized <= 0 or normalized == 123456789


def _auth_failure_from_payload(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    code = payload.get("code", payload.get("status"))
    message = str(payload.get("msg") or payload.get("message") or payload.get("errmsg") or "").lower()
    if str(code) in {"401", "403"}:
        return True
    auth_words = ("token", "auth", "credential", "login", "unauthorized", "forbidden", "expired")
    return any(word in message for word in auth_words)


def _safe_exception_details(exc: Exception, message: str) -> Dict[str, str]:
    return {"exception": type(exc).__name__, "message": message}


def _get_dashen_api_client() -> Any:
    try:
        from overstats.src.client.apiclient import dashen_api_client
    except ModuleNotFoundError:
        from src.client.apiclient import dashen_api_client
    return dashen_api_client


class DashenAuthService:
    def __init__(
        self,
        *,
        config_loader: Callable[[], Any] = get_dashen_client_config,
        probe_runner: Optional[Callable[[], Awaitable[Any]]] = None,
    ) -> None:
        self._config_loader = config_loader
        self._probe_runner = probe_runner

    def status(self) -> Dict[str, Any]:
        try:
            config = self._config_loader()
        except Exception as exc:
            return {
                "ok": False,
                "state": "credentials_missing",
                "message": "Dashen credentials are not configured.",
                "error": "dashen_auth_config_error",
                "details": _safe_exception_details(exc, "Dashen credential configuration could not be loaded."),
                "accounts": [],
            }

        accounts = []
        has_account = False
        has_placeholder = False
        for index, account in enumerate(_iter_accounts(config), start=1):
            has_account = True
            name = str(_account_field(account, "name", f"account-{index}") or f"account-{index}")
            role_id = _account_field(account, "role_id", "")
            token = _account_field(account, "token", "")
            role_placeholder = _is_placeholder_role_id(role_id)
            token_placeholder = _is_placeholder_token(token)
            configured = not role_placeholder and not token_placeholder
            has_placeholder = has_placeholder or not configured
            accounts.append(
                {
                    "name": name,
                    "configured": configured,
                    "role_id": int(role_id) if str(role_id).isdigit() else None,
                    "role_id_configured": not role_placeholder,
                    "token_configured": not token_placeholder,
                    "token_preview": mask_secret(token) if configured else "",
                }
            )

        if not has_account:
            state = "credentials_missing"
            ok = False
            message = "Dashen credentials are not configured."
        elif has_placeholder:
            state = "credentials_placeholder"
            ok = False
            message = "Dashen credentials still contain placeholder values."
        else:
            state = "credentials_unverified"
            ok = True
            message = "Dashen credentials are configured but not yet verified."

        return {"ok": ok, "state": state, "message": message, "accounts": accounts}

    async def probe(self) -> Dict[str, Any]:
        current = self.status()
        if current["state"] in {"credentials_missing", "credentials_placeholder"}:
            return current

        try:
            payload = await self._run_probe()
        except Exception as exc:
            exception_message = str(exc)
            if (
                "401" in exception_message
                or "403" in exception_message
                or "token" in exception_message.lower()
                or "auth" in exception_message.lower()
            ):
                return {
                    "ok": False,
                    "state": "credentials_invalid",
                    "message": "Dashen credentials appear to be invalid or expired.",
                    "error": "dashen_auth_invalid",
                    "details": _safe_exception_details(exc, "Dashen credential probe failed authentication."),
                    "accounts": current.get("accounts", []),
                }
            return {
                "ok": False,
                "state": "upstream_limited_or_unavailable",
                "message": "Dashen upstream is unavailable or rate limited.",
                "error": "dashen_upstream_unavailable",
                "details": _safe_exception_details(exc, "Dashen upstream probe failed before verification completed."),
                "accounts": current.get("accounts", []),
            }

        if _auth_failure_from_payload(payload):
            return {
                "ok": False,
                "state": "credentials_invalid",
                "message": "Dashen credentials appear to be invalid or expired.",
                "error": "dashen_auth_invalid",
                "accounts": current.get("accounts", []),
            }

        return {
            "ok": True,
            "state": "credentials_ready",
            "message": "Dashen credentials are ready.",
            "accounts": current.get("accounts", []),
        }

    async def _run_probe(self) -> Any:
        if self._probe_runner is not None:
            return await self._probe_runner()
        dashen_api_client = _get_dashen_api_client()
        return await dashen_api_client.search_bnet_account(PROBE_BATTLE_TAG)


dashen_auth_module = DashenAuthService()
