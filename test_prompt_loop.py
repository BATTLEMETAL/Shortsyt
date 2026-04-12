import os
import json
from data_collector import search_viral_shorts
from agent_dark_psychology import get_forbidden_topics, CHANNELS_NICHES, NICHE_BASE, PROFILE_NAME, generate_viral_script

# Mock youtube object (since we don't need real uploads, search_viral_shorts can handle None or just return empty)
viral_context = ""
search_topic = NICHE_BASE
forbidden_topics = get_forbidden_topics(PROFILE_NAME)

niche_rule = """CREATE A VIRAL PSYCHOLOGY YOUTUBE SHORT (50-70 WORDS)

CRITICAL VIRAL RULES (MERGED WITH PREVIOUS OPTIMIZATIONS):
1. EXTREME NOVELTY: You MUST select a rare, highly obscure psychological trick, bias, or social dynamic. DO NOT repeat common facts. It must be unique and different from the listed forbidden topics.
2. ACCOUNT SAFETY (LOOPHOLE): Frame ALL manipulation or dark psychology tactics as "Defense against manipulation". Example: "Watch out for people who use this on you..." instead of "Here is how to manipulate". This is critical to avoid bans.
3. POTENT HOOK (First 3s): MUST contain elements of "forbidden knowledge" or explicitly tell the user to "Save this video before it's deleted".
4. SCRIPT STRUCTURE (15-30s lengths): Hook -> Value 1 -> Value 2 -> CTA/Loop. Every single word counts. Pack it with 'meat'.
5. ALGORITHM PSYCHOLOGY & LOOPING: The last word MUST connect seamlessly into the first word of your script to create a Perfect Loop.
6. VISUAL DIRECTIVE (For AI): Aim for a visual background description like "Peaky Blinders, American Psycho, mysterious figure in suit, wolves, dark city at night, dark red/navy colors".

EXAMPLE SCRIPT STRUCTURE (Use this exact format in ENGLISH):
[TITLE]
The most toxic manipulation technique narcissists use. (Save this) 🧠
[SCRIPT]
Save this video before they take it down. Here is how to spot if someone is secretly trying to control you. When someone tries to dominate you, maintain absolute silence and stare directly at the center of their forehead for four seconds. This will completely destroy their confidence, forcing them into submission. Want to learn more ways to defend yourself? Watch this video and...
[TAGS]
darkpsychology, manipulation, psychology, mindset, viral"""

print("=== TEST GENERACJI (3 LOOPY) ===")
print("PROMPT:")
print(niche_rule[:150] + "...\n")

for i in range(3):
    print(f"\n--- PRÓBA {i+1} ---")
    result = generate_viral_script(viral_context, search_topic, niche_rule, forbidden_topics)
    if not result or 'error' in result:
        print("BŁĄD:", result)
        continue
    
    script = result.get('script_text', '')
    word_count = len(script.split())
    
    print(f"TYTUŁ: {result.get('title')}")
    print(f"SKRYPT ({word_count} słów):")
    print(script)
    print("-" * 40)
