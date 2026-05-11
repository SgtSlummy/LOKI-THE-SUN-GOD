import asyncio
import contextlib
import logging
import os
import pkgutil
from pathlib import Path

import discord
from discord.ext import commands

from utils import db, runtime_paths, worker_singleton
from utils.command_descriptions import apply_descriptions_to_bot
from utils.outbound_post_guard import install_outbound_post_guard

runtime_paths.load_app_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("loki")

TOKEN = os.getenv("DISCORD_TOKEN")
DEFAULT_PREFIX = os.getenv("PREFIX", "!")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
TRUTHY = {"1", "true", "yes", "on"}
RELAY_DATABASE_URL_ERROR = (
    "RELAY_ENABLED=true requires DATABASE_URL. LOKI THE SUN GOD relay workers must share "
    "the same database-backed dedupe table; set RELAY_ENABLED=false for local "
    "dashboard-only runs."
)
RELAY_LOCAL_SQLITE_WARNING = (
    "Relay is running with local SQLite because ALLOW_LOCAL_SQLITE_RELAY=true. "
    "Keep any hosted relay worker stopped, or both processes can relay the same live event."
)


def relay_enabled_from_env() -> bool:
    return os.getenv("RELAY_ENABLED", "false").lower() in TRUTHY


def allow_local_sqlite_relay() -> bool:
    return os.getenv("ALLOW_LOCAL_SQLITE_RELAY", "false").lower() in TRUTHY


def validate_startup_config() -> None:
    if relay_enabled_from_env() and not db.database_url():
        if allow_local_sqlite_relay():
            log.warning(RELAY_LOCAL_SQLITE_WARNING)
            return
        raise SystemExit(RELAY_DATABASE_URL_ERROR)


async def prefix_for(bot, message):
    if not message.guild:
        return commands.when_mentioned_or(DEFAULT_PREFIX)(bot, message)
    async with db.get() as conn:
        cur = await conn.execute("SELECT prefix FROM guild_config WHERE guild_id=?", (message.guild.id,))
        row = await cur.fetchone()
    p = row[0] if row else DEFAULT_PREFIX
    return commands.when_mentioned_or(p)(bot, message)


def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True
    intents.typing = False
    return intents


def log_intent_requirements(intents: discord.Intents) -> None:
    needed = []
    if intents.members:
        needed.append("GUILD_MEMBERS")
    if intents.message_content:
        needed.append("MESSAGE_CONTENT")
    if needed:
        log.info(
            "Privileged intents in use: %s. Ensure they are enabled for the app in the Discord Developer Portal.",
            ", ".join(needed),
        )


def discover_cog_names() -> list[str]:
    try:
        import cogs

        manifest = getattr(cogs, "COG_MODULES", None)
        if manifest:
            return sorted(str(name) for name in manifest)

        names = [module.name for module in pkgutil.iter_modules(cogs.__path__)]
        if names:
            return sorted(names)
    except Exception:
        pass
    cogs_dir = Path(__file__).parent / "cogs"
    return sorted(path.stem for path in cogs_dir.glob("*.py"))


class LokiBot(commands.Bot):
    def __init__(self):
        intents = build_intents()
        log_intent_requirements(intents)
        self._worker_lease = None
        self._worker_lease_task = None
        super().__init__(
            command_prefix=prefix_for,
            intents=intents,
            owner_id=OWNER_ID or None,
            help_command=None,  # cogs/help_v2.py provides /help with autocomplete
        )

    async def setup_hook(self):
        validate_startup_config()
        await db.init()
        try:
            self._worker_lease = await worker_singleton.claim_worker_lease(replace_existing=True)
        except worker_singleton.DuplicateWorkerError as exc:
            raise SystemExit(str(exc)) from exc
        worker_singleton.set_active_worker_lease(self._worker_lease)
        self._worker_lease_task = asyncio.create_task(worker_singleton.maintain_worker_lease(self._worker_lease))
        install_outbound_post_guard()
        for cog_name in self._iter_cog_names():
            if cog_name.startswith("_"):
                continue
            try:
                await self.load_extension(f"cogs.{cog_name}")
                log.info(f"Loaded cog: {cog_name}")
            except Exception as e:
                log.exception(f"Failed to load {cog_name}: {e}")
        apply_descriptions_to_bot(self)
        try:
            test_guild_id = os.getenv("TEST_GUILD_ID")
            if test_guild_id and test_guild_id.isdigit():
                guild = discord.Object(id=int(test_guild_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} slash commands to guild {test_guild_id} (instant)")
            else:
                synced = await self.tree.sync()
                log.info(f"Synced {len(synced)} slash commands globally (~1h propagation)")
        except Exception as e:
            log.warning(f"Slash sync failed: {e}")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} ({self.user.id})")
        await self.change_presence(activity=discord.Game(name=f"{DEFAULT_PREFIX}help | LOKI THE SUN GOD"))

    def _iter_cog_names(self) -> list[str]:
        return discover_cog_names()

    async def close(self):
        task = self._worker_lease_task
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self._worker_lease_task = None
        lease = self._worker_lease
        if lease is not None:
            with contextlib.suppress(Exception):
                await worker_singleton.release_worker_lease(lease)
            worker_singleton.clear_active_worker_lease(lease)
            self._worker_lease = None
        await super().close()


async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN missing in .env")
    validate_startup_config()
    killed = worker_singleton.stop_local_duplicate_workers(Path(__file__).resolve().parent)
    if killed:
        log.warning(
            "Stopped duplicate local LOKI THE SUN GOD worker process(es): %s",
            ", ".join(str(pid) for pid in killed),
        )
    bot = LokiBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
