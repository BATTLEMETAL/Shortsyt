"""
Shortsyt — Product Advertisement Metadata Profile
Dark Psychology CTR hooks dla reklam i review produktów.
Maximum scroll-stop, curiosity gap, urgency.
"""
import random

AD_TITLE_HOOKS = {
    'reveal': [
        'Nobody Talks About This... 👀 #Shorts',
        'I Found Something CRAZY 😱 #Shorts',
        'Wait Until You See This 👀 #Shorts',
        'They Don\'t Want You to Know This 🤫 #Shorts',
        'This Changed Everything for Me 🔥 #Shorts',
    ],
    'review': [
        'Honest Review: Worth It or Not? 🤔 #Shorts',
        'I Tested It for 30 Days. Here\'s the Truth. #Shorts',
        'Everyone\'s Buying This. But Should You? 👀 #Shorts',
        'Best Purchase I Made This Year? 🔥 #Shorts',
        'The Review Nobody Wanted to Make 😳 #Shorts',
    ],
    'demo': [
        'Watch This Until the End 👀 #Shorts',
        'How Did I Not Know About This?! 😱 #Shorts',
        'Tried It So You Don\'t Have To 🔥 #Shorts',
        'POV: You Find Something Life-Changing 😮 #Shorts',
    ],
    'unboxing': [
        'Unboxing the Most Hyped Product Right Now 📦 #Shorts',
        'Is the Hype Real? Let\'s Find Out 🎁 #Shorts',
        'First Look: Everyone\'s Talking About This 😱 #Shorts',
    ],
    'cta': [
        'Link in Bio — Limited Time 🔥 #Shorts',
        'Get Yours Before It Sells Out 👀 #Shorts',
        'This Deal Won\'t Last Long 🚨 #Shorts',
    ],
}

AD_BASE_TAGS = [
    'shorts', 'viral', 'review', 'unboxing', 'product review',
    'must have', 'trending', 'recommendation', 'honest review'
]

def generate_title(action_type: str, subject_name: str = '', rank: str = '') -> str:
    act = action_type.lower().replace(' ', '_')
    templates = AD_TITLE_HOOKS.get(act, AD_TITLE_HOOKS['reveal'])
    title = random.choice(templates)
    if subject_name:
        if 'This' in title and len(subject_name) < 20:
            title = title.replace('This', subject_name, 1)
    return title

def generate_description(title: str, product_name: str = '', action_type: str = 'reveal') -> str:
    product_line = f'Product: {product_name}\n' if product_name else ''
    return (
        f'{title}\n\n'
        f'{product_line}'
        f'💡 Full review and details below!\n'
        f'🔔 Subscribe for honest reviews!\n'
        f'👍 Like if you found this helpful!\n'
        f'💬 Have you tried this? Let me know! 👇\n\n'
        f'#Shorts #Review #Viral'
    )

def generate_pinned_comment(subject_name: str = '', action_type: str = 'reveal') -> str:
    comments = [
        f'Have you tried {subject_name}? Drop your thoughts below! 👇' if subject_name else 'What do you think? Comment below! 👇',
        'Would you buy this? Yes or No? 👇',
        'Tag someone who needs to see this! 👇🔥',
        'Is this worth it? Let me know in the comments! 👇',
    ]
    return random.choice(comments)

def generate_metadata(
    action_type: str,
    subject_name: str = '',
    rank: str = '',
    extra_context: dict = None
) -> dict:
    extra_context = extra_context or {}
    product_name = subject_name or extra_context.get('product_name', '')
    title = generate_title(action_type, product_name, rank)
    desc = generate_description(title, product_name, action_type)
    comment = generate_pinned_comment(product_name, action_type)
    tags = list(dict.fromkeys([
        product_name.lower().replace(' ', '') if product_name else 'product',
        action_type.lower()
    ] + AD_BASE_TAGS))[:30]
    return {
        'title': title,
        'description': desc,
        'pinned_comment': comment,
        'tags': tags,
        'hook_text': 'WAIT FOR IT 👀',
        'action_type': action_type,
        'subject_name': product_name,
    }
