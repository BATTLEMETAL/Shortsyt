import os
import subprocess
import shutil
from typing import Optional

# ULEPSZENIE: Mechanizm "lazy loading", aby nie wczytywać modelu Whisper za każdym razem.
# Zostanie załadowany tylko raz, przy pierwszym użyciu.
_whisper_model = None


def _get_whisper_model(model_size="base"):
    """Ładuje model Whisper, upewniając się, że jest w pamięci tylko jedna jego instancja."""
    global _whisper_model
    if _whisper_model is None:
        print("🎙️ Ładuję model Whisper AI (tylko za pierwszym razem, to może chwilę potrwać)...")
        import whisper
        _whisper_model = whisper.load_model(model_size)
    return _whisper_model


def normalize_audio(input_path: str, output_path: str, target_dbfs: float = -14.0) -> Optional[str]:
    """
    Normalizuje poziom dźwięku w filmie za pomocą FFmpeg w sposób szybki i niezawodny.
    """
    if not os.path.exists(input_path):
        print(f"❌ Błąd: Plik wejściowy do normalizacji nie istnieje: {input_path}")
        return None

    print(f"🔊 Normalizuję dźwięk dla: {os.path.basename(input_path)}...")

    # ULEPSZENIE: Kopiujemy ścieżkę wideo (-c:v copy) bez re-enkodowania, co jest znacznie szybsze.
    ffmpeg_command = [
        "ffmpeg", "-i", input_path,
        "-af", f"loudnorm=I={target_dbfs}:LRA=11:TP=-1.5",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-y", output_path
    ]

    try:
        # ULEPSZENIE: Sprawdzamy, czy komenda zakończyła się sukcesem.
        subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"✅ Dźwięk wyrównany: {os.path.basename(output_path)}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"❌ BŁĄD KRYTYCZNY podczas normalizacji dźwięku przez FFmpeg: {e.stderr.decode()}")
        return None
    except FileNotFoundError:
        print("❌ BŁĄD KRYTYCZNY: Polecenie 'ffmpeg' nie zostało znalezione. Upewnij się, że jest zainstalowane.")
        return None


def generate_and_burn_subtitles(video_path: str, output_path: str) -> str:
    """
    Generuje napisy dla filmu za pomocą Whisper i "wypala" je na stałe w klatkach wideo.
    """
    # Importy wewnątrz funkcji, aby uniknąć błędów, jeśli biblioteki nie są używane
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

    print("💬 Generuję i nakładam napisy...")
    video_clip = None
    final_video = None

    try:
        model = _get_whisper_model()
        result = model.transcribe(video_path, fp16=False)
        video_clip = VideoFileClip(video_path)

        subtitle_clips = []
        for segment in result.get("segments", []):
            start, end, text = segment["start"], segment["end"], segment["text"].strip().upper()
            if not text:
                continue

            # ULEPSZENIE: Bezpieczny wybór czcionki
            font = 'Impact' if 'Impact' in TextClip.list('font') else 'Arial-Bold'

            text_clip = (TextClip(
                txt=text, fontsize=75, color='white', font=font,
                stroke_color='black', stroke_width=3, method='caption',
                size=(video_clip.w * 0.9, None)  # Szerokość napisu to 90% szerokości filmu
            )
                         .set_position(('center', 0.8), relative=True)  # Napisy niżej, lepsze dla Shorts
                         .set_duration(end - start).set_start(start))
            subtitle_clips.append(text_clip)

        if not subtitle_clips:
            print("🟡 Nie wykryto mowy w klipie. Kopiuję wideo bez napisów.")
            shutil.copy(video_path, output_path)
            return output_path

        final_video = CompositeVideoClip([video_clip] + subtitle_clips)
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac', logger=None, threads=4)

        print(f"✅ Napisy nałożone: {os.path.basename(output_path)}")
        return output_path

    except Exception as e:
        print(f"❌ Wystąpił błąd podczas generowania napisów: {e}")
        print("   > Zapisuję oryginalny klip, aby proces mógł kontynuować.")
        if not os.path.exists(output_path):
            shutil.copy(video_path, output_path)  # Kopiujemy, aby następny krok miał plik
        return output_path
    finally:
        # ULEPSZENIE: Zapewniamy zwolnienie zasobów plikowych
        if video_clip:
            video_clip.close()
        if final_video:
            final_video.close()