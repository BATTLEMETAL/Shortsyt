import pytest
from lol_agent.lol_metadata_generator import generate_channel_title, generate_metadata

def test_fallback_triple_kill_titles_no_defensive_assumptions():
    """Verify that generated fallback titles for triple kills don't assume false enemy jumps."""
    for _ in range(10):
        title = generate_channel_title(action_type="triple", champion="Katarina")
        assert "they tried to jump" not in title.lower()
        assert "they cornered" not in title.lower()
        assert "dive" not in title.lower()
        assert "katarina" in title.lower() or "triple" in title.lower()

def test_fallback_outplay_titles_no_dive():
    """Verify fallback outplay titles do not hallucinate tower dives."""
    for _ in range(10):
        title = generate_channel_title(action_type="outplay", champion="Katarina")
        assert "dive" not in title.lower()

def test_metadata_chase_context():
    """Verify metadata generator accepts and reflects aggressive pursuit."""
    meta = generate_metadata(
        action_type="triple",
        champion_name="Katarina",
        rank="Diamond",
        extra_context={
            "combat_narrative": "Offensive pursuit: Chasing down and hunting enemies across the map. NOT defending a tower dive.",
            "combat_style": "Relentless Triple Kill Chase & Rampage",
            "kill_count": 3
        }
    )
    title = meta.get("title", "")
    assert len(title) > 10
    assert "dive" not in title.lower()


def test_generate_channel_title_ab_variants_differ_and_enforce_hashtags():
    """Verify that Variant A and Variant B generate different titles and both enforce hashtags."""
    title_a = generate_channel_title(action_type="solo_bolo", champion="Zed", variant="A")
    title_b = generate_channel_title(action_type="solo_bolo", champion="Zed", variant="B", exclude_title=title_a)
    assert title_a != title_b
    assert "#shorts" in title_a.lower()
    assert "#leagueoflegends" in title_a.lower()
    assert "#lol" in title_a.lower()
    assert "#shorts" in title_b.lower()
    assert "#leagueoflegends" in title_b.lower()
    assert "#lol" in title_b.lower()


def test_generate_metadata_includes_title_variants():
    """Verify generate_metadata outputs both primary title and title_variant_b."""
    meta = generate_metadata(
        action_type="outplay",
        champion_name="Akali",
        rank="Master"
    )
    assert "title" in meta
    assert "title_variant_b" in meta
    assert "title_variants" in meta
    assert len(meta["title_variants"]) == 2
    assert meta["title"] == meta["title_variants"][0]
    assert meta["title_variant_b"] == meta["title_variants"][1]
    assert "#shorts" in meta["title_variant_b"].lower()


def test_channel_title_no_banned_cliches_and_high_diversity():
    """Verify generated titles eliminate overused tropes, rank prefixes, and have high diversity."""
    banned = ["bad idea", "hunting grounds", "massacre", "reset machine", "mistake", "regret"]
    actions = ["solo_bolo", "outplay", "triple", "double", "pentakill"]

    for act in actions:
        generated = []
        for _ in range(15):
            t = generate_channel_title(action_type=act, champion="Katarina", map_zone_label="River")
            t_lower = t.lower()
            for b in banned:
                assert b not in t_lower, f"Found banned trope '{b}' in title: {t}"
            assert not t_lower.startswith("master "), f"Found rank prefix in title: {t}"
            assert not t_lower.startswith("diamond "), f"Found rank prefix in title: {t}"
            generated.append(t)

        # Diversity check: at least 4 unique titles out of 15, and river is not 100% forced
        unique_titles = set(generated)
        assert len(unique_titles) >= 4, f"Low diversity for {act}: {len(unique_titles)} unique out of 15"
        river_count = sum(1 for t in generated if "river" in t.lower())
        assert river_count < 15, f"Map zone overwhelmed all choices for {act} (15/15 had river)"

