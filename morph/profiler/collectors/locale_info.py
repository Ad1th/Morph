"""Locale collector: a POSIX locale usable as LC_ALL, its BCP-47 tag, and an IANA timezone.

What is captured must be something `apply_locale` can hand to a child and have
it mean the same thing:

* ``locale``    -> ``en_US.UTF-8`` (POSIX; works as ``LC_ALL`` on Linux/macOS)
* ``language_tag`` -> ``en-US`` (BCP-47 companion; display, Windows targets)
* ``timezone``  -> ``Asia/Kolkata`` (IANA; works as ``TZ``). ``time.tzname``
  gives an abbreviation (``IST``) that libc treats as UTC and that is ambiguous
  (India/Israel/Ireland), so it is only a last resort and is marked APPROXIMATED.
"""

from __future__ import annotations

import locale
import os
import platform
import re
import subprocess
import time
from datetime import datetime

from morph.schema.profile import FieldStatus, LocaleInfo, ProfileField


def _windows_language_tag() -> str | None:
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(85)
        ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85)  # type: ignore[attr-defined]
        return buf.value or None
    except Exception:
        return None


# ll_CC[.encoding][@modifier]; rejects the bare "UTF-8" macOS terminals put in LC_CTYPE.
_POSIX_LOCALE_RE = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?(\.[A-Za-z0-9-]+)?(@\w+)?$")


def _apple_locale() -> str | None:
    if platform.system() != "Darwin":
        return None
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleLocale"],
                             capture_output=True, text=True, timeout=5)
        name = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return name if _POSIX_LOCALE_RE.match(name) else None


def _posix_locale() -> str:
    """The locale a child would inherit, as a POSIX name."""
    for var in ("LC_ALL", "LC_CTYPE", "LANG"):
        value = (os.environ.get(var) or "").strip()
        if value and value not in ("C", "POSIX") and _POSIX_LOCALE_RE.match(value):
            return value if "." in value else f"{value}.UTF-8"
    name = locale.getlocale()[0]
    if name and _POSIX_LOCALE_RE.match(name):
        return f"{name}.UTF-8"
    apple = _apple_locale()
    if apple:
        return f"{apple}.UTF-8"
    return "en_US.UTF-8"


def _locale_pair() -> tuple[str, str]:
    """(posix_locale, bcp47_tag)."""
    if platform.system() == "Windows":
        # locale.getlocale() returns a Windows display name ("English_India") on
        # Windows, not a usable tag. GetUserDefaultLocaleName gives "en-IN".
        tag = _windows_language_tag()
        if tag:
            lang, _, region = tag.partition("-")
            posix = f"{lang.lower()}_{region.upper()}.UTF-8" if region else f"{lang.lower()}.UTF-8"
            return posix, tag
    posix = _posix_locale()
    base = posix.split(".")[0].split("@")[0]
    tag = base.replace("_", "-") if base and base not in ("C", "POSIX") else "en-US"
    return posix, tag


def _iana_from_localtime_symlink() -> str | None:
    """`/etc/localtime -> .../zoneinfo/Asia/Kolkata` on Linux and macOS."""
    try:
        target = os.readlink("/etc/localtime")
    except (OSError, AttributeError):
        return None
    marker = "zoneinfo/"
    idx = target.rfind(marker)
    if idx == -1:
        return None
    name = target[idx + len(marker):].strip("/")
    return name or None


def _iana_from_debian_file() -> str | None:
    try:
        with open("/etc/timezone", encoding="utf-8") as f:
            name = f.read().strip()
        return name or None
    except OSError:
        return None


def _iana_from_windows() -> str | None:
    """`tzutil /g` gives a Windows zone name; map it through tzdata's windowsZones when available."""
    try:
        out = subprocess.run(["tzutil", "/g"], capture_output=True, text=True, timeout=5)
        win_name = out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not win_name:
        return None
    try:
        from tzdata import windows_zones  # not always shipped; best effort

        mapping = getattr(windows_zones, "WINDOWS_TO_IANA", {})
        return mapping.get(win_name) or None
    except Exception:
        return None


def _is_iana(name: str | None) -> bool:
    if not name:
        return False
    if name == "UTC":
        return True
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(name)
        return True
    except Exception:
        return False


def _timezone() -> tuple[str, FieldStatus]:
    """(zone, status): an IANA name when we can prove one, else an APPROXIMATED abbreviation."""
    env_tz = (os.environ.get("TZ") or "").strip().lstrip(":")
    candidates = [env_tz]
    if platform.system() == "Windows":
        candidates.append(_iana_from_windows())
    else:
        candidates.append(_iana_from_localtime_symlink())
        candidates.append(_iana_from_debian_file())
    for name in candidates:
        if _is_iana(name):
            return name, FieldStatus.CAPTURED

    # Last resort: an abbreviation. Honest about it: a child cannot interpret
    # "IST" as anything but UTC, so this is APPROXIMATED, not CAPTURED.
    abbrev = datetime.now().astimezone().tzname() or (time.tzname[0] if time.tzname else "UTC")
    if abbrev == "UTC":
        return "UTC", FieldStatus.CAPTURED
    return abbrev, FieldStatus.APPROXIMATED


def collect_locale() -> LocaleInfo:
    posix, tag = _locale_pair()
    tz, tz_status = _timezone()
    return LocaleInfo(
        locale=ProfileField(value=posix, status=FieldStatus.CAPTURED),
        timezone=ProfileField(value=tz, status=tz_status),
        language_tag=ProfileField(value=tag, status=FieldStatus.CAPTURED),
    )
