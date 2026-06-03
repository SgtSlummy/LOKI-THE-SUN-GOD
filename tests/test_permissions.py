from types import SimpleNamespace

from bot.services.permissions import PermissionManager


def test_admin_permission_accepts_configured_owner_id():
    manager = PermissionManager(admin_user_ids={123})
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=123),
        guild_id=1,
        permissions=SimpleNamespace(administrator=False),
    )

    assert manager.is_admin_interaction(interaction) is True


def test_admin_permission_accepts_discord_administrator_permission():
    manager = PermissionManager(admin_user_ids=set())
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=456),
        guild_id=1,
        permissions=SimpleNamespace(administrator=True),
    )

    assert manager.is_admin_interaction(interaction) is True


def test_admin_permission_rejects_non_admins():
    manager = PermissionManager(admin_user_ids={123})
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=456),
        guild_id=1,
        permissions=SimpleNamespace(administrator=False),
    )

    assert manager.is_admin_interaction(interaction) is False

