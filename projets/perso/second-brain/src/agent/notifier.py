"""
Second Brain — Notification System (Phase 3)
===============================================
Sends desktop notifications for proactive insights.

Primary backend: macOS native notifications via osascript (zero deps).
Fallback: plyer library for cross-platform support.

Anti-spam: enforces a minimum cooldown between notifications.
"""

import logging
import subprocess
import platform
import time

from config.settings import NOTIFICATION_COOLDOWN

logger = logging.getLogger(__name__)

# ── State ───────────────────────────────────────────────────────────
_last_notification_time: float = 0.0

# ── Constants ───────────────────────────────────────────────────────
MAX_MESSAGE_LENGTH = 200
APP_TITLE = "🧠 Second Cerveau"


# ── Public API ──────────────────────────────────────────────────────

def notify(text: str, title: str = APP_TITLE) -> bool:
    """
    Send a desktop notification.

    Handles message truncation and anti-spam cooldown.

    Args:
        text:  Notification body text.
        title: Notification title.

    Returns:
        True if the notification was sent, False if skipped/failed.
    """
    global _last_notification_time

    if not text or not text.strip():
        return False

    # Anti-spam: enforce cooldown
    now = time.time()
    elapsed = now - _last_notification_time
    if elapsed < NOTIFICATION_COOLDOWN:
        logger.debug(
            f"Notification cooldown: {NOTIFICATION_COOLDOWN - elapsed:.0f}s remaining"
        )
        return False

    # Truncate long messages
    display_text = _truncate(text, MAX_MESSAGE_LENGTH)

    # Send notification
    success = _send_notification(title, display_text)

    if success:
        _last_notification_time = now
        logger.info(f"Notification sent: {display_text[:80]}...")

    return success


def notify_insights(insights: list[str]) -> int:
    """
    Send notifications for a list of insights.

    Combines multiple insights into a single notification
    to avoid notification spam.

    Args:
        insights: List of insight strings.

    Returns:
        Number of notifications sent.
    """
    if not insights:
        return 0

    # Combine top insights into one message
    if len(insights) == 1:
        message = insights[0]
    else:
        # Show first 2-3 insights in one notification
        top = insights[:3]
        message = " | ".join(top)

    success = notify(message)
    return 1 if success else 0


# ── Backend Implementations ─────────────────────────────────────────

def _send_notification(title: str, message: str) -> bool:
    """
    Send a desktop notification using the best available backend.

    Priority:
    1. macOS: osascript (native, zero deps)
    2. Fallback: plyer library
    3. Last resort: terminal print
    """
    system = platform.system()

    if system == "Darwin":
        return _notify_macos(title, message)

    # Fallback: plyer
    if _notify_plyer(title, message):
        return True

    # Last resort: print to terminal
    return _notify_terminal(title, message)


def _notify_macos(title: str, message: str) -> bool:
    """Send notification via macOS osascript (AppleScript)."""
    try:
        # Escape quotes for AppleScript
        safe_title = title.replace('"', '\\"')
        safe_message = message.replace('"', '\\"')

        script = (
            f'display notification "{safe_message}" '
            f'with title "{safe_title}"'
        )

        subprocess.run(
            ["osascript", "-e", script],
            timeout=5,
            capture_output=True,
        )
        return True

    except subprocess.TimeoutExpired:
        logger.warning("osascript notification timed out")
        return False
    except Exception as e:
        logger.warning(f"osascript notification failed: {e}")
        return False


def _notify_plyer(title: str, message: str) -> bool:
    """Send notification via plyer library (cross-platform fallback)."""
    try:
        from plyer import notification as plyer_notification

        plyer_notification.notify(
            title=title,
            message=message,
            timeout=10,
        )
        return True

    except ImportError:
        logger.debug("plyer not installed, skipping")
        return False
    except Exception as e:
        logger.warning(f"plyer notification failed: {e}")
        return False


def _notify_terminal(title: str, message: str) -> bool:
    """Print notification to terminal as last resort."""
    print(f"\n{'='*50}")
    print(f"🔔 {title}")
    print(f"   {message}")
    print(f"{'='*50}\n")
    return True


# ── Helpers ─────────────────────────────────────────────────────────

def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max_length, adding '...' if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3].rstrip() + "..."


def reset_cooldown():
    """Reset the notification cooldown (useful for testing)."""
    global _last_notification_time
    _last_notification_time = 0.0
