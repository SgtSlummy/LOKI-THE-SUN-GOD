from __future__ import annotations

import unittest

from utils.link_previews import (
    LinkPreview,
    extract_music_artists,
    extract_urls,
    is_safe_preview_url,
    parse_html_preview,
    strip_urls,
)


class LinkPreviewTextTests(unittest.TestCase):
    def test_extracts_urls_and_trims_sentence_punctuation(self):
        text = "Listen: https://open.spotify.com/track/abc?si=123. Also see <https://example.com/a(b)>!"

        self.assertEqual(
            extract_urls(text),
            [
                "https://open.spotify.com/track/abc?si=123",
                "https://example.com/a(b)",
            ],
        )

    def test_strips_url_only_message_to_empty_text(self):
        self.assertEqual(strip_urls("https://store.steampowered.com/app/3124540/?snr=1_5_9__205"), "")

    def test_strips_multiple_urls_while_preserving_words(self):
        text = "Play this https://example.com/one and this\nhttps://example.com/two, please"

        self.assertEqual(strip_urls(text), "Play this and this please")

    def test_strips_angle_wrapped_url_without_leaving_brackets(self):
        self.assertEqual(strip_urls("look <https://example.com/photo.jpg> now"), "look now")


class LinkPreviewMusicTests(unittest.TestCase):
    def test_extracts_spotify_artist_from_track_metadata(self):
        preview = LinkPreview(
            url="https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b",
            title="Blinding Lights",
            description="The Weeknd · After Hours · Song · 2020",
            site_name="Spotify",
        )

        self.assertEqual(extract_music_artists(preview), "The Weeknd")

    def test_keeps_simple_spotify_description_as_artist(self):
        preview = LinkPreview(
            url="https://open.spotify.com/track/abc",
            title="Battles",
            description="Alpine Universe",
            site_name="Spotify",
        )

        self.assertEqual(extract_music_artists(preview), "Alpine Universe")

    def test_ignores_non_music_preview_descriptions(self):
        preview = LinkPreview(
            url="https://example.com/news",
            title="News",
            description="A normal page description",
            site_name="Example",
        )

        self.assertEqual(extract_music_artists(preview), "")


class LinkPreviewHtmlTests(unittest.TestCase):
    def test_parses_open_graph_and_twitter_metadata(self):
        html = """
        <html><head>
          <meta property="og:title" content="Far Far West">
          <meta name="twitter:description" content="A dusty co-op game.">
          <meta property="og:image" content="/capsule.jpg">
          <meta property="og:site_name" content="Steam">
        </head></html>
        """

        preview = parse_html_preview("https://store.steampowered.com/app/3124540/", html)

        self.assertEqual(
            preview,
            LinkPreview(
                url="https://store.steampowered.com/app/3124540/",
                title="Far Far West",
                description="A dusty co-op game.",
                image_url="https://store.steampowered.com/capsule.jpg",
                site_name="Steam",
            ),
        )

    def test_uses_html_title_when_social_metadata_is_missing(self):
        html = "<html><head><title>Example Page</title></head><body></body></html>"

        preview = parse_html_preview("https://example.com/posts/1", html)

        self.assertEqual(preview.title, "Example Page")
        self.assertEqual(preview.description, "")
        self.assertIsNone(preview.image_url)

    def test_login_wall_without_image_is_not_returned_as_preview(self):
        html = """
        <html><head>
          <meta property="og:title" content="Log in or sign up to view">
          <meta property="og:description" content="See posts, photos and more on Facebook.">
        </head></html>
        """

        self.assertIsNone(parse_html_preview("https://www.facebook.com/share/r/example", html))


class LinkPreviewSafetyTests(unittest.TestCase):
    def test_rejects_private_loopback_and_link_local_urls(self):
        blocked = [
            "http://127.0.0.1:5000/healthz",
            "http://localhost/admin",
            "http://10.0.0.5/secret",
            "http://172.16.0.1/secret",
            "http://192.168.1.1/router",
            "http://169.254.169.254/latest/meta-data",
            "http://0.0.0.0/admin",
            "http://[::]/admin",
            "http://[::1]/admin",
            "http://[fe80::1]/metadata",
            "file:///etc/passwd",
        ]

        for url in blocked:
            with self.subTest(url=url):
                self.assertFalse(is_safe_preview_url(url))

    def test_allows_public_http_and_https_urls(self):
        self.assertTrue(is_safe_preview_url("https://open.spotify.com/track/abc"))
        self.assertTrue(is_safe_preview_url("http://example.com/image.jpg"))


if __name__ == "__main__":
    unittest.main()
