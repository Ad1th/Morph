"""Locale collector: language/region locale (as a BCP-47 tag, e.g. "en-IN") and timezone."""

import locale
import platform
import time

from morph.schema.profile import FieldStatus, LocaleInfo, ProfileField


def _locale_name() -> str:
    if platform.system() == "Windows":
        # locale.getlocale() returns a Windows display name ("English_India") on
        # Windows, not a usable BCP-47 tag. GetUserDefaultLocaleName gives the
        # real tag ("en-IN") directly, matching every example in the PRD/spec.
        import ctypes

        buf = ctypes.create_unicode_buffer(85)
        ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)
        if buf.value:
            return buf.value
    return (locale.getlocale()[0] or "en_US").replace("_", "-")


def collect_locale() -> LocaleInfo:
    timezone = time.tzname[0] if time.tzname else "UTC"

    return LocaleInfo(
        locale=ProfileField(value=_locale_name(), status=FieldStatus.CAPTURED),
        timezone=ProfileField(value=timezone, status=FieldStatus.CAPTURED),
    )
