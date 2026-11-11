"""
Tests for multi_platform_copywriter.py
Verifies per-platform copy generation: structure, length constraints, fallback paths.
All tests must pass without network access (Gemini mocked).
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Ensure lol_agent is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lol_agent.multi_platform_copywriter import (
    generate_youtube_copy,
    generate_tiktok_copy,
    generate_instagram_copy,
    generate_facebook_copy,
    generate_all_platform_copy,
    _yt_hashtags,
    _tiktok_hashtags,
    _instagram_hashtags,
    _facebook_hashtags,
)


@pytest.fixture(autouse=True)
def disable_gemini(monkeypatch):
    monkeypatch.setattr('lol_agent.multi_platform_copywriter.GENAI_OK', False)


# ─── Hashtag helpers ──────────────────────────────────────────────────────────

class TestHashtagHelpers:
    def test_yt_hashtags_returns_list(self):
        tags = _yt_hashtags("Katarina", "pentakill")
        assert isinstance(tags, list)
        assert len(tags) >= 8

    def test_yt_hashtags_contains_champion(self):
        tags = _yt_hashtags("Jinx", "outplay")
        assert any("Jinx" in t or "jinx" in t.lower() for t in tags)

    def test_tiktok_hashtags_max_5(self):
        tags = _tiktok_hashtags("Zed", "outplay")
        assert len(tags) <= 5

    def test_tiktok_hashtags_no_hash_prefix(self):
        tags = _tiktok_hashtags("Zed", "outplay")
        for t in tags:
            assert not t.startswith("#"), f"Tag should not have # prefix: {t}"

    def test_instagram_hashtags_max_15(self):
        tags = _instagram_hashtags("Katarina", "pentakill")
        assert len(tags) <= 15

    def test_facebook_hashtags_max_3(self):
        tags = _facebook_hashtags("Jinx", "clutch")
        assert len(tags) <= 3

    def test_champion_name_sanitised(self):
        """Apostrophes and spaces stripped from champion name in tags."""
        tags = _yt_hashtags("Cho'Gath", "outplay")
        for t in tags:
            assert "'" not in t, f"Apostrophe in tag: {t}"

    def test_unknown_action_defaults_gracefully(self):
        tags = _tiktok_hashtags("Aatrox", "random_unknown_action")
        assert isinstance(tags, list)
        assert len(tags) > 0


# ─── YouTube copy ─────────────────────────────────────────────────────────────

class TestYouTubeCopy:
    def test_returns_required_keys(self):
        result = generate_youtube_copy("Katarina", "pentakill")
        for key in ("platform", "title", "caption", "hashtags", "description"):
            assert key in result, f"Missing key: {key}"

    def test_platform_field_correct(self):
        result = generate_youtube_copy("Katarina", "outplay")
        assert result["platform"] == "youtube"

    def test_title_max_100_chars(self):
        result = generate_youtube_copy("Katarina", "pentakill")
        assert len(result["title"]) <= 100

    def test_uses_base_metadata_title(self):
        base = {"title": "My Custom Title", "description": "desc", "tags": ["tag1"]}
        result = generate_youtube_copy("Katarina", "pentakill", base_metadata=base)
        assert result["title"] == "My Custom Title"

    def test_fallback_title_when_no_base_metadata(self):
        result = generate_youtube_copy("Jinx", "triple")
        assert len(result["title"]) > 0
        assert "Jinx" in result["title"] or "TRIPLE" in result["title"]

    def test_hashtags_not_empty(self):
        result = generate_youtube_copy("Katarina", "outplay")
        assert len(result["hashtags"]) > 0


# ─── TikTok copy ──────────────────────────────────────────────────────────────

class TestTikTokCopy:
    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_fallback_when_no_gemini(self):
        """Must produce valid copy even without Gemini."""
        result = generate_tiktok_copy("Katarina", "pentakill")
        assert result["title"]
        assert result["caption"]
        assert result["platform"] == "tiktok"

    def test_returns_required_keys(self):
        result = generate_tiktok_copy("Zed", "outplay")
        for key in ("platform", "title", "caption", "hashtags"):
            assert key in result

    def test_platform_field_correct(self):
        result = generate_tiktok_copy("Zed", "outplay")
        assert result["platform"] == "tiktok"

    def test_title_max_90_chars_without_gemini(self):
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_tiktok_copy("Katarina", "pentakill")
            assert len(result["title"]) <= 90

    def test_hashtags_max_5(self):
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_tiktok_copy("Katarina", "pentakill")
            assert len(result["hashtags"]) <= 5

    def test_caption_contains_hashtags(self):
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_tiktok_copy("Katarina", "outplay")
            assert "#" in result["caption"]

    @patch("lol_agent.multi_platform_copywriter._call_gemini")
    def test_uses_gemini_when_available(self, mock_gemini):
        mock_gemini.return_value = "This Katarina outplay is insane"
        result = generate_tiktok_copy("Katarina", "outplay")
        assert "Katarina" in result["title"] or "insane" in result["title"]


# ─── Instagram copy ───────────────────────────────────────────────────────────

class TestInstagramCopy:
    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_fallback_when_no_gemini(self):
        result = generate_instagram_copy("Jinx", "clutch")
        assert result["caption"]
        assert result["platform"] == "instagram"

    def test_returns_required_keys(self):
        result = generate_instagram_copy("Jinx", "triple")
        for key in ("platform", "title", "caption", "hashtags"):
            assert key in result

    def test_platform_field_correct(self):
        result = generate_instagram_copy("Jinx", "triple")
        assert result["platform"] == "instagram"

    def test_caption_contains_hashtags(self):
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_instagram_copy("Jinx", "triple")
            assert "#" in result["caption"]

    def test_title_max_80_chars(self):
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_instagram_copy("Katarina", "pentakill")
            assert len(result["title"]) <= 80

    def test_hashtags_max_15(self):
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_instagram_copy("Katarina", "pentakill")
            assert len(result["hashtags"]) <= 15

    def test_separator_dots_in_caption(self):
        """IG best practice: dot separators push hashtags below the fold."""
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_instagram_copy("Katarina", "outplay")
            assert ".\n.\n." in result["caption"]


# ─── Facebook copy ────────────────────────────────────────────────────────────

class TestFacebookCopy:
    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_fallback_when_no_gemini(self):
        result = generate_facebook_copy("Katarina", "outplay")
        assert result["caption"]
        assert result["platform"] == "facebook"

    def test_returns_required_keys(self):
        result = generate_facebook_copy("Katarina", "outplay")
        for key in ("platform", "title", "caption", "hashtags"):
            assert key in result

    def test_platform_field_correct(self):
        result = generate_facebook_copy("Katarina", "outplay")
        assert result["platform"] == "facebook"

    def test_hashtags_max_3(self):
        with patch("lol_agent.multi_platform_copywriter.GENAI_OK", False):
            result = generate_facebook_copy("Katarina", "outplay")
            assert len(result["hashtags"]) <= 3


# ─── generate_all_platform_copy ───────────────────────────────────────────────

class TestGenerateAll:
    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    @patch('lol_agent.multi_platform_copywriter.GENAI_OK', False)
    def test_default_platforms_returned(self):
        result = generate_all_platform_copy("Katarina", "pentakill")
        assert "youtube" in result
        assert "tiktok" in result
        assert "instagram" in result
        assert "facebook" not in result   # not in default set

    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_facebook_only_when_requested(self):
        result = generate_all_platform_copy(
            "Katarina", "outplay", platforms=["facebook"]
        )
        assert "facebook" in result
        assert "youtube" not in result
        assert "tiktok" not in result

    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_all_four_platforms(self):
        result = generate_all_platform_copy(
            "Jinx", "clutch",
            platforms=["youtube", "tiktok", "instagram", "facebook"]
        )
        assert len(result) == 4

    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_base_metadata_passed_to_yt(self):
        base = {"title": "Forced YT Title", "description": "d", "tags": []}
        result = generate_all_platform_copy(
            "Katarina", "pentakill",
            base_metadata=base,
            platforms=["youtube"],
        )
        assert result["youtube"]["title"] == "Forced YT Title"

    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_each_platform_has_different_copy(self):
        """TikTok and Instagram copy should not be identical."""
        result = generate_all_platform_copy(
            "Katarina", "outplay",
            platforms=["tiktok", "instagram"]
        )
        assert result["tiktok"]["caption"] != result["instagram"]["caption"]

    @patch("lol_agent.multi_platform_copywriter.GENAI_OK", False)
    def test_empty_platforms_list_returns_empty_dict(self):
        result = generate_all_platform_copy("Katarina", "outplay", platforms=[])
        assert result == {}
