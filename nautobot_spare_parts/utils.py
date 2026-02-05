"""Utility functions for Nautobot Spare Parts plugin."""

from packaging import version
import nautobot


def get_nautobot_version():
    """Get the current Nautobot version."""
    return version.parse(nautobot.__version__)


def is_nautobot_2_3_or_newer():
    """Check if Nautobot version is 2.3 or newer."""
    return get_nautobot_version() >= version.parse("2.3.0")


def is_nautobot_3_0_or_newer():
    """Check if Nautobot version is 3.0 or newer."""
    return get_nautobot_version() >= version.parse("3.0.0")
