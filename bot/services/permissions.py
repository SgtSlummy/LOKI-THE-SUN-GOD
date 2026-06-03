from __future__ import annotations

from typing import Any


class PermissionManager:
    def __init__(self, *, admin_user_ids: set[int]):
        self.admin_user_ids = admin_user_ids

    def is_admin_interaction(self, interaction: Any) -> bool:
        user = getattr(interaction, "user", None)
        user_id = getattr(user, "id", None)
        if user_id in self.admin_user_ids:
            return True

        permissions = getattr(interaction, "permissions", None)
        if permissions is None and user is not None:
            permissions = getattr(user, "guild_permissions", None)
        return bool(getattr(permissions, "administrator", False))

