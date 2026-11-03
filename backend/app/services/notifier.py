"""Notifier interface and disabled stubs for external notification channels.

docs/08_API_AND_UI.md section 5:
Notifier interface with disabled stubs for email/Telegram.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """Abstract interface for external alert notifications."""

    @abstractmethod
    def send_alert(self, alert: dict[str, Any]) -> bool:
        """Send an alert to the external channel. Returns True if sent, False otherwise."""


class EmailNotifier(Notifier):
    """Stub for SMTP / email notifications."""

    def __init__(self, enabled: bool = False, recipient: str = ""):
        self.enabled = enabled
        self.recipient = recipient

    def send_alert(self, alert: dict[str, Any]) -> bool:
        if not self.enabled:
            logger.debug(f"EmailNotifier disabled; suppressed alert: {alert.get('id')}")
            return False
        # Stub for future implementation
        logger.info(f"Email notification stub sent to {self.recipient}: {alert.get('message')}")
        return True


class TelegramNotifier(Notifier):
    """Stub for Telegram bot notifications."""

    def __init__(self, enabled: bool = False, chat_id: str = ""):
        self.enabled = enabled
        self.chat_id = chat_id

    def send_alert(self, alert: dict[str, Any]) -> bool:
        if not self.enabled:
            logger.debug(f"TelegramNotifier disabled; suppressed alert: {alert.get('id')}")
            return False
        # Stub for future implementation
        logger.info(f"Telegram notification stub sent to {self.chat_id}: {alert.get('message')}")
        return True


class MultiNotifier(Notifier):
    """Dispatches alerts across a list of configured notifiers."""

    def __init__(self, notifiers: list[Notifier] | None = None):
        self.notifiers = notifiers or []

    def send_alert(self, alert: dict[str, Any]) -> bool:
        dispatched = False
        for notifier in self.notifiers:
            try:
                if notifier.send_alert(alert):
                    dispatched = True
            except Exception as e:  # noqa: BLE001
                logger.error(f"Notifier error in {type(notifier).__name__}: {e}")
        return dispatched
