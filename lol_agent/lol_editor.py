"""
LOL Agent — Editor
Montaż: wyciszenie game audio, nakładanie muzyki, kadrowanie 9:16, overlaye tekstowe
"""
import os
import random
import subprocess
import glob
from typing import Optional
from lol_config import (
    LOL_MUSIC_DIR, LOL_TEMP_DIR,
    OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS,
    MUSIC_VOLUME, GAME_AUDIO_VOLUME,
    SLOWMO_FACTOR, SLOWMO_DURATION,
    ACTION_LABELS, OVERLAY_FONT, OVERLAY_FONT_FALLBACK,
    SHORT_MAX_DURATION
)


def ensure_temp_dir():
    os.makedirs(LOL_TEMP_DIR, exist_ok=True)


def pick_random_music() -> Optional[str]:
    """Losuje utwór muzyczny z folderu lol_music/."""
    music_files = []
    for fmt in ("*.mp3", "*.wav", "*.ogg", "*.m4a"):
        music_files.extend(glob.glob(os.path.join(LOL_MUSIC_DIR, fmt)))

    if not music_files:
        print("⚠️  Brak muzyki w folderze lol_music/ — wideo będzie bez muzyki")
        return None

    chosen = random.choice(music_files)
    print(f"🎵 Wybrano muzykę: {os.path.basename(chosen)}")
    return chosen


