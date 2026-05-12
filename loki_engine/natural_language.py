from __future__ import annotations

from dataclasses import dataclass

from loki_engine.permissions import PermissionContext, assert_admin_action


@dataclass(frozen=True)
class NaturalLanguageRights:
    can_search_local: bool = False
    can_search_online: bool = False


@dataclass(frozen=True)
class NaturalLanguageRoute:
    allowed: bool
    intent: str
    action: str
    reason: str


ADMIN_CHANGE_TERMS = (
    "change ",
    "set ",
    "disable ",
    "enable ",
    "reset ",
    "delete ",
    "remove ",
    "update ",
    "configure ",
    "automod",
    "welcome channel",
    "goodbye channel",
    "mute role",
    "npc personality",
    "permissions",
)
ONLINE_SEARCH_TERMS = (
    "search the web",
    "search online",
    "google",
    "internet",
    "latest",
    "current news",
)
LOCAL_SEARCH_TERMS = (
    "search memory",
    "saved memory",
    "our memory",
    "server memory",
    "look up our",
    "what do we know about",
)


def route_natural_language_request(
    prompt: str,
    context: PermissionContext,
    *,
    rights: NaturalLanguageRights | None = None,
) -> NaturalLanguageRoute:
    rights = rights or NaturalLanguageRights()
    normalized = f" {prompt.lower().strip()} "

    if _contains_any(normalized, ONLINE_SEARCH_TERMS):
        if rights.can_search_online:
            return NaturalLanguageRoute(True, "online_search", "search_online", "Online search right granted.")
        return NaturalLanguageRoute(False, "online_search", "search_online", "Online search right is required.")

    if _contains_any(normalized, LOCAL_SEARCH_TERMS):
        if rights.can_search_local:
            return NaturalLanguageRoute(True, "local_search", "search_local_memory", "Local search right granted.")
        return NaturalLanguageRoute(False, "local_search", "search_local_memory", "Local search right is required.")

    if _contains_any(normalized, ADMIN_CHANGE_TERMS):
        decision = assert_admin_action(context, "change_server_settings")
        return NaturalLanguageRoute(
            decision.allowed,
            "admin_change",
            decision.action,
            decision.reason,
        )

    return NaturalLanguageRoute(True, "question", "answer_question", "Questions are open to every member.")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
