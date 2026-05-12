from __future__ import annotations

from typing import Any

from utils.hermes_loki_bridge import legacy_bot_search_terms


def _user(member: dict[str, Any]) -> dict[str, Any]:
    return member.get("user") or {}


def identify_old_loki_bot(members: list[dict[str, Any]], *, current_bot_id: str) -> dict[str, Any] | None:
    matcher = legacy_bot_search_terms()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for member in members:
        user = _user(member)
        if not user.get("bot") or str(user.get("id")) == str(current_bot_id):
            continue
        username = str(user.get("global_name") or user.get("username") or "")
        role_text = " ".join(str(role) for role in member.get("roles", []))
        score = 0
        if matcher.search(username):
            score += 10
        if matcher.search(role_text):
            score += 3
        if "loki" in username.lower() and "sun" in username.lower():
            score += 5
        if score:
            candidates.append((score, member))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def bot_role_delta(*, old_role_ids: list[str], current_role_ids: list[str]) -> list[str]:
    current = {str(role_id) for role_id in current_role_ids}
    return [str(role_id) for role_id in old_role_ids if str(role_id) not in current]


def role_names(role_ids: list[str], roles_by_id: dict[str, dict[str, Any]]) -> list[str]:
    return [str(roles_by_id.get(str(role_id), {}).get("name") or role_id) for role_id in role_ids]


def render_legacy_bot_report(
    *,
    guild_name: str,
    old_bot: dict[str, Any],
    current_bot: dict[str, Any],
    roles_by_id: dict[str, dict[str, Any]],
    old_messages: list[dict[str, Any]],
    roles_to_assume: list[str],
    executed: bool,
) -> str:
    old_user = _user(old_bot)
    current_user = _user(current_bot)
    old_roles = role_names([str(role) for role in old_bot.get("roles", [])], roles_by_id)
    current_roles = role_names([str(role) for role in current_bot.get("roles", [])], roles_by_id)
    assume_roles = role_names(roles_to_assume, roles_by_id)
    lines = [
        "# LOKI Legacy Bot Takeover Report",
        "",
        f"Guild: {guild_name}",
        f"Executed: {'yes' if executed else 'no'}",
        "",
        "## Current LOKI",
        f"- {current_user.get('username')} ({current_user.get('id')})",
        "- Roles: " + (", ".join(current_roles) or "none"),
        "",
        "## Legacy Bot Identified",
        f"- {old_user.get('username')} ({old_user.get('id')})",
        "- Roles: " + (", ".join(old_roles) or "none"),
        "",
        "## Roles LOKI Should Assume",
        "- " + ("\n- ".join(assume_roles) if assume_roles else "none; current LOKI already has all legacy roles"),
        "",
        "## Recent Legacy Bot Evidence",
    ]
    if old_messages:
        for message in old_messages[:25]:
            content = " ".join(str(message.get("content") or "").split())[:250]
            lines.append(f"- #{message.get('channel_name', 'unknown')}: {content or '[embed/attachment/no text]'}")
    else:
        lines.append("- No recent accessible messages were found for the legacy bot.")
    lines.extend(
        [
            "",
            "## Takeover Actions",
            "- Research Discord roles, channels, and accessible recent messages.",
            "- Assign legacy bot roles to current LOKI when Discord permissions allow it.",
            "- Remove the identified legacy LOKI bot from the guild after role assumption.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
