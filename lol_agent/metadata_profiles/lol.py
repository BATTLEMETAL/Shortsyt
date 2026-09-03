"""
Shortsyt — LoL Metadata Profile
Wrapper delegujacy do glownego lol_metadata_generator.py.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from lol_agent.lol_metadata_generator import (
        generate_metadata as _generate_metadata,
        generate_channel_title,
        build_channel_description,
        build_pinned_comment,
    )
except ImportError:
    from lol_metadata_generator import (
        generate_metadata as _generate_metadata,
        generate_channel_title,
        build_channel_description,
        build_pinned_comment,
    )


def generate_metadata(
    action_type: str,
    subject_name: str = 'Katarina',
    rank: str = 'Master',
    extra_context: dict = None
) -> dict:
    """
    LoL metadata profile — deleguje do lol_metadata_generator.
    subject_name = champion_name dla backward compat.
    """
    return _generate_metadata(
        action_type=action_type,
        champion_name=subject_name or 'Katarina',
        rank=rank or 'Master',
    )
