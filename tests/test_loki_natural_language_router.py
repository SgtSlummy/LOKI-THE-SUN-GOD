from __future__ import annotations

from loki_engine.natural_language import NaturalLanguageRights, route_natural_language_request
from loki_engine.permissions import ADMINISTRATOR, MANAGE_GUILD, PermissionContext


def user_context(*, permissions: int = 0) -> PermissionContext:
    return PermissionContext(user_id=123, guild_id=456, permissions=permissions)


def test_any_member_question_routes_to_llm_answer_without_admin_rights():
    route = route_natural_language_request("LOKI, what did people talk about today?", user_context())

    assert route.allowed is True
    assert route.intent == "question"
    assert route.action == "answer_question"
    assert route.reason == "Questions are open to every member."


def test_admin_change_request_is_blocked_without_admin_or_manage_guild_rights():
    route = route_natural_language_request("change the welcome channel to general", user_context())

    assert route.allowed is False
    assert route.intent == "admin_change"
    assert route.action == "change_server_settings"
    assert "administrator or manage-guild" in route.reason.lower()


def test_admin_change_request_is_allowed_for_manage_guild_or_administrator():
    manage_route = route_natural_language_request(
        "disable invites and update automod settings",
        user_context(permissions=MANAGE_GUILD),
    )
    admin_route = route_natural_language_request(
        "reset the npc personality",
        user_context(permissions=ADMINISTRATOR),
    )

    assert manage_route.allowed is True
    assert admin_route.allowed is True
    assert manage_route.intent == "admin_change"
    assert admin_route.intent == "admin_change"


def test_search_requests_are_denied_until_matching_right_is_granted():
    local_route = route_natural_language_request("search memory for Alice's music taste", user_context())
    online_route = route_natural_language_request("search the web for new AI music tools", user_context())

    assert local_route.allowed is False
    assert local_route.intent == "local_search"
    assert local_route.action == "search_local_memory"
    assert "local search right" in local_route.reason.lower()
    assert online_route.allowed is False
    assert online_route.intent == "online_search"
    assert online_route.action == "search_online"
    assert "online search right" in online_route.reason.lower()


def test_search_requests_follow_individual_local_and_online_rights():
    local_rights = NaturalLanguageRights(can_search_local=True)
    online_rights = NaturalLanguageRights(can_search_online=True)

    local_route = route_natural_language_request(
        "look up our saved memory for Bob",
        user_context(),
        rights=local_rights,
    )
    online_route = route_natural_language_request(
        "google the latest Discord bot hosting options",
        user_context(),
        rights=online_rights,
    )

    assert local_route.allowed is True
    assert local_route.intent == "local_search"
    assert online_route.allowed is True
    assert online_route.intent == "online_search"
