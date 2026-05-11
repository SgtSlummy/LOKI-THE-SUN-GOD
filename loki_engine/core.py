from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from loki_engine.permissions import PermissionContext, PermissionDecision, assert_admin_action, can_manage_activity


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    action: str
    reason: str

    @classmethod
    def from_permission(cls, decision: PermissionDecision) -> "ActionDecision":
        return cls(allowed=decision.allowed, action=decision.action, reason=decision.reason)


@dataclass(frozen=True)
class AuditRecord:
    action: str
    actor_id: int
    guild_id: int | None
    allowed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time()))


class LokiEngine:
    """Small central policy interface shared by bot, dashboard, MCP, and agents."""

    def __init__(self) -> None:
        self._audit_records: list[AuditRecord] = []

    def decide_discord_settings_change(self, context: PermissionContext, action: str) -> ActionDecision:
        return ActionDecision.from_permission(assert_admin_action(context, action))

    def decide_activity_change(self, context: PermissionContext) -> ActionDecision:
        return ActionDecision.from_permission(can_manage_activity(context))

    def audit(
        self,
        context: PermissionContext,
        action: str,
        decision: ActionDecision | PermissionDecision,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            action=action,
            actor_id=context.user_id,
            guild_id=context.guild_id,
            allowed=decision.allowed,
            reason=decision.reason,
            details=details or {},
        )
        self._audit_records.append(record)
        return record

    def audit_records(self) -> list[AuditRecord]:
        return list(self._audit_records)
