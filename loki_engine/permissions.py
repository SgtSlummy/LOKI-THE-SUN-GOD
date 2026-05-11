from __future__ import annotations

from dataclasses import dataclass

ADMINISTRATOR = 0x8
MANAGE_GUILD = 0x20
MANAGE_EVENTS = 0x2000000000
CREATE_EVENTS = 0x8000000000


@dataclass(frozen=True)
class PermissionContext:
    user_id: int
    guild_id: int | None
    permissions: int

    def has(self, flag: int) -> bool:
        return bool(self.permissions & flag)

    @property
    def is_admin(self) -> bool:
        return self.has(ADMINISTRATOR)

    @property
    def can_manage_guild(self) -> bool:
        return self.is_admin or self.has(MANAGE_GUILD)


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    action: str
    reason: str


def assert_admin_action(context: PermissionContext, action: str) -> PermissionDecision:
    if context.can_manage_guild:
        return PermissionDecision(True, action, "Discord administrator or manage-guild permission verified.")
    return PermissionDecision(False, action, "This action requires Discord administrator or manage-guild permission.")


def can_manage_activity(context: PermissionContext) -> PermissionDecision:
    if context.can_manage_guild or context.has(MANAGE_EVENTS) or context.has(CREATE_EVENTS):
        return PermissionDecision(True, "manage_activity", "Activity/event management permission verified.")
    return PermissionDecision(False, "manage_activity", "This action requires create-events, manage-events, or admin.")


def can_create_activity_event(context: PermissionContext) -> PermissionDecision:
    if context.is_admin or context.has(CREATE_EVENTS):
        return PermissionDecision(True, "create_activity_event", "Create-events permission verified.")
    return PermissionDecision(
        False,
        "create_activity_event",
        "Creating Discord scheduled events requires create-events or admin.",
    )
