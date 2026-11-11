#!/usr/bin/env python3
"""
FLIKCUT / SHORTSYT — SKRYPT DO RENDERÓW KONTROLNYCH (KROK 7 AGENTS.md)
Renderuje 5 klipów wzorcowych dla 5 archetypów:
1. SOLO_BOLO
2. OUTPLAY
3. TRIPLE KILL
4. DOUBLE KILL
5. CHAOTIC_TEAMFIGHT

Każdy wyrenderowany klip zapisywany jest w katalogu:
outputs/benchmark_new_engine/ (lub outputs/benchmark_old_engine/ w zależności od gałęzi)
W nowym silniku obok każdego pliku .mp4 powstanie <plik>.recipe.json.
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
LOL_AGENT_DIR = os.path.join(ROOT_DIR, "lol_agent")
if LOL_AGENT_DIR not in sys.path:
    sys.path.insert(0, LOL_AGENT_DIR)

from lol_agent.api.pipeline_runner import _run_pipeline, _state

BASE_CLIPS_DIR = r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_11-10-2026_23-18-24-742"

BENCHMARK_CLIPS = [
    {
        "id": "1_solo_bolo",
        "video": os.path.join(BASE_CLIPS_DIR, "League of Legends 11-10-2026 23-21-31-987_0.mp4"),
        "action": "solo_bolo",
        "champion": "Katarina",
        "rank": "Diamond",
        "hook": "SOLO BOLO!",
        "start": 2.0,
        "end": 17.0,
        "peak": 10.0,
    },
    {
        "id": "2_outplay",
        "video": os.path.join(BASE_CLIPS_DIR, "League of Legends 11-10-2026 23-25-11-785_0.mp4"),
        "action": "outplay",
        "champion": "Katarina",
        "rank": "Diamond",
        "hook": "CLEAN OUTPLAY!",
        "start": 2.0,
        "end": 17.0,
        "peak": 10.5,
    },
    {
        "id": "3_triple_kill",
        "video": os.path.join(BASE_CLIPS_DIR, "League of Legends 11-10-2026 23-26-58-636_0.mp4"),
        "action": "triple",
        "champion": "Katarina",
        "rank": "Diamond",
        "hook": "TRIPLE KILL!",
        "start": 3.0,
        "end": 18.0,
        "peak": 11.0,
    },
    {
        "id": "4_double_kill",
        "video": os.path.join(BASE_CLIPS_DIR, "League of Legends 11-10-2026 23-29-55-782_0.mp4"),
        "action": "double",
        "champion": "Katarina",
        "rank": "Diamond",
        "hook": "DOUBLE KILL!",
        "start": 2.0,
        "end": 17.0,
        "peak": 9.5,
    },
    {
        "id": "5_chaotic_teamfight",
        "video": os.path.join(BASE_CLIPS_DIR, "League of Legends 11-10-2026 23-31-04-038_0.mp4"),
        "action": "triple",
        "champion": "Katarina",
        "rank": "Diamond",
        "hook": "TEAMFIGHT RESET!",
        "start": 1.0,
        "end": 16.0,
        "peak": 9.0,
    },
]

def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "benchmark_output"
    out_dir = os.path.join(ROOT_DIR, "outputs", target_dir)
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 60)
    print(f"🎬 FLIKCUT RENDER KONTROLNY (5 KLIPÓW WZORCOWYCH)")
    print(f"📁 Folder wyjściowy: {out_dir}")
    print("=" * 60)

    for i, clip in enumerate(BENCHMARK_CLIPS, 1):
        if not os.path.exists(clip["video"]):
            print(f"⚠️  Pominięto klip {i} (brak pliku: {clip['video']})")
            continue

        out_name = f"short_{clip['id']}.mp4"
        out_path = os.path.join(out_dir, out_name)
        print(f"\n[{i}/5] Renderuję: {clip['id']} ({clip['action']}, {clip['champion']})...")
        t0 = time.time()

        try:
            _run_pipeline(
                source_path=clip["video"],
                clip_start=clip["start"],
                clip_end=clip["end"],
                action_type=clip["action"],
                champion_name=clip["champion"],
                rank=clip["rank"],
                use_speed_ramp=True,
                use_zoom_punch=True,
                use_smart_camera=True,
                peak_moment=clip["peak"],
                hook_text=clip["hook"],
                notify_token=None,
                output_filename=os.path.join(target_dir, out_name),
            )
            dur = time.time() - t0
            print(f"   ✅ Gotowe w {dur:.1f}s | QA Score: {_state.qa_score} | Output: {_state.output_path}")
            recipe_path = os.path.splitext(out_path)[0] + ".recipe.json"
            if os.path.exists(recipe_path):
                print(f"   📜 Przepis (recipe): {recipe_path}")
        except Exception as e:
            print(f"   ❌ Błąd renderu klipu {clip['id']}: {e}")

    print("\n" + "=" * 60)
    print("🎯 Render kontrolny zakończony!")
    print(f"Pliki do weryfikacji znajdują się w: {out_dir}")
    print("=" * 60)

if __name__ == "__main__":
    main()