def cut_clip(input_path: str, start: float, end: float, output_path: str) -> str:
    """Wycina fragment klipu (ffmpeg seek)."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        output_path
    ]
    print(f"✂️  Tnę klip: {start:.1f}s → {end:.1f}s ({duration:.1f}s)")
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg cut error: {result.stderr.decode()}")
    return output_path


def apply_slowmo_ending(input_path: str, output_path: str,
                        clip_duration: float,
                        slowmo_factor: float = SLOWMO_FACTOR,
                        slowmo_duration: float = SLOWMO_DURATION) -> str:
    """
    Nakłada slow-motion na ostatnią część klipu.
    Normalna prędkość → potem slow-mo na peak moment.
    """
    normal_end = max(0, clip_duration - slowmo_duration)

    if normal_end <= 0:
        # Klip za krótki na slow-mo — kopiuj
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path],
                       capture_output=True)
        return output_path

    temp_normal = output_path.replace(".mp4", "_norm.mp4")
    temp_slow = output_path.replace(".mp4", "_slow.mp4")

    # Part 1: normalna prędkość
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-t", str(normal_end),
        "-c", "copy", temp_normal
    ], capture_output=True)

    # Part 2: slow motion
    pts_factor = 1.0 / slowmo_factor  # 2.0 = 0.5x speed
    subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-ss", str(normal_end),
        "-vf", f"setpts={pts_factor}*PTS",
        "-af", f"atempo={slowmo_factor}",
        temp_slow
    ], capture_output=True)

    # Concat
    concat_file = output_path.replace(".mp4", "_concat.txt")
    with open(concat_file, "w") as f:
        f.write(f"file '{os.path.abspath(temp_normal)}'\n")
        f.write(f"file '{os.path.abspath(temp_slow)}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file, "-c", "copy", output_path
    ], capture_output=True)

    # Cleanup
    for tmp in [temp_normal, temp_slow, concat_file]:
        if os.path.exists(tmp):
            os.remove(tmp)

    print(f"🐌 Slow-motion na ostatnie {slowmo_duration}s ({slowmo_factor}x)")
    return output_path


def crop_to_vertical(input_path: str, output_path: str) -> str:
    """
    Kadruje wideo do formatu 9:16 (1080x1920).
    Jeśli oryginał jest 16:9, wycentruj i przytnij.
    """
    print(f"📐 Kadrowanie do 9:16 ({OUTPUT_WIDTH}x{OUTPUT_HEIGHT})...")

    # Oblicz crop dla 16:9 → 9:16
    # Dla 1920x1080 źródła: crop do 608x1080, potem scale do 1080x1920
    vf_filter = (
        f"scale={OUTPUT_WIDTH * 3}:-1,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:flags=lanczos,"
        f"fps={OUTPUT_FPS}"
    )

    # Prostszy i bardziej niezawodny filter
    vf_filter = (
        f"scale='if(gt(iw/ih,9/16),{OUTPUT_HEIGHT}*9/16,{OUTPUT_WIDTH})':'if(gt(iw/ih,9/16),{OUTPUT_HEIGHT},{OUTPUT_WIDTH}*16/9)',"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={OUTPUT_FPS}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-an",  # Usuń audio — dodamy muzykę osobno
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Fallback: prosty crop
        cmd_fallback = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={OUTPUT_FPS}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-an",
            output_path
        ]
        result2 = subprocess.run(cmd_fallback, capture_output=True)
        if result2.returncode != 0:
            raise RuntimeError(f"FFmpeg crop error: {result2.stderr.decode()}")

    return output_path


def merge_music(video_path: str, music_path: Optional[str],
                output_path: str, video_duration: float) -> str:
    """
    Łączy wideo (bez audio) z muzyką.
    Game audio wyciszone (GAME_AUDIO_VOLUME = 0).
    """
    if not music_path or not os.path.exists(music_path):
        print("⚠️  Brak muzyki — eksportuję bez dźwięku")
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path
        ], capture_output=True)
        return output_path

    print(f"🎵 Nakładam muzykę: {os.path.basename(music_path)}")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", music_path,
        "-map", "0:v:0",         # Video z klipu
        "-map", "1:a:0",         # Audio z muzyki
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-af", f"volume={MUSIC_VOLUME}",
        "-t", str(video_duration),  # Przytnij muzykę do długości klipu
        "-shortest",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge error: {result.stderr.decode()}")

    print(f"✅ Muzyka nałożona pomyślnie")
    return output_path


def add_text_overlay(video_path: str, output_path: str,
                     action_label: str,
                     champion_name: str = "",
                     rank: str = "") -> str:
    """
    Dodaje tekstowy overlay z etykietą akcji (np. PENTAKILL 🔥).
    Używa FFmpeg drawtext filter.
    """
    print(f"🖊️  Dodaję overlay: {action_label}")

    # Emoji nie działają w ffmpeg drawtext — użyj czystego tekstu
    clean_label = action_label
    for emoji in ["🔥", "⚡", "💥", "🎯", "👑", "🚀", "💀", "🐉"]:
        clean_label = clean_label.replace(emoji, "")
    clean_label = clean_label.strip()

    # Linia 1: Akcja (duży tekst, na górze)
    # Linia 2: Champion (mniejszy, pod spodem)
    sub_text = ""
    if champion_name:
        sub_text = f" | {champion_name.upper()}"
    if rank:
        sub_text += f" | {rank}"

    # Drawtext filter
    # Tło półprzezroczyste + biały tekst
    main_font_size = 90
    sub_font_size = 50

    drawtext_main = (
        f"drawtext="
        f"text='{clean_label}{sub_text}':"
        f"fontsize={main_font_size}:"
        f"fontcolor=white:"
        f"bordercolor=black:borderw=4:"
        f"x=(w-text_w)/2:y=h*0.08:"
        f"font=Impact"
    )

    # Animacja — fade in na początku
    drawtext_animated = (
        f"drawtext="
        f"text='{clean_label}':"
        f"fontsize={main_font_size}:"
        f"fontcolor=white:"
        f"bordercolor=black:borderw=5:"
        f"x=(w-text_w)/2:y=h*0.07:"
        f"font=Impact:"
        f"alpha='if(lt(t,0.3),t/0.3,1)'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", drawtext_animated,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"⚠️  Drawtext error, kopiuję bez overlaya: {result.stderr.decode()[:200]}")
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path
        ], capture_output=True)

    return output_path


def add_gradient_bar(video_path: str, output_path: str) -> str:
    """Dodaje gradient bar na dole ekranu (elegancki wygląd gaming)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", (
            "drawbox=x=0:y=ih*0.85:w=iw:h=ih*0.15:"
            "color=black@0.6:t=fill"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path, "-c", "copy", output_path
        ], capture_output=True)
    return output_path


