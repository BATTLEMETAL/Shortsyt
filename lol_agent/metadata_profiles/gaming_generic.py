"""
Shortsyt — Generic Gaming Metadata Profile
Neutralne szablony tytułów/opisów do dowolnej gry (Valorant, CS2, Fortnite, itp.).
"""
import random

GAMING_TITLE_TEMPLATES = {
    'pentakill': [
        'This is INSANE. Five Eliminations in Seconds! 💥 #Shorts #Gaming',
        'Nobody Survived. ACE! 💀 #Shorts #Gaming',
        'They Had No Chance! 🔥 5 Kills in 5 Seconds #Shorts #Gaming',
        '1 vs Everyone. Somehow Won. 😈 #Shorts #Gaming',
    ],
    'quadrakill': [
        '4 Kills in One Fight!? 💥 How is This Real #Shorts #Gaming',
        'They Rushed in 4v1... Wrong Idea 💀 #Shorts #Gaming',
        'Absolutely DELETED Them! ⚡ 4K Outplay #Shorts #Gaming',
    ],
    'triple': [
        'Triple Kill! They Never Saw It Coming 😈 #Shorts #Gaming',
        'Turned the Fight Around Instantly! 💥 Triple #Shorts #Gaming',
        'Wait until you see the end... 😱 #Shorts #Gaming',
        '3v1 Clutch Nobody Expected 🔥 #Shorts #Gaming',
    ],
    'double': [
        'The Disrespect on That Double Kill 💀 #Shorts #Gaming',
        'They Tried to Bait Me. Got Doubled Instead. 😈 #Shorts #Gaming',
        'Fast Double Kill Outplay ⚡ #Shorts #Gaming',
    ],
    'clutch': [
        '1% HP Clutch Nobody Believed In 💀 #Shorts #Gaming',
        'How Was That Even Possible?! 😱 Clutch Win #Shorts #Gaming',
        'They Had the Win. Then This Happened. 😈 #Shorts #Gaming',
    ],
    'outplay': [
        'They Thought They Had Me... 😏 #Shorts #Gaming',
        'The Most Disrespectful Outplay Today 💀 #Shorts #Gaming',
        'Enemy Got Outplayed So Hard They Logged Off 💀 #Shorts #Gaming',
        'Nobody Talks About This Strategy 🧠 #Shorts #Gaming',
    ],
}

GAMING_BASE_TAGS = [
    'gaming', 'gaming highlights', 'gaming clips', 'gaming shorts',
    'best plays', 'outplay', 'clutch', 'gaming montage', 'shorts'
]

def generate_title(action_type: str, subject_name: str = '', rank: str = '') -> str:
    act = action_type.lower().replace(' ', '_')
    templates = GAMING_TITLE_TEMPLATES.get(act, GAMING_TITLE_TEMPLATES['outplay'])
    title = random.choice(templates)
    return title

def generate_description(title: str, game_name: str = 'Gaming', action_type: str = 'outplay') -> str:
    act_clean = action_type.replace('_', ' ').title()
    return (
        f'Insane {act_clean} play! 🎮🔥\n'
        f'They thought they had the fight won... Instant regret.\n\n'
        f'🎮 Best {game_name} clips and highlights\n'
        f'⚡ New viral shorts every day!\n\n'
        f'👍 Like if you enjoyed the outplay!\n'
        f'🔔 Subscribe for daily highlights!\n'
        f'💬 Rate this play 1-10! 👇\n\n'
        f'#Shorts #Gaming #{game_name.replace(" ","")}'
    )

def generate_pinned_comment(subject_name: str = '', action_type: str = 'outplay') -> str:
    comments = [
        'What would you have done differently? Rate this play 1-10! 👇🔥',
        'Could you have survived that? Let me know! 🧠👇',
        'Drop a comment if this was CLEAN 🔥👇',
        'What\'s your main? Comment below! ⚔️👇',
    ]
    return random.choice(comments)

def generate_metadata(
    action_type: str,
    subject_name: str = '',
    rank: str = '',
    extra_context: dict = None
) -> dict:
    extra_context = extra_context or {}
    game_name = extra_context.get('game_name', 'Gaming')
    title = generate_title(action_type, subject_name, rank)
    desc = generate_description(title, game_name, action_type)
    comment = generate_pinned_comment(subject_name, action_type)
    tags = list(dict.fromkeys([
        game_name.lower(), action_type.lower(), 'gaming', 'shorts'
    ] + GAMING_BASE_TAGS))[:30]
    return {
        'title': title,
        'description': desc,
        'pinned_comment': comment,
        'tags': tags,
        'hook_text': action_type.upper().replace('_', ' ') + '! 💥',
        'action_type': action_type,
        'subject_name': subject_name,
    }
