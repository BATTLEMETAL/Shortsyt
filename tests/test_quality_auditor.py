"""
tests/test_quality_auditor.py
===============================
Unit tests for Shortsyt quality_auditor.py.
These tests cover the core scoring functions without any external dependencies
(no GPU, no API keys, no network).

Run with:
    pytest tests/test_quality_auditor.py -v
"""
import sys
import os

# Allow importing from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quality_auditor import score_title, score_script, BANNED_TITLE_PREFIXES


# ─── score_title tests ────────────────────────────────────────────────────────

class TestScoreTitle:
    def test_bracket_prefix_gets_heavy_penalty(self):
        """Titles starting with [Bracket] should get -20 penalty."""
        score, notes = score_title("[Nero's] dark psychology trick 🧠 #shorts")
        assert score < 0, f"Expected negative score for bracket prefix, got {score}"
        assert any("PREFIX_BRACKET" in n for n in notes)

    def test_question_format_gets_bonus(self):
        """Titles starting with question word should score higher than statements."""
        score_q, _ = score_title("Have you ever felt someone draining your energy? 🧠 #shorts")
        score_s, _ = score_title("People draining your energy explained")
        assert score_q > score_s, "Question format should score higher than plain statement"

    def test_banned_word_reduces_score(self):
        """Title containing a banned word should score lower than clean title."""
        score_banned, notes = score_title("The secret revealed about dark psychology")
        score_clean, _ = score_title("Can you spot the manipulation tactic? 🧠 #shorts")
        assert score_banned < score_clean
        assert any("revealed" in n for n in notes)

    def test_proven_keywords_give_bonus(self):
        """Title with known high-performing keywords should earn keyword bonus."""
        score, notes = score_title("How to command respect effortlessly 🧠 #shorts")
        assert any("Sprawdzone słowa" in n for n in notes)

    def test_emoji_gives_bonus(self):
        """Title with emoji should score higher than identical title without emoji."""
        score_with, _ = score_title("Can you spot manipulation? 🧠 #shorts")
        score_without, _ = score_title("Can you spot manipulation? #shorts")
        assert score_with > score_without


# ─── score_script tests ───────────────────────────────────────────────────────

class TestScoreScript:
    GOOD_SCRIPT = (
        "Most people don't know this. "
        "Have you ever noticed how some people command respect without saying a word? "
        "Research by Paul Ekman shows 93% of communication is nonverbal. "
        "They use tactical mirroring — matching posture and pace subconsciously. "
        "But here's what nobody tells you — "
        "this works both ways. They might be doing it to you right now. "
        "Follow for more dark psychology tactics."
    )

    def test_good_script_is_approved(self):
        """A well-structured script should score ≥ 20 points (passing zone)."""
        score, notes = score_script(self.GOOD_SCRIPT)
        assert score >= 20, f"Expected good script to score ≥20, got {score}. Notes: {notes}"

    def test_empty_script_scores_zero(self):
        """Empty script should score 0 — no structure detected."""
        score, notes = score_script("")
        assert score == 0

    def test_script_without_prehook_scores_lower(self):
        """Script missing PRE-HOOK should score lower than one with it."""
        no_hook = (
            "Dark psychology is fascinating. "
            "People use manipulation every day without you knowing. "
            "But here's what nobody tells you — "
            "you can reverse it. "
            "Follow for more."
        )
        score_good, _ = score_script(self.GOOD_SCRIPT)
        score_no_hook, _ = score_script(no_hook)
        assert score_good > score_no_hook

    def test_script_without_cta_loses_points(self):
        """Script missing CTA should score lower than script with CTA."""
        no_cta = (
            "Most people don't know this. "
            "Have you noticed how some people command respect? "
            "It's called tactical mirroring. "
            "But here's what nobody tells you — "
            "this works on everyone."
        )
        score_good, _ = score_script(self.GOOD_SCRIPT)
        score_no_cta, _ = score_script(no_cta)
        assert score_good >= score_no_cta

    def test_very_short_script_penalised(self):
        """Scripts under 25 words should not receive the length bonus."""
        short = "Dark psychology is powerful. Use it wisely. Follow for more."
        score, notes = score_script(short)
        assert not any("+10" in n or "+6" in n for n in notes), \
            "Short script should not receive length bonus"
