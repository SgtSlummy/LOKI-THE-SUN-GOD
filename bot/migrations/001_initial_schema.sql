CREATE TABLE IF NOT EXISTS relay_routes (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    source_channel_id BIGINT NOT NULL,
    destination_channel_id BIGINT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('one_way', 'bidirectional')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_relay_routes_source
    ON relay_routes(guild_id, source_channel_id, enabled);

CREATE INDEX IF NOT EXISTS idx_relay_routes_destination
    ON relay_routes(guild_id, destination_channel_id, enabled);

CREATE TABLE IF NOT EXISTS relay_message_map (
    id BIGSERIAL PRIMARY KEY,
    source_message_id BIGINT NOT NULL,
    source_channel_id BIGINT NOT NULL,
    destination_message_id BIGINT NOT NULL,
    destination_channel_id BIGINT NOT NULL,
    route_id BIGINT NOT NULL REFERENCES relay_routes(id),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(source_message_id, source_channel_id, route_id),
    UNIQUE(destination_message_id, destination_channel_id)
);

CREATE TABLE IF NOT EXISTS media_cache (
    id BIGSERIAL PRIMARY KEY,
    original_url_hash TEXT NOT NULL UNIQUE,
    provider TEXT,
    title TEXT,
    thumbnail_url TEXT,
    media_type TEXT,
    resolved_payload_json JSONB NOT NULL,
    expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_id BIGINT,
    guild_id BIGINT,
    channel_id BIGINT,
    message_id BIGINT,
    details_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS plugin_state (
    plugin_name TEXT PRIMARY KEY,
    slot TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    config_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS indexed_messages (
    message_id BIGINT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    author_id BIGINT,
    sanitized_text TEXT NOT NULL,
    media_metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL
);

