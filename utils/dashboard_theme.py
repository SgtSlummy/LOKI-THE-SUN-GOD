from __future__ import annotations

DASHBOARD_BRAND = {
    "name": "LOKI THE SUN GOD",
    "dashboard_title": "LOKI THE SUN GOD Dashboard",
    "desktop_title": "LOKI THE SUN GOD Dashboard",
    "initials": "B",
    "subtitle": "Admin surface for LOKI THE SUN GOD",
    "icon_alt": "LOKI THE SUN GOD dashboard icon",
}

DASHBOARD_COLORS = {
    "blurple": "#5865F2",
    "blurple_hover": "#4752C4",
    "bart_yellow": "#f6c244",
    "shirt_red": "#e24732",
    "skate_green": "#22c55e",
    "ink_950": "#0c0d10",
    "ink_900": "#15171b",
    "ink_800": "#1e2025",
    "ink_700": "#2b2d31",
    "ink_600": "#3f4147",
    "mint": "#22c55e",
    "amber": "#f59e0b",
    "rose": "#ef4444",
}


def css_variables() -> str:
    return ";".join(f"--loki-{name.replace('_', '-')}: {value}" for name, value in DASHBOARD_COLORS.items())
