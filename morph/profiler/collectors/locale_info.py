"""Locale collector: language/region locale and timezone."""

import locale
import time

from morph.schema.profile import FieldStatus, LocaleInfo, ProfileField


def collect_locale() -> LocaleInfo:
    loc = locale.getlocale()[0] or "en_US"
    timezone = time.tzname[0] if time.tzname else "UTC"

    return LocaleInfo(
        locale=ProfileField(value=loc.replace("_", "-"), status=FieldStatus.CAPTURED),
        timezone=ProfileField(value=timezone, status=FieldStatus.CAPTURED),
    )
