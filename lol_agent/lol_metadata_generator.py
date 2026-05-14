"""
LOL Agent — Generator metadanych YouTube (Gemini AI)
Tytuł, opis, tagi zoptymalizowane pod algorytm YT Gaming
"""
import os
import json
import random
import google.generativeai as genai
from lol_config import GEMINI_API_KEY, YT_BASE_TAGS, ACTION_LABELS


POPULAR_CHAMPIONS = [
    "Jinx", "Yasuo", "Zed", "Ahri", "Lee Sin", "Thresh", "Vayne",
    "Master Yi", "Katarina", "Lux", "Yone", "Viego", "Akali",
    "Ezreal", "Caitlyn", "Sylas", "Fizz", "Rengar", "Kha'Zix", "Irelia"
]

RANKS = ["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond", "Master", "Challenger"]


def generate_metadata(
    action_type: str,
    champion_name: str = "",
    rank: str = "",
    language: str = "pl"
) -> dict:
    """
    Generuje tytuł, opis i tagi dla Shorta LoL przez Gemini AI.
    Fallback na szablony jeśli API niedostępne.
    """
    action_label = ACTION_LABELS.get(action_type, "OUTPLAY").replace("🔥", "").replace("⚡", "").replace("💥", "").replace("🎯", "").replace("👑", "").strip()

    if not champion_name:
        champion_name = random.choice(POPULAR_CHAMPIONS)
    if not rank:
        rank = random.choice(["Gold", "Platinum", "Diamond"])

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = f"""Jesteś ekspertem od YouTube Shorts dla graczy League of Legends.
Wygeneruj metadane dla krótkiego wideo gamingowego.

KONTEKST:
- Typ akcji: {action_label}
- Champion: {champion_name}
- Ranga: {rank}
- Format: YouTube Short (9:16, < 60 sekund)
- Kanał: Dwannellenga (polsko-angielski gaming)

WYGENERUJ (w formacie JSON):
{{
  "title": "Chwytliwy tytuł po polsku lub angielsku, max 70 znaków, z emoji, SEO friendly",
  "description": "Opis 150-200 słów. Opisz akcję, zachęć do subskrypcji. Dodaj hashtagi na końcu.",
  "tags": ["lista", "15-20", "tagów", "gaming", "LoL", "specific"],
  "hook_text": "Krótki hook 3-5 słów do overlay na wideo (np. NIEMOŻLIWY OUTPLAY)"
}}

ZASADY:
- Tytuł musi być CLICKBAIT ale prawdziwy
- Użyj: {champion_name}, {action_label}, ranga {rank}
- Hashtagi: #LeagueOfLegends #LoL #Shorts #gaming
- Tagi po angielsku i polsku
- Hook po polsku LUB angielsku — max 4 słowa, CAPS"""

        response = model.generate_content(prompt)
        text = response.text.strip()

        # Wyciągnij JSON z odpowiedzi
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)

        # Dodaj bazowe tagi
        all_tags = data.get("tags", []) + YT_BASE_TAGS
        all_tags = list(dict.fromkeys(all_tags))[:30]  # Max 30, bez duplikatów

        result = {
            "title": data.get("title", generate_fallback_title(action_label, champion_name, rank)),
            "description": data.get("description", generate_fallback_description(action_label, champion_name)),
            "tags": all_tags,
            "hook_text": data.get("hook_text", action_label.upper()),
            "champion": champion_name,
            "rank": rank,
            "action_type": action_type,
        }

        print(f"✅ Metadane wygenerowane przez Gemini AI")
        print(f"   📌 Tytuł: {result['title']}")
        print(f"   🏷️  Tagi: {len(result['tags'])} tagów")
        return result

    except Exception as e:
        print(f"⚠️  Gemini API error: {e} — używam fallback")
        return generate_fallback_metadata(action_label, champion_name, rank, action_type)


def generate_fallback_title(action_label: str, champion: str, rank: str) -> str:
    templates = [
        f"NIESAMOWITY {action_label} {champion} w {rank}! 🔥 #Shorts",
        f"{champion} {action_label} - Nigdy tego nie zapomnisz! 😱 #LoL",
        f"Ten {action_label} był NIEMOŻLIWY... {champion} {rank} Gameplay 🎮",
        f"Jak? {action_label} na {champion} w {rank} 👑 #LeagueOfLegends",
        f"{action_label} roku! {champion} carry w {rank} 💥 #LoLShorts",
    ]
    return random.choice(templates)


def generate_fallback_description(action_label: str, champion: str) -> str:
    return f"""Niesamowity {action_label} na {champion}! 🎮

Oglądasz jeden z najlepszych momentów w League of Legends. Subskrybuj kanał Dwannellenga po więcej epic highlightów z LoL!

👍 Jeśli podobał Ci się ten klip — zostaw like!
🔔 Subskrybuj żeby nie przegapić więcej takich momentów!
💬 Napisz w komentarzu swój najlepszy moment!

#LeagueOfLegends #LoL #{champion.replace(" ", "")} #{action_label.replace(" ", "")} #Shorts #Gaming #LoLHighlights #BestPlays #Montage #Polski #LoLPL"""


def generate_fallback_metadata(action_label: str, champion: str, rank: str, action_type: str) -> dict:
    all_tags = [
        champion, champion.lower(), f"lol {champion.lower()}",
        action_label.lower(), action_type, rank.lower(),
        f"{rank.lower()} gameplay",
    ] + YT_BASE_TAGS
    all_tags = list(dict.fromkeys(all_tags))[:30]

    return {
        "title": generate_fallback_title(action_label, champion, rank),
        "description": generate_fallback_description(action_label, champion),
        "tags": all_tags,
        "hook_text": action_label.upper(),
        "champion": champion,
        "rank": rank,
        "action_type": action_type,
    }


if __name__ == "__main__":
    result = generate_metadata(
        action_type="pentakill",
        champion_name="Jinx",
        rank="Diamond"
    )
    print(f"\n📋 WYNIK:")
    print(f"Tytuł: {result['title']}")
    print(f"Hook: {result['hook_text']}")
    print(f"Tagi: {', '.join(result['tags'][:10])}...")
