"""Posting job output to Zulip.

One function, one job: turn a message into an HTTP POST to a Zulip incoming
webhook. Deliberately thin -- no retry logic, no queueing -- because the
caller is always a Nautobot Job, which already has its own logger and its
own record of success/failure; duplicating that here would just be a second
place for the same information to drift out of sync.

The webhook URL is read from this app's own settings
(``PLUGINS_CONFIG["nautobot_spare_parts"]["zulip_webhook_url"]``), never from
an argument a caller could accidentally hardcode, and an unset URL is a
silent no-op rather than an error -- every job that can notify Zulip has to
keep working on an instance that has never configured it.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

#: How long to wait for Zulip before giving up. A Job should never hang
#: because a third-party webhook is slow.
TIMEOUT_SECONDS = 10


def _app_setting(key, default=""):
    """Read one of this app's own PLUGINS_CONFIG settings."""
    return settings.PLUGINS_CONFIG.get("nautobot_spare_parts", {}).get(key, default)


def is_configured():
    """Whether a Zulip webhook URL is set at all."""
    return bool(_app_setting("zulip_webhook_url"))


def send_message(text):
    """POST ``text`` to the configured Zulip webhook.

    Payload shape is ``{"text": ...}`` -- not the generic Zulip bot API's
    ``{"topic", "content"}`` -- to match the existing incoming-webhook
    integration already proven working for other EEN alerting scripts
    (``report_common.py``'s ``send_zulip``). The stream/topic for this
    webhook is fixed on the Zulip side, not something a caller here sets.

    Returns ``True`` if the webhook was configured and accepted the message,
    ``False`` if nothing was sent (not configured) or Zulip rejected it. Never
    raises: a notification failure should show up as a log line, not as the
    calling Job itself failing.
    """
    webhook_url = _app_setting("zulip_webhook_url")
    if not webhook_url:
        logger.info("Zulip webhook not configured; skipping notification.")
        return False

    try:
        response = requests.post(webhook_url, json={"text": text}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Failed to post to Zulip.")
        return False
    return True


def notify_job(job_logger, text):
    """Send ``text`` and log the outcome on the calling Job's own logger.

    The one thing every Job that can notify Zulip needs: post it, then log
    whether it actually went anywhere, without each Job repeating the same
    three-way if/elif.
    """
    if send_message(text):
        job_logger.info("Posted to Zulip.")
    elif is_configured():
        job_logger.warning("Zulip is configured but the post failed. Check the Nautobot logs.")
    else:
        job_logger.info("Zulip is not configured; nothing was posted.")
