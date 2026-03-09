import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip
from typing import Optional

# --- USTAWIENIA ---
# Upewnij się, że masz te pliki w głównym folderze projektu
LOGO_PATH = "logo.png"  # Ścieżka do Twojego pliku z logo
FONT_PATH = "impact.ttf"  # Ścieżka do pliku czcionki (np. Impact)
OUTPUT_DIR = "temp_videos"


def create_thumbnail(video_path: str, title: str, output_filename: str = "thumbnail.jpg") -> Optional[str]:
    """
    Generuje profesjonalną miniaturkę dla shorta YouTube.

    1. Automatycznie wyciąga klatkę ze środka filmu.
    2. Nakłada ciemny filtr dla lepszego kontrastu.
    3. Dodaje logo w rogu.
    4. Dodaje tytuł na środku (biały tekst z czarnym obramowaniem), automatycznie łamiąc długie linie.
    """
    print("🖼️ Rozpoczynam generowanie miniaturki...")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    try:
        # 1. Wyciągnij klatkę ze środka filmu
        with VideoFileClip(video_path) as clip:
            frame_time = clip.duration / 2
            frame = clip.get_frame(frame_time)
            bg_image = Image.fromarray(frame)

        # 2. Nałóż półprzezroczystą czarną warstwę dla lepszego kontrastu
        overlay = Image.new('RGBA', bg_image.size, (0, 0, 0, 90))  # Zwiększono do 90 dla lepszego kontrastu
        bg_image_rgba = bg_image.convert('RGBA')
        bg_image = Image.alpha_composite(bg_image_rgba, overlay)

        draw = ImageDraw.Draw(bg_image)

        # 3. Dodaj logo
        if os.path.exists(LOGO_PATH):
            with Image.open(LOGO_PATH).convert("RGBA") as logo_img:
                logo_img.thumbnail((220, 220))
                bg_image.paste(logo_img, (60, 60), logo_img)  # Margines
        else:
            print(f"🟡 Ostrzeżenie: Nie znaleziono pliku logo w '{LOGO_PATH}'.")

        # 4. Dodaj tytuł z obramowaniem
        try:
            font = ImageFont.truetype(FONT_PATH, 120)  # Zwiększono czcionkę
        except IOError:
            print(f"🟡 Ostrzeżenie: Nie znaleziono czcionki '{FONT_PATH}'. Używam domyślnej.")
            font = ImageFont.load_default()

        # ULEPSZENIE: Automatyczne łamanie długich tytułów
        avg_char_width = sum(font.getbbox(char)[2] for char in 'abcdefghijklmnopqrstuvwxyz') / 26
        max_chars_per_line = int(bg_image.width * 0.8 / avg_char_width)  # 80% szerokości
        wrapped_title = textwrap.fill(title.upper(), width=max_chars_per_line)

        # Wylicz pozycję dla całego bloku tekstu
        text_bbox = draw.textbbox((0, 0), wrapped_title, font=font, align='center')
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = (bg_image.width - text_width) / 2
        y = (bg_image.height - text_height) / 2 - 50  # Przesunięcie lekko w górę

        # Rysuj czarne obramowanie (stroke)
        stroke_width = 5
        draw.text((x, y), wrapped_title, font=font, fill="black", stroke_width=stroke_width, align='center')

        # Rysuj właściwy biały tekst
        draw.text((x, y), wrapped_title, font=font, fill="white", align='center')

        # 5. Zapisz finalną miniaturkę
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        bg_image.convert("RGB").save(output_path, "JPEG", quality=95)

        print(f"✅ Miniaturka zapisana w: {output_path}")
        return output_path

    except Exception as e:
        print(f"❌ Wystąpił błąd podczas tworzenia miniaturki: {e}")
        return None


if __name__ == '__main__':
    # --- Prosty test działania modułu ---
    TEST_VIDEO_PATH = os.path.join("videos", "test_clip.mp4")
    # Dłuższy tytuł do testowania łamania linii
    TEST_TITLE = "🤯 NIESAMOWITA AKCJA, KTÓREJ NIKT SIĘ NIE SPODZIEWAŁ!"

    if os.path.exists(TEST_VIDEO_PATH):
        create_thumbnail(TEST_VIDEO_PATH, TEST_TITLE)
        print("\n🎉 Test zakończony. Sprawdź plik 'thumbnail.jpg' w folderze 'temp_videos'.")
    else:
        print(f"❌ Błąd: Plik testowy '{TEST_VIDEO_PATH}' nie został znaleziony.")