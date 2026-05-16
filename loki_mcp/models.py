from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class EmptyArgs(BaseModel):
    pass


class GuildQuery(BaseModel):
    guild_id: int = Field(..., ge=1, description="Discord guild ID stored in LOKI THE SUN GOD's local database.")


class CommandSearchQuery(BaseModel):
    query: str = Field(default="", description="Free-text search query for command names, descriptions, or options.")
    category: str = Field(default="", description="Optional command category filter, such as Automod or Tickets.")
    slash_only: bool = Field(default=False, description="Limit results to slash-capable commands.")


class DocSearchQuery(BaseModel):
    query: str = Field(..., min_length=1, description="Free-text query for the AI/operator documentation library.")
    include_content: bool = Field(default=False, description="Include full document content in results.")


class LegacyLibrarySearchQuery(BaseModel):
    query: str = Field(default="", description="Free-text query for external legacy libraries, such as Ralph Wiggum.")
    include_content: bool = Field(default=False, description="Include the full extracted legacy index in results.")


class MemorySearchQuery(BaseModel):
    guild_id: int = Field(..., ge=1, description="Discord guild ID for public NPC memory lookup.")
    query: str = Field(default="", description="Optional free-text search over redacted public memory snippets.")
    user_id: Optional[int] = Field(default=None, ge=1, description="Optional Discord member ID filter.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum redacted memory snippets to return.")


class MemoryUserPreviewQuery(BaseModel):
    guild_id: int = Field(..., ge=1, description="Discord guild ID for the memory preview.")
    user_id: int = Field(..., ge=1, description="Discord member ID for the preview.")
    limit: int = Field(default=20, ge=1, le=50, description="Maximum redacted memory snippets to include.")


class CamelotExportQuery(BaseModel):
    entity_type: str = Field(
        default="",
        description="Optional Camelot entity type filter, such as user, bot, concept, or plugin.",
    )
    status: str = Field(
        default="",
        description="Optional Camelot status filter: new, reviewed, active, deprecated, blocked, or complete.",
    )
    limit: int = Field(default=50, ge=1, le=50, description="Maximum Camelot records to export.")


class StickyDeleteInput(BaseModel):
    guild_id: int = Field(..., ge=1, description="Guild that owns the sticky entry.")
    channel_id: int = Field(..., ge=1, description="Channel ID for the sticky entry to remove.")


class AutomodInput(BaseModel):
    anti_invite: bool = False
    anti_spam: bool = False
    anti_caps: bool = False
    anti_mention: bool = False
    bad_words: str = ""
    max_mentions: int = Field(default=5, ge=0)
    spam_threshold: int = Field(default=5, ge=0)
    caps_percent: int = Field(default=70, ge=0)


class GuildConfigWriteInput(BaseModel):
    guild_id: int = Field(..., ge=1, description="Guild ID to update.")
    prefix: str = Field(default="!", max_length=10)
    log_channel: Optional[int] = Field(default=None, ge=1)
    welcome_channel: Optional[int] = Field(default=None, ge=1)
    starboard_channel: Optional[int] = Field(default=None, ge=1)
    star_threshold: int = Field(default=3, ge=0)
    level_enabled: bool = True
    automod: AutomodInput = Field(default_factory=AutomodInput)


class GuildListResult(BaseModel):
    guilds: list[dict[str, Any]]
    total: int


class GuildConfigResult(BaseModel):
    guild_id: int
    snapshot: dict[str, Any]


class ChannelClusterResult(BaseModel):
    guild_id: int
    clusters: list[dict[str, Any]]
    total: int
    live: bool
    error: Optional[str] = None


class CommandSearchResult(BaseModel):
    commands: list[dict[str, Any]]
    total: int


class DocSearchResult(BaseModel):
    docs: list[dict[str, Any]]
    total: int


class LegacyLibrarySearchResult(BaseModel):
    libraries: list[dict[str, Any]]
    total: int


class DiagnosticsResult(BaseModel):
    diagnostics: dict[str, Any]


class OllamaStatusResult(BaseModel):
    status: dict[str, Any]


class MusicStateResult(BaseModel):
    state: dict[str, Any]


class NpcSummaryResult(BaseModel):
    summary: dict[str, Any]


class ActivityStateResult(BaseModel):
    state: dict[str, Any]


class MythosSummaryResult(BaseModel):
    summary: dict[str, Any]


class MemorySearchResult(BaseModel):
    guild_id: int
    query: str
    user_id: Optional[int] = None
    entries: list[dict[str, Any]]
    total: int
    redacted: bool
    source_url_included: bool


class MemoryExportPreviewResult(BaseModel):
    guild_id: int
    user_id: int
    entry_count: int
    entries: list[dict[str, Any]]
    redacted: bool
    source_url_included: bool
    audit_receipt_created: bool


class MemoryDeletePreviewResult(BaseModel):
    guild_id: int
    user_id: int
    would_delete_count: int
    oldest_at: Optional[int] = None
    newest_at: Optional[int] = None
    deleted: bool
    audit_receipt_created: bool


class CamelotExportResult(BaseModel):
    schema_path: str
    record_count: int
    records: list[dict[str, Any]]


class MutationResult(BaseModel):
    ok: bool
    message: str
    snapshot: Optional[dict[str, Any]] = None
    deleted: int = 0
