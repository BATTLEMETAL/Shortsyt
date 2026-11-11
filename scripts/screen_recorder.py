"""
Shortsyt — Windows Interactive Desktop Screen Recorder
Automated High-Performance Screen Capture via Win32 GDI + FFmpeg Pipeline

Solves the Windows Background Session / Desktop Isolation issue (Error 5 / Access Denied)
by switching the thread desktop to 'Default' on WinSta0.
"""
import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
from typing import Optional, Tuple


u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32

# Win32 Constants
DESKTOP_GENERIC_ALL = 0x10000000
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD)
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ('left', wintypes.LONG),
        ('top', wintypes.LONG),
        ('right', wintypes.LONG),
        ('bottom', wintypes.LONG)
    ]


def switch_to_default_desktop() -> bool:
    """
    Przełącza wątek z sesji izolowanej (exebox/Session 0) na fizyczny interaktywny pulpit 'Default'.
    Umożliwia bezbłędny odczyt bufora ekranu bez błędu 'Access Denied'.
    """
    try:
        hdesk = u32.OpenDesktopW("Default", 0, False, DESKTOP_GENERIC_ALL)
        if hdesk:
            ok = u32.SetThreadDesktop(hdesk)
            return bool(ok)
    except Exception as e:
        print(f"[screen_recorder] Warning during desktop switch: {e}", file=sys.stderr)
    return False


def get_ffmpeg_path() -> str:
    """Znajduje ścieżkę do binarnego FFmpeg."""
    candidates = [
        r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.exe",
        "ffmpeg",
    ]
    for c in candidates:
        if Path(c).is_file():
            return str(Path(c).resolve())
    return "ffmpeg"


def find_window_geometry(target_title: str) -> Optional[Tuple[int, int, int, int]]:
    """
    Wyszukuje widoczne okno zawierające dany ciąg znaków w tytule i zwraca (x, y, w, h).
    Wymiary w i h są zaokrąglane do liczb parzystych (wymóg H.264).
    """
    found_hwnd = None

    def enum_windows_callback(hwnd, extra):
        nonlocal found_hwnd
        if u32.IsWindowVisible(hwnd):
            length = u32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                u32.GetWindowTextW(hwnd, buf, length + 1)
                if target_title.lower() in buf.value.lower():
                    found_hwnd = hwnd
                    return False
        return True

    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_windows_callback)
    u32.EnumWindows(cb, 0)

    if not found_hwnd:
        return None

    rect = RECT()
    u32.GetWindowRect(found_hwnd, ctypes.byref(rect))
    x = max(0, rect.left)
    y = max(0, rect.top)
    w = max(100, rect.right - rect.left)
    h = max(100, rect.bottom - rect.top)

    # Wymóg H.264: szerokość i wysokość muszą być parzyste
    if w % 2 != 0:
        w -= 1
    if h % 2 != 0:
        h -= 1

    return (x, y, w, h)


def record_screen(
    output_path: str,
    duration: Optional[float] = 30.0,
    fps: int = 30,
    window_title: Optional[str] = None,
    stop_event: Optional[threading.Event] = None,
) -> bool:
    """
    Nagrywa pulpit lub wybrane okno aplikacji bezpośrednio do pliku MP4 (H.264).
    """
    # 1. Uzyskaj uprawnienia do interaktywnego pulpitu
    switch_to_default_desktop()

    # 2. Wyznacz geometrię nagrywania
    x, y = 0, 0
    w = u32.GetSystemMetrics(0)
    h = u32.GetSystemMetrics(1)

    if window_title:
        geom = find_window_geometry(window_title)
        if geom:
            x, y, w, h = geom
            print(f"[screen_recorder] Wykryto okno '{window_title}': {w}x{h} na pozycji ({x}, {y})")
        else:
            print(f"[screen_recorder] Okno '{window_title}' nieznalezione, nagrywam cały pulpit ({w}x{h})")

    # Upewnij się, że wymiary są parzyste
    if w % 2 != 0:
        w -= 1
    if h % 2 != 0:
        h -= 1

    # 3. Przygotuj kontekst graficzny Win32 GDI
    hdc_screen = u32.GetDC(0)
    hdc_mem = g32.CreateCompatibleDC(hdc_screen)
    hbm = g32.CreateCompatibleBitmap(hdc_screen, w, h)
    g32.SelectObject(hdc_mem, hbm)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down DIB
    bmi.biPlanes = 1
    bmi.biBitCount = 24
    bmi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 3)

    # 4. Skonfiguruj potok FFmpeg
    ffmpeg_bin = get_ffmpeg_path()
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{w}x{h}",
        "-pix_fmt", "bgr24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(Path(output_path).resolve())
    ]

    print(f"[screen_recorder] Rozpoczynam nagrywanie: {w}x{h} @ {fps} FPS -> {output_path}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    frame_interval = 1.0 / fps
    t_start = time.time()
    t_end = (t_start + duration) if duration else float("inf")
    frames = 0

    try:
        while time.time() < t_end:
            if stop_event and stop_event.is_set():
                break

            target_frame_time = t_start + frames * frame_interval

            # Przechwyć klatkę z pulpitu
            g32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY)
            g32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)

            # Wyślij surowy bufor BGR24 do FFmpeg
            try:
                proc.stdin.write(buf.raw)
            except (BrokenPipeError, OSError):
                break

            frames += 1

            # Płynny pacing klatek
            delay = target_frame_time - time.time()
            if delay > 0.001:
                time.sleep(delay)

    except KeyboardInterrupt:
        print("\n[screen_recorder] Przerwano nagrywanie przez użytkownika.")
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

        u32.ReleaseDC(0, hdc_screen)
        g32.DeleteDC(hdc_mem)
        g32.DeleteObject(hbm)

    total_time = max(0.1, time.time() - t_start)
    actual_fps = frames / total_time
    print(f"[screen_recorder] Zakończono: nagrano {frames} klatek ({total_time:.1f}s, {actual_fps:.1f} FPS).")
    print(f"[screen_recorder] Plik zapisany: {output_path}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shortsyt Windows Desktop Screen Recorder")
    parser.add_argument("--duration", type=float, default=15.0, help="Czas nagrania w sekundach (domyślnie: 15s)")
    parser.add_argument("--output", type=str, default="shortsyt_demo.mp4", help="Ścieżka do pliku wyjściowego MP4")
    parser.add_argument("--fps", type=int, default=30, help="Klatki na sekundę (domyślnie: 30)")
    parser.add_argument("--window", type=str, default=None, help="Nazwa okna do nagrywania (np. 'Shortsyt Studio')")
    args = parser.parse_args()

    record_screen(
        output_path=args.output,
        duration=args.duration,
        fps=args.fps,
        window_title=args.window,
    )
