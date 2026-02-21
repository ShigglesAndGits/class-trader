"""
Notification system using Apprise.

Sends alerts for: trade proposals, executions, circuit breakers, system errors,
and daily summaries. Silently no-ops if no APPRISE_URLS are configured —
the system degrades gracefully to log-only mode.

Apprise supports 70+ notification platforms via URL schemes. Configure via
APPRISE_URLS in .env. Multiple URLs = comma-separated.
"""

import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


class Notifier:
    """
    Thin async wrapper around Apprise.
    All public methods are safe to await even if Apprise is not installed
    or no URLs are configured.
    """

    def __init__(self, urls: list[str]) -> None:
        self._urls = urls
        self._apprise = None

        if not urls:
            logger.info("Notifier: no APPRISE_URLS configured — running in log-only mode.")
            return

        try:
            import apprise

            self._apprise = apprise.Apprise()
            added = 0
            for url in urls:
                if self._apprise.add(url):
                    added += 1
                else:
                    logger.warning(f"Notifier: failed to add Apprise URL (invalid scheme?): {url!r}")
            logger.info(f"Notifier: initialized with {added}/{len(urls)} valid endpoint(s).")
        except ImportError:
            logger.warning(
                "Notifier: apprise package not installed. "
                "Install it to enable push notifications. Running in log-only mode."
            )

    async def send(
        self,
        event_type: str,
        message: str,
        title: Optional[str] = None,
    ) -> None:
        """
        Send a notification. Falls back to a log entry if Apprise is unavailable.

        event_type: used to build the default title and for log identification.
        """
        notification_title = title or _default_title(event_type)

        if not self._apprise:
            logger.info(f"[Notification — {event_type}] {notification_title}: {message[:200]}")
            return

        try:
            await self._apprise.async_notify(
                body=message,
                title=notification_title,
            )
            logger.info(f"Notification sent: {event_type}")
        except Exception as e:
            logger.error(f"Failed to send notification ({event_type}): {e}")

    async def trade_proposed(
        self,
        ticker: str,
        action: str,
        sleeve: str,
        confidence: float,
        reasoning: str,
        wash_sale_flagged: bool = False,
    ) -> None:
        """Convenience method for trade-pending-approval notifications."""
        wash_note = "\n⚠️ Wash sale window active — cost basis will be adjusted." if wash_sale_flagged else ""
        message = (
            f"{action} {ticker} ({sleeve} sleeve)\n"
            f"Confidence: {confidence:.0%}\n"
            f"Reasoning: {reasoning[:400]}{'...' if len(reasoning) > 400 else ''}"
            f"{wash_note}"
        )
        await self.send(
            event_type="trade_proposed",
            message=message,
            title=f"Approval Required: {action} {ticker}",
        )

    async def trade_executed(
        self,
        ticker: str,
        action: str,
        qty: float,
        filled_price: float,
        sleeve: str,
        slippage: float,
    ) -> None:
        """Convenience method for trade execution confirmations."""
        slippage_note = f"Slippage: ${slippage:+.3f}/share" if slippage != 0 else "No slippage."
        message = (
            f"{action} {qty:.0f} × {ticker} @ ${filled_price:.2f}\n"
            f"Sleeve: {sleeve}\n"
            f"{slippage_note}"
        )
        await self.send(
            event_type="trade_executed",
            message=message,
            title=f"Trade Executed: {action} {ticker}",
        )

    async def circuit_breaker(
        self,
        event_type: str,
        sleeve: Optional[str],
        reason: str,
    ) -> None:
        """Convenience method for circuit breaker alerts."""
        target = sleeve or "ALL sleeves"
        message = f"Trading halted for {target}.\n\nReason: {reason}\n\nResolve via Settings → Circuit Breakers."
        await self.send(
            event_type="circuit_breaker",
            message=message,
            title=f"Circuit Breaker: {event_type}",
        )

    async def system_error(self, message: str, context: Optional[str] = None) -> None:
        """Convenience method for system-level error alerts."""
        full_message = message
        if context:
            full_message += f"\n\nContext: {context}"
        await self.send(
            event_type="system_error",
            message=full_message,
            title="Class Trader — System Error",
        )

    async def daily_summary(
        self,
        main_pnl: float,
        penny_pnl: float,
        trades_executed: int,
        regime: str,
    ) -> None:
        """End-of-day summary notification."""
        total_pnl = main_pnl + penny_pnl
        sign = "+" if total_pnl >= 0 else ""
        footer = "Nothing today. The market can wait." if trades_executed == 0 else ""
        message = (
            f"Today's P&L: {sign}${total_pnl:.2f}\n"
            f"  Main sleeve: {'+' if main_pnl >= 0 else ''}${main_pnl:.2f}\n"
            f"  Penny sleeve: {'+' if penny_pnl >= 0 else ''}${penny_pnl:.2f}\n"
            f"Trades executed: {trades_executed}\n"
            f"Market regime: {regime}"
            + (f"\n\n{footer}" if footer else "")
        )
        await self.send(
            event_type="daily_summary",
            message=message.strip(),
            title="Daily Summary",
        )


@lru_cache(maxsize=1)
def get_notifier() -> Notifier:
    """Singleton Notifier, initialized once from settings."""
    from app.config import get_settings

    settings = get_settings()
    return Notifier(settings.apprise_url_list)


def _default_title(event_type: str) -> str:
    titles = {
        "trade_proposed": "Trade Pending Approval",
        "trade_executed": "Trade Executed",
        "circuit_breaker": "Circuit Breaker Triggered",
        "system_error": "System Error",
        "daily_summary": "Daily Summary",
    }
    return titles.get(event_type, f"Class Trader — {event_type.replace('_', ' ').title()}")
