"""Pluggable SMS delivery. Two interchangeable providers behind one interface:
- "mock": records messages in an in-memory outbox + logs them (no network).
- "africastalking_sandbox": real Africa's Talking sandbox API (no real delivery,
  but the request appears in the AT dashboard Outbox).
The active provider is chosen by settings.SMS_PROVIDER — business logic never
changes.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from app.config import settings

log = logging.getLogger("dawal.sms")


class SmsError(RuntimeError):
    """Raised when an SMS could not be sent (network error or provider rejected
    the message). Callers decide whether that is fatal for the operation."""


@dataclass
class SentSms:
    to: str
    body: str


class SmsProvider(Protocol):
    def send(self, to: str, body: str) -> None: ...


class MockSmsProvider:
    """Records every message so tests and local dev can inspect what would have
    been sent. Never contacts a network."""

    def __init__(self) -> None:
        self.outbox: list[SentSms] = []

    def send(self, to: str, body: str) -> None:
        self.outbox.append(SentSms(to=to, body=body))
        log.info("[MOCK SMS] to=%s body=%s", to, body)

    def clear(self) -> None:
        self.outbox.clear()


class AfricasTalkingProvider:
    """Real SMS via the Africa's Talking SDK. The full API response (recipient
    status codes, message id, cost) is stored on `last_response` and logged, so
    a caller can confirm the request was well-formed and authenticated even
    though the sandbox does not deliver to a real phone."""

    def __init__(self, username: str, api_key: str) -> None:
        # Imported lazily so 'mock' dev never needs the SDK installed.
        import africastalking

        africastalking.initialize(username, api_key)
        self._sms = africastalking.SMS
        self.last_response: dict | None = None

    def send(self, to: str, body: str) -> None:
        try:
            response = self._sms.send(body, [to])
        except Exception as e:  # network/TLS/SDK error
            log.error("[AT SMS] send failed to=%s error=%s", to, e)
            raise SmsError(f"Africa's Talking send failed: {e}") from e

        self.last_response = response
        log.info("[AT SMS] to=%s response=%s", to, response)

        recipients = response.get("SMSMessageData", {}).get("Recipients", [])
        # statusCode 101 = "Success" (queued/sent). Anything else is a rejection.
        if not any(r.get("statusCode") == 101 for r in recipients):
            raise SmsError(f"Africa's Talking did not accept the message: {response}")


_mock_singleton = MockSmsProvider()
_at_singleton: AfricasTalkingProvider | None = None


def get_sms_provider() -> SmsProvider:
    if settings.SMS_PROVIDER == "mock":
        return _mock_singleton
    if settings.SMS_PROVIDER == "africastalking_sandbox":
        global _at_singleton
        if _at_singleton is None:
            _at_singleton = AfricasTalkingProvider(
                settings.SMS_OTP_USERNAME, settings.SMS_OTP_API_KEY
            )
        return _at_singleton
    raise RuntimeError(
        f"Unknown SMS_PROVIDER={settings.SMS_PROVIDER!r}; "
        "expected 'mock' or 'africastalking_sandbox'."
    )
