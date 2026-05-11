from __future__ import annotations

import unittest
from unittest.mock import patch

from cogs import highlights as highlights_module
from cogs.highlights import music_artists_for_message_content
from utils.link_previews import LinkPreview


class HighlightArtistTests(unittest.IsolatedAsyncioTestCase):
    async def test_music_artists_for_message_content_returns_spotify_artists(self):
        async def fake_resolve(_urls):
            return [
                LinkPreview(
                    url="https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b",
                    title="Blinding Lights",
                    description="The Weeknd · After Hours · Song · 2020",
                    site_name="Spotify",
                )
            ]

        with patch.object(highlights_module, "resolve_link_previews", fake_resolve):
            artists = await music_artists_for_message_content(
                "highlight this https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"
            )

        self.assertEqual(artists, "The Weeknd")

    async def test_music_artists_for_message_content_deduplicates_artists(self):
        async def fake_resolve(_urls):
            return [
                LinkPreview(
                    url="https://open.spotify.com/track/1",
                    title="Track 1",
                    description="The Weeknd · Album · Song · 2020",
                    site_name="Spotify",
                ),
                LinkPreview(
                    url="https://open.spotify.com/track/2",
                    title="Track 2",
                    description="the weeknd · Album · Song · 2021",
                    site_name="Spotify",
                ),
            ]

        with patch.object(highlights_module, "resolve_link_previews", fake_resolve):
            artists = await music_artists_for_message_content(
                "https://open.spotify.com/track/1 https://open.spotify.com/track/2"
            )

        self.assertEqual(artists, "The Weeknd")


if __name__ == "__main__":
    unittest.main()
