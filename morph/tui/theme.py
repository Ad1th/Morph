"""Morph's design tokens as Textual Themes, plus a palette helper for widgets
that paint with Rich.

The palette matches the product's landing page: an abyss/rose ground with a
gold evidence accent. Every widget reads colours through :func:`palette` so a
theme switch (``F2``) restyles the lanes, gauge and matrix, not just the CSS.

Semantics
    pass      -> green        (a trial passed, a field is REPRODUCED)
    fail      -> rose         (a trial failed, a verdict blames the environment)
    evidence  -> gold         (e-values, thresholds, credible bands, stamps)
    warn      -> amber        (APPROXIMATED, near a boundary)
    text/muted-> bone/bone-dim
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.theme import Theme

ABYSS = "#17030a"
BASE = "#2b060f"
RAISED = "#4a0e22"
GLOW_ROSE = "#e0447c"
ROSE_SOFT = "#f79cbc"
GOLD = "#d8a24a"
GOLD_DIM = "#9c7231"
BONE = "#f5ede6"
BONE_DIM = "#bd93a1"
GREEN = "#4fbf7a"
AMBER = "#e2b04a"

# Light counterparts: the same hues on a bone ground.
L_GROUND = "#fbf6f1"
L_SURFACE = "#f3e7e0"
L_PANEL = "#e9d3cf"
L_INK = "#2b060f"
L_INK_DIM = "#7a5560"
L_GREEN = "#1f8a4c"
L_AMBER = "#9a6b12"
L_GOLD = "#8d6520"
L_ROSE = "#c22a63"

_SEMANTIC_DARK = {
    "pass": GREEN,
    "fail": GLOW_ROSE,
    "evidence": GOLD,
    "evidence-dim": GOLD_DIM,
    "warn": AMBER,
    "bone": BONE,
    "bone-dim": BONE_DIM,
    "rose-soft": ROSE_SOFT,
    "abyss": ABYSS,
    "raised": RAISED,
    "track": "#3a0c1c",
    "ink-on-pass": ABYSS,
    "ink-on-fail": BONE,
    "ink-on-evidence": ABYSS,
}

_SEMANTIC_LIGHT = {
    "pass": L_GREEN,
    "fail": L_ROSE,
    "evidence": L_GOLD,
    "evidence-dim": GOLD_DIM,
    "warn": L_AMBER,
    "bone": L_INK,
    "bone-dim": L_INK_DIM,
    "rose-soft": "#a33a63",
    "abyss": L_GROUND,
    "raised": L_PANEL,
    "track": "#dcc3c0",
    "ink-on-pass": L_GROUND,
    "ink-on-fail": L_GROUND,
    "ink-on-evidence": L_GROUND,
}

MORPH_DARK = Theme(
    name="morph-dark",
    primary=GLOW_ROSE,
    secondary=GOLD,
    accent=GOLD,
    warning=AMBER,
    error=GLOW_ROSE,
    success=GREEN,
    foreground=BONE,
    background=ABYSS,
    surface=BASE,
    panel=RAISED,
    boost="#5a1a30",
    dark=True,
    variables={
        **_SEMANTIC_DARK,
        "footer-key-foreground": GOLD,
        "footer-description-foreground": BONE_DIM,
        "footer-background": BASE,
        "block-cursor-background": GLOW_ROSE,
        "block-cursor-foreground": BONE,
        "input-cursor-background": GOLD,
        "input-cursor-foreground": ABYSS,
        "input-selection-background": f"{GOLD} 40%",
        "border": GOLD_DIM,
        "border-blurred": RAISED,
        "button-color-foreground": BONE,
        "button-focus-text-style": "bold",
    },
)

MORPH_LIGHT = Theme(
    name="morph-light",
    primary=L_ROSE,
    secondary=L_GOLD,
    accent=L_GOLD,
    warning=L_AMBER,
    error=L_ROSE,
    success=L_GREEN,
    foreground=L_INK,
    background=L_GROUND,
    surface=L_SURFACE,
    panel=L_PANEL,
    boost="#dcbdb8",
    dark=False,
    variables={
        **_SEMANTIC_LIGHT,
        "footer-key-foreground": L_GOLD,
        "footer-description-foreground": L_INK_DIM,
        "footer-background": L_SURFACE,
        "block-cursor-background": L_ROSE,
        "block-cursor-foreground": L_GROUND,
        "input-cursor-background": L_GOLD,
        "input-cursor-foreground": L_GROUND,
        "input-selection-background": f"{L_GOLD} 40%",
        "border": L_GOLD,
        "border-blurred": L_PANEL,
        "button-color-foreground": L_INK,
        "button-focus-text-style": "bold",
    },
)

THEMES = (MORPH_DARK, MORPH_LIGHT)
SEMANTIC_DEFAULTS = dict(_SEMANTIC_DARK)


@dataclass(frozen=True)
class Palette:
    """Resolved colours for Rich rendering inside widgets."""

    pass_: str
    fail: str
    evidence: str
    evidence_dim: str
    warn: str
    text: str
    muted: str
    track: str
    ink_on_pass: str
    ink_on_fail: str
    ink_on_evidence: str
    accent: str
    surface: str


def palette(widget) -> Palette:
    """The active theme's semantic colours, with dark-theme fallbacks so a
    widget rendered outside a Morph app (tests, docs) still paints sensibly."""
    try:
        v = widget.app.get_css_variables()
    except Exception:
        v = {}
    d = _SEMANTIC_DARK

    def get(name: str, default: str) -> str:
        return v.get(name) or default

    return Palette(
        pass_=get("pass", d["pass"]),
        fail=get("fail", d["fail"]),
        evidence=get("evidence", d["evidence"]),
        evidence_dim=get("evidence-dim", d["evidence-dim"]),
        warn=get("warn", d["warn"]),
        text=get("bone", d["bone"]),
        muted=get("bone-dim", d["bone-dim"]),
        track=get("track", d["track"]),
        ink_on_pass=get("ink-on-pass", d["ink-on-pass"]),
        ink_on_fail=get("ink-on-fail", d["ink-on-fail"]),
        ink_on_evidence=get("ink-on-evidence", d["ink-on-evidence"]),
        accent=get("accent", GOLD),
        surface=get("surface", BASE),
    )


def status_style(p: Palette, status: str) -> str:
    """Rich style for a reconcile / fidelity badge."""
    s = (status or "").lower()
    if s in {"reproduced", "exact"}:
        return f"bold {p.pass_}"
    if s in {"approximated", "approximate", "partial"}:
        return f"bold {p.warn}"
    if s in {"unavailable", "unsupported", "none"}:
        return f"bold {p.fail}"
    return p.muted
