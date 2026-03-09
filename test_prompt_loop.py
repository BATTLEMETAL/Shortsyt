import os
import json
from data_collector import search_viral_shorts
from agent_dark_psychology import get_forbidden_topics, CHANNELS_NICHES, NICHE_BASE, PROFILE_NAME, generate_viral_script

# Mock youtube object (since we don't need real uploads, search_viral_shorts can handle None or just return empty)
viral_context = ""
search_topic = NICHE_BASE
forbidden_topics = get_forbidden_topics(PROFILE_NAME)

niche_rule = """CREATE A VIRAL PSYCHOLOGY YOUTUBE SHORT (40-70 WORDS)

CRITICAL RULES:
1. STRONG HOOK (First 2 seconds): Start with a direct question or a powerful, shocking statement directed at the viewer to grab attention instantly.
2. NATURAL TITLE: The [TITLE] MUST be a natural, intriguing question or strong statement. ABSOLUTELY NO keyword stuffing (do not use "secrets facts manipulation").
3. STORYTELLING & FACTS: Blend historical facts or storytelling with practical psychology lessons.
4. CALL TO ACTION (COMMENTS): Ask the viewers a specific question to drive comments right before the loop. (e.g., "Have you experienced this? Tell me in the comments.").
5. YOU MUST USE A PERFECT LOOP: The last word of your script MUST connect seamlessly into the first word of your script.
6. NEVER use the word 'forehead'. Choose a completely fresh, NEW concept each time.

EXAMPLE SCRIPT STRUCTURE (Follow this exact style):
[TITLE]
Have you ever fallen for the Benjamin Franklin effect? 🧠
[SCRIPT]
Have you ever fallen for the Benjamin Franklin effect? It's a dark truth about making people like you. Instead of doing favors for them, ask them to do a small favor for you. Their brain will subconsciously convince them they like you. Has this ever worked on you? Tell me in the comments if you...
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