def render_short(
    source_path: str,
    clip_start: float,
    clip_end: float,
    action_type: str,
    champion_name: str = "",
    rank: str = "",
    use_slowmo: bool = True,
    output_filename: str = "lol_short_final.mp4"
) -> str:
    """
    Główna funkcja montażu — przeprowadza cały pipeline edycji.
    Zwraca ścieżkę do gotowego Shorta.
    """
    ensure_temp_dir()
    print(f"\n{'='*50}")
    print(f"🎬 LOL EDITOR — START MONTAŻU")
    print(f"{'='*50}")

    clip_duration = clip_end - clip_start

    # Ścieżki tymczasowe
    t = lambda name: os.path.join(LOL_TEMP_DIR, name)

    step1_cut = t("01_cut.mp4")
    step2_vertical = t("02_vertical.mp4")
    step3_slowmo = t("03_slowmo.mp4")
    step4_gradient = t("04_gradient.mp4")
    step5_overlay = t("05_overlay.mp4")
    step6_final = os.path.join(LOL_TEMP_DIR, output_filename)

    # === KROK 1: Wycięcie najlepszego fragmentu ===
    print("\n📍 KROK 1/5: Wycinanie fragmentu...")
    cut_clip(source_path, clip_start, clip_end, step1_cut)

    # === KROK 2: Kadrowanie do 9:16 ===
    print("\n📍 KROK 2/5: Kadrowanie do 9:16...")
    crop_to_vertical(step1_cut, step2_vertical)

    # === KROK 3: Slow-motion na zakończenie ===
    if use_slowmo and clip_duration > SLOWMO_DURATION + 2:
        print("\n📍 KROK 3/5: Slow-motion...")
        apply_slowmo_ending(step2_vertical, step3_slowmo, clip_duration)
    else:
        print("\n📍 KROK 3/5: Slow-motion pominięty (klip za krótki)")
        import shutil
        shutil.copy(step2_vertical, step3_slowmo)

    # === KROK 4: Gradient bar ===
    print("\n📍 KROK 4/5: Gradient overlay...")
    add_gradient_bar(step3_slowmo, step4_gradient)

    # === KROK 5: Tekst overlay ===
    print("\n📍 KROK 5/5: Tekst overlay...")
    action_label = ACTION_LABELS.get(action_type, "OUTPLAY 🎯")
    add_text_overlay(step4_gradient, step5_overlay, action_label, champion_name, rank)

    # === KROK 6: Muzyka ===
    print("\n📍 KROK 6/6: Nakładanie muzyki...")
    music_path = pick_random_music()

    # Pobierz faktyczną długość po ewentualnym slow-mo
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", step5_overlay
    ], capture_output=True, text=True)
    final_duration = float(result.stdout.strip()) if result.stdout.strip() else clip_duration

    merge_music(step5_overlay, music_path, step6_final, final_duration)

    print(f"\n🎉 SHORT GOTOWY: {step6_final}")
    print(f"   ⏱️  Długość: {final_duration:.1f}s")
    print(f"   🎮 Akcja: {action_label}")
    return step6_final


if __name__ == "__main__":
    # Test
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else \
        r"c:\Users\mz100\PycharmProjects\shortsyt\League of Legends_10-01-2025_3-26-40-0.mp4"

    if os.path.exists(source):
        result_path = render_short(
            source_path=source,
            clip_start=0,
            clip_end=55,
            action_type="pentakill",
            champion_name="Jinx",
            rank="Gold"
        )
        print(f"\n✅ Test zakończony: {result_path}")
    else:
        print(f"❌ Plik nie istnieje: {source}")
