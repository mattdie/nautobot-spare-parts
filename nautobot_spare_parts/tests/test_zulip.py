"""Tests for the Zulip notifier.

Every test here mocks ``requests.post`` -- nothing in this module is allowed
to make a real HTTP call. The webhook URL is also always overridden to a
fake value via ``override_settings``, never left pointing at whatever a real
deployment's PLUGINS_CONFIG happens to have.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from nautobot_spare_parts import zulip

FAKE_PLUGIN_SETTINGS = {"nautobot_spare_parts": {"zulip_webhook_url": "https://example.invalid/webhook"}}


class IsConfiguredTestCase(SimpleTestCase):
    """Whether a webhook URL is set at all."""

    @override_settings(PLUGINS_CONFIG=FAKE_PLUGIN_SETTINGS)
    def test_true_when_a_url_is_set(self):
        self.assertTrue(zulip.is_configured())

    @override_settings(PLUGINS_CONFIG={"nautobot_spare_parts": {"zulip_webhook_url": ""}})
    def test_false_when_blank(self):
        self.assertFalse(zulip.is_configured())

    @override_settings(PLUGINS_CONFIG={})
    def test_false_when_the_app_has_no_settings_at_all(self):
        self.assertFalse(zulip.is_configured())


class SendMessageTestCase(SimpleTestCase):
    """send_message() posts, and never raises."""

    @override_settings(PLUGINS_CONFIG={"nautobot_spare_parts": {"zulip_webhook_url": ""}})
    def test_not_configured_is_a_no_op(self):
        with patch("nautobot_spare_parts.zulip.requests.post") as mock_post:
            result = zulip.send_message("hello")
        self.assertFalse(result)
        mock_post.assert_not_called()

    @override_settings(PLUGINS_CONFIG=FAKE_PLUGIN_SETTINGS)
    def test_configured_posts_the_text_payload_to_the_webhook_url(self):
        mock_response = MagicMock(status_code=200)
        mock_response.raise_for_status.return_value = None
        with patch("nautobot_spare_parts.zulip.requests.post", return_value=mock_response) as mock_post:
            result = zulip.send_message("hello from a test")

        self.assertTrue(result)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://example.invalid/webhook")
        self.assertEqual(kwargs["json"], {"text": "hello from a test"})

    @override_settings(PLUGINS_CONFIG=FAKE_PLUGIN_SETTINGS)
    def test_a_request_exception_is_swallowed_not_raised(self):
        import requests

        with patch("nautobot_spare_parts.zulip.requests.post", side_effect=requests.ConnectionError("down")):
            result = zulip.send_message("hello")
        self.assertFalse(result)


class NotifyJobTestCase(SimpleTestCase):
    """notify_job() logs the outcome instead of making the caller branch on it."""

    @override_settings(PLUGINS_CONFIG=FAKE_PLUGIN_SETTINGS)
    def test_logs_info_on_success(self):
        logger = MagicMock()
        mock_response = MagicMock(status_code=200)
        mock_response.raise_for_status.return_value = None
        with patch("nautobot_spare_parts.zulip.requests.post", return_value=mock_response):
            zulip.notify_job(logger, "hello")
        logger.info.assert_called_once_with("Posted to Zulip.")

    @override_settings(PLUGINS_CONFIG={"nautobot_spare_parts": {"zulip_webhook_url": ""}})
    def test_logs_info_when_not_configured(self):
        logger = MagicMock()
        with patch("nautobot_spare_parts.zulip.requests.post") as mock_post:
            zulip.notify_job(logger, "hello")
        mock_post.assert_not_called()
        logger.info.assert_called_with("Zulip is not configured; nothing was posted.")

    @override_settings(PLUGINS_CONFIG=FAKE_PLUGIN_SETTINGS)
    def test_logs_warning_when_configured_but_the_post_fails(self):
        import requests

        logger = MagicMock()
        with patch("nautobot_spare_parts.zulip.requests.post", side_effect=requests.ConnectionError("down")):
            zulip.notify_job(logger, "hello")
        logger.warning.assert_called_once_with("Zulip is configured but the post failed. Check the Nautobot logs.")
