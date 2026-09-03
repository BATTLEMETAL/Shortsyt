"""
Shortsyt — Metadata Profiles Router
Automatycznie wybiera odpowiedni generator metadanych na podstawie game_type.
"""
import importlib
import random

PROFILE_MAP = {
    'lol': 'lol_agent.metadata_profiles.lol',
    'valorant': 'lol_agent.metadata_profiles.gaming_generic',
    'fortnite': 'lol_agent.metadata_profiles.gaming_generic',
    'cs2': 'lol_agent.metadata_profiles.gaming_generic',
    'generic': 'lol_agent.metadata_profiles.gaming_generic',
    'product_ad': 'lol_agent.metadata_profiles.product_ad',
}


def get_metadata_profile(game_type: str = 'lol'):
    """Zwraca modul profilu metadanych dla danego game_type."""
    mod_path = PROFILE_MAP.get(game_type, 'lol_agent.metadata_profiles.gaming_generic')
    try:
        return importlib.import_module(mod_path)
    except ImportError:
        try:
            short = mod_path.replace('lol_agent.', '')
            return importlib.import_module(short)
        except ImportError:
            import lol_agent.metadata_profiles.gaming_generic as fallback
            return fallback


def generate_metadata_for_game(
    game_type: str,
    action_type: str,
    subject_name: str = '',
    rank: str = '',
    extra_context: dict = None
) -> dict:
    """
    Glowny entry point — generuje metadane dla dowolnego game_type.
    Zwraca dict: {title, description, pinned_comment, tags, hook_text, action_type, subject_name}
    """
    extra_context = extra_context or {}
    profile = get_metadata_profile(game_type)
    return profile.generate_metadata(
        action_type=action_type,
        subject_name=subject_name,
        rank=rank,
        extra_context=extra_context
    )
