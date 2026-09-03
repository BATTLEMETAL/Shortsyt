"""
smart_watermark_remover.py
===========================
Inteligentne usuwanie znaków wodnych z filmów (TikTok, Snapchat, CapCut, InShot).

Strategie:
  - inpaint: OpenCV inpainting (TELEA/NS) — najlepsza jakość, klatka po klatce
  - delogo:  ffmpeg delogo filter — szybki, dla statycznych watermarków
  - auto:    automatyczny wybór per-watermark (domyślny)

Użycie:
  python smart_watermark_remover.py video.mp4                        # auto
  python smart_watermark_remover.py video.mp4 --strategy inpaint     # wymuś inpainting
  python smart_watermark_remover.py video.mp4 --strategy delogo      # wymuś delogo
  python smart_watermark_remover.py video.mp4 --preview              # zapisz klatki debug
  python smart_watermark_remover.py --folder "C:\\path" --strategy auto
  python smart_watermark_remover.py video.mp4 --dry-run              # analiza bez zapisu
"""
import os
import sys
import json
import re
import shutil
import subprocess
import argparse
import math
import time
from dataclasses import dataclass, field
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np

# ── Konfiguracja ─────────────────────────────────────────────────────────────
TEMP_DIR  = os.path.join(os.path.dirname(__file__), "temp_videos", "wm_temp")
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "temp_videos", "wm_debug")

os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)


# ── Typy danych ──────────────────────────────────────────────────────────────
@dataclass
class WatermarkRegion:
    """Pojedynczy wykryty watermark."""
    x: int
    y: int
    w: int
    h: int
    platform: str          # "tiktok_username", "tiktok_logo", "tiktok_ui", "snapchat", "capcut", "inshot", "generic"
    confidence: float      # 0.0 – 1.0
    is_static: bool        # True = nie zmienia pozycji między klatkami
    timestamp: float = 0.0 # czas w sekundzie (dla floating)
    mask: Optional[np.ndarray] = field(default=None, repr=False)  # precyzyjna maska pikseli


@dataclass
class WatermarkAnalysis:
    """Wynik analizy całego wideo."""
    regions_per_frame: dict  # {frame_idx: [WatermarkRegion, ...]}
    static_regions: list     # regiony stabilne przez cały film
    floating_regions: list   # regiony zmieniające pozycję
    video_info: dict
    platform_summary: dict   # {"tiktok_username": 45, "tiktok_logo": 50, ...}


# ══════════════════════════════════════════════════════════════════════════════
# DETEKCJA WATERMARKÓW
# ══════════════════════════════════════════════════════════════════════════════

class WatermarkDetector:
    """Wieloplatformowe wykrywanie watermarków w klatkach wideo."""

    def __init__(self, video_w: int, video_h: int):
        self.vw = video_w
        self.vh = video_h

    # ── Główna detekcja ──────────────────────────────────────────────────────
    def detect_all(self, frame: np.ndarray) -> list[WatermarkRegion]:
        """Wykrywa wszystkie watermarki w klatce."""
        results = []
        results += self._detect_tiktok_username(frame)
        results += self._detect_tiktok_logo(frame)
        results += self._detect_tiktok_ui_icons(frame)
        results += self._detect_snapchat(frame)
        results += self._detect_capcut_inshot(frame)
        results += self._detect_generic_corner_text(frame)

        # Deduplikacja: usuń nakładające się regiony (zachowaj wyższe confidence)
        results = self._deduplicate(results)
        return results

    # ── TikTok @username (floating) ──────────────────────────────────────────
    def _detect_tiktok_username(self, frame: np.ndarray) -> list[WatermarkRegion]:
        """
        TikTok @username watermark:
        - Biały tekst z czarnym cieniem/outline ("TikTok" + "@username")
        - Floating: zmienia pozycję co kilka sekund
        - Rozmiar: ~25-45% szerokości × ~4-10% wysokości
        - Pozycja: krawędzie kadru (lewy/prawy/dolny) — NIE środek!
          Watermark TikTok NIGDY nie jest wycentrowany — jest przy brzegach.
        """
        w, h = self.vw, self.vh
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # TikTok watermark pojawia się TYLKO przy krawędziach kadru:
        # - Lewa strona (x < 40% szerokości) — najczęściej
        # - Prawa strona (x > 55% szerokości) — czasem
        # - Dolna strefa (y > 55% wysokości)
        # NIGDY nie jest wycentrowany — tekst w centrum to napisy/treść!
        edge_zones = [
            # (sy1, sy2, sx1, sx2) — strefy krawędziowe
            (int(h * 0.45), int(h * 0.90), 0, int(w * 0.50)),               # lewy dół
            (int(h * 0.45), int(h * 0.90), int(w * 0.45), w),               # prawy dół
            (int(h * 0.15), int(h * 0.55), 0, int(w * 0.35)),               # lewy środek
            (int(h * 0.15), int(h * 0.55), int(w * 0.60), w),               # prawy środek
        ]

        results = []

        for sy1, sy2, sx1, sx2 in edge_zones:
            zone = gray[sy1:sy2, sx1:sx2]

            # Threshold: biały tekst watermarku (>210 jasności)
            _, bright = cv2.threshold(zone, 210, 255, cv2.THRESH_BINARY)

            # Morfologia: łącz litery horyzontalnie, potem linie pionowo
            k_join_h = cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.04), 3))
            joined = cv2.dilate(bright, k_join_h, iterations=2)
            k_join_v = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 12))
            joined = cv2.dilate(joined, k_join_v, iterations=1)
            k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            closed = cv2.morphologyEx(joined, cv2.MORPH_CLOSE, k_close)

            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            min_wm_w = int(w * 0.15)
            max_wm_w = int(w * 0.60)
            min_wm_h = int(h * 0.025)
            max_wm_h = int(h * 0.14)

            for cnt in contours:
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                if not (min_wm_w <= rw <= max_wm_w and min_wm_h <= rh <= max_wm_h):
                    continue
                aspect = rw / max(rh, 1)
                if not (1.3 <= aspect <= 8.0):
                    continue
                region_bright = bright[ry:ry + rh, rx:rx + rw]
                density = np.sum(region_bright > 0) / max(rw * rh, 1)
                if not (0.04 <= density <= 0.60):
                    continue
                shadow_score = self._check_text_shadow(zone, rx, ry, rw, rh)
                confidence = min(1.0, density * 1.5 + shadow_score * 0.3 + (aspect / 8.0) * 0.2)
                if confidence < 0.25:
                    continue

                pad_x, pad_y = 15, 20
                abs_x = max(0, sx1 + rx - pad_x)
                abs_y = max(0, sy1 + ry - pad_y)
                abs_w = min(w - abs_x, rw + pad_x * 2)
                abs_h = min(h - abs_y, rh + pad_y * 2)

                # Watermark TikTok NIGDY nie jest w top 25% kadru
                if abs_y < h * 0.25:
                    continue
                # Wycentrowany tekst w top 45% = napisy treści (center_x > 35%)
                # Watermark TikTok po lewej: center_x ≈ 22-30% → NIE odrzucamy
                # Napisy treści ("Peruczka..."): center_x ≈ 55-65% → odrzucamy
                center_x = abs_x + abs_w / 2
                if (w * 0.35 < center_x < w * 0.80) and abs_y < h * 0.45:
                    continue

                mask = self._create_text_mask(frame, abs_x, abs_y, abs_w, abs_h)
                results.append(WatermarkRegion(
                    x=abs_x, y=abs_y, w=abs_w, h=abs_h,
                    platform="tiktok_username",
                    confidence=round(confidence, 2),
                    is_static=False,
                    mask=mask,
                ))

        return results

    # ── TikTok logo (♪ prawa dolna) ──────────────────────────────────────────
    def _detect_tiktok_logo(self, frame: np.ndarray) -> list[WatermarkRegion]:
        """
        TikTok logo nuty muzycznej (♪) + tekst "TikTok":
        - Prawy dolny róg, mały okrągły element + tekst
        - Animowany (obraca się)
        - Białe/kolorowe na dowolnym tle
        """
        w, h = self.vw, self.vh
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Region: prawy-środkowy i prawy-dolny (ostatnie 35% szerokości, dolne 35% wysokości)
        # Rozszerzono w górę z 82% do 65% aby złapać blok "TikTok + @username" przy prawej krawędzi
        rx1 = int(w * 0.60)
        ry1 = int(h * 0.65)
        zone = gray[ry1:h, rx1:w]

        # Szukaj jasnych elementów
        _, bright = cv2.threshold(zone, 200, 255, cv2.THRESH_BINARY)

        # Morfologia
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        dilated = cv2.dilate(bright, k, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        for cnt in contours:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch

            # Logo TikTok: może być mały element (samo logo) lub duży blok (logo + @username)
            min_area = int(w * h * 0.001)
            max_area = int(w * h * 0.060)  # zwiększono — blok 254×124px = ~5.4% kadru

            if not (min_area <= area <= max_area):
                continue

            density = np.sum(bright[cy:cy + ch, cx:cx + cw] > 0) / max(area, 1)
            if density < 0.08:
                continue

            pad = 10
            abs_x = max(0, rx1 + cx - pad)
            abs_y = max(0, ry1 + cy - pad)
            abs_w = min(w - abs_x, cw + pad * 2)
            abs_h = min(h - abs_y, ch + pad * 2)

            mask = self._create_text_mask(frame, abs_x, abs_y, abs_w, abs_h)

            results.append(WatermarkRegion(
                x=abs_x, y=abs_y, w=abs_w, h=abs_h,
                platform="tiktok_logo",
                confidence=round(min(1.0, density * 2), 2),
                is_static=False,  # animowane
                mask=mask,
            ))

        return results

    # ── TikTok UI ikony (❤️ 💬 ↗️ po prawej) ────────────────────────────────
    def _detect_tiktok_ui_icons(self, frame: np.ndarray) -> list[WatermarkRegion]:
        """
        TikTok prawoboczny panel UI: serce, komentarz, share, profil.
        - Prawy bok, 40-80% wysokości
        - Białe ikony z cieniem
        - Pionowy układ
        """
        w, h = self.vw, self.vh
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Region: prawy bok (ostatnie 18% szerokości, 35-80% wysokości)
        rx1 = int(w * 0.82)
        ry1 = int(h * 0.35)
        ry2 = int(h * 0.82)
        zone = gray[ry1:ry2, rx1:w]

        _, bright = cv2.threshold(zone, 210, 255, cv2.THRESH_BINARY)

        # Szukaj wielu małych okrągłych elementów w pionie
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilated = cv2.dilate(bright, k, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filtruj ikony (małe, okrągłe elementy)
        icons = []
        icon_min = int(w * 0.03)
        icon_max = int(w * 0.14)

        for cnt in contours:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            if icon_min <= cw <= icon_max and icon_min <= ch <= icon_max:
                aspect = cw / max(ch, 1)
                if 0.4 <= aspect <= 2.5:
                    icons.append((cx, cy, cw, ch))

        # Jeśli znaleźliśmy >= 2 ikony ułożone pionowo — to TikTok UI
        if len(icons) >= 2:
            # Otocz wszystkie ikony jednym regionem
            all_x = [i[0] for i in icons]
            all_y = [i[1] for i in icons]
            all_x2 = [i[0] + i[2] for i in icons]
            all_y2 = [i[1] + i[3] for i in icons]

            pad = 8
            abs_x = max(0, rx1 + min(all_x) - pad)
            abs_y = max(0, ry1 + min(all_y) - pad)
            abs_w = min(w - abs_x, max(all_x2) - min(all_x) + pad * 2)
            abs_h = min(h - abs_y, max(all_y2) - min(all_y) + pad * 2)

            mask = self._create_text_mask(frame, abs_x, abs_y, abs_w, abs_h)

            return [WatermarkRegion(
                x=abs_x, y=abs_y, w=abs_w, h=abs_h,
                platform="tiktok_ui",
                confidence=min(1.0, len(icons) * 0.25),
                is_static=True,
                mask=mask,
            )]

        return []

    # ── Snapchat ─────────────────────────────────────────────────────────────
    def _detect_snapchat(self, frame: np.ndarray) -> list[WatermarkRegion]:
        """
        Snapchat watermark:
        - Żółty ghost logo lub tekst w lewym górnym/dolnym rogu
        - Timestamp/lokalizacja w środku
        - Żółty kolor (H: 25-35, S: 200+, V: 200+)
        """
        w, h = self.vw, self.vh
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Maska żółtych pikseli (Snapchat yellow: HSV ~25-35, high sat+val)
        lower_yellow = np.array([20, 150, 180])
        upper_yellow = np.array([40, 255, 255])
        yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

        # Sprawdź rogi
        corners = [
            ("lt", 0, 0, int(w * 0.35), int(h * 0.12)),                # lewy górny
            ("lb", 0, int(h * 0.88), int(w * 0.35), h - int(h * 0.88)),# lewy dolny
            ("rt", int(w * 0.65), 0, w - int(w * 0.65), int(h * 0.12)),# prawy górny
        ]

        results = []
        for name, cx, cy, cw, ch in corners:
            corner_zone = yellow_mask[cy:cy + ch, cx:cx + cw]
            yellow_count = np.sum(corner_zone > 0)
            yellow_ratio = yellow_count / max(cw * ch, 1)

            if yellow_ratio > 0.01 and yellow_count > 100:
                # Znajdź bounding box żółtych pikseli
                ys, xs = np.nonzero(corner_zone)
                if len(xs) < 10:
                    continue

                pad = 10
                abs_x = max(0, cx + int(np.min(xs)) - pad)
                abs_y = max(0, cy + int(np.min(ys)) - pad)
                abs_w = min(w - abs_x, int(np.max(xs) - np.min(xs)) + pad * 2)
                abs_h = min(h - abs_y, int(np.max(ys) - np.min(ys)) + pad * 2)

                if abs_w < 15 or abs_h < 15:
                    continue

                mask = self._create_color_mask(frame, abs_x, abs_y, abs_w, abs_h,
                                               lower_yellow, upper_yellow)

                results.append(WatermarkRegion(
                    x=abs_x, y=abs_y, w=abs_w, h=abs_h,
                    platform="snapchat",
                    confidence=round(min(1.0, yellow_ratio * 10), 2),
                    is_static=True,
                    mask=mask,
                ))

        return results

    # ── CapCut / InShot ──────────────────────────────────────────────────────
    def _detect_capcut_inshot(self, frame: np.ndarray) -> list[WatermarkRegion]:
        """
        CapCut: "CapCut" tekst w lewym górnym lub dolnym
        InShot: "InShot" tekst w prawym dolnym rogu
        - Szary/biały tekst, małe, statyczne
        """
        w, h = self.vw, self.vh
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        corners = [
            ("capcut_lt", 0, 0, int(w * 0.30), int(h * 0.08)),
            ("capcut_lb", 0, int(h * 0.92), int(w * 0.30), h - int(h * 0.92)),
            ("inshot_rb", int(w * 0.65), int(h * 0.92), w - int(w * 0.65), h - int(h * 0.92)),
        ]

        results = []
        for name, cx, cy, cw, ch in corners:
            zone = gray[cy:cy + ch, cx:cx + cw]
            _, bright = cv2.threshold(zone, 190, 255, cv2.THRESH_BINARY)

            k = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 3))
            joined = cv2.dilate(bright, k, iterations=1)

            contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                # CapCut/InShot logo: mały tekst, aspect ratio > 2
                if bw < int(w * 0.10) or bh < 10:
                    continue
                aspect = bw / max(bh, 1)
                if aspect < 2.0 or aspect > 10.0:
                    continue

                density = np.sum(bright[by:by + bh, bx:bx + bw] > 0) / max(bw * bh, 1)
                # CapCut/InShot tekst ma wyraźną gęstość (10-50%)
                # Zbyt niska = szum/refleks, zbyt wysoka = biała ściana
                if not (0.10 <= density <= 0.55):
                    continue

                confidence = min(1.0, density * 2.5)
                if confidence < 0.35:
                    continue

                pad = 6
                abs_x = max(0, cx + bx - pad)
                abs_y = max(0, cy + by - pad)
                abs_w = min(w - abs_x, bw + pad * 2)
                abs_h = min(h - abs_y, bh + pad * 2)

                platform = "capcut" if "capcut" in name else "inshot"
                mask = self._create_text_mask(frame, abs_x, abs_y, abs_w, abs_h)

                results.append(WatermarkRegion(
                    x=abs_x, y=abs_y, w=abs_w, h=abs_h,
                    platform=platform,
                    confidence=round(confidence, 2),
                    is_static=True,
                    mask=mask,
                ))

        return results

    # ── Generic corner text ──────────────────────────────────────────────────
    def _detect_generic_corner_text(self, frame: np.ndarray) -> list[WatermarkRegion]:
        """
        Fallback: szukaj dowolnego jasnego tekstu w MAŁYCH rogach kadru
        (inne edytory, apki, niezidentyfikowane watermarki).
        Bardzo konserwatywny — łapie tylko wyraźny tekst w samych rogach.
        """
        w, h = self.vw, self.vh
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Tylko MAŁE rogi — 20% × 5% kadru — unikamy łapania treści
        corners = [
            (0, 0, int(w * 0.22), int(h * 0.05)),                          # lewy górny
            (int(w * 0.78), 0, w - int(w * 0.78), int(h * 0.05)),          # prawy górny
            (0, int(h * 0.95), int(w * 0.22), h - int(h * 0.95)),          # lewy dolny
            (int(w * 0.78), int(h * 0.95), w - int(w * 0.78), h - int(h * 0.95)),  # prawy dolny
        ]

        results = []
        for cx, cy, cw, ch in corners:
            if cw <= 0 or ch <= 0:
                continue
            zone = gray[cy:cy + ch, cx:cx + cw]
            _, bright = cv2.threshold(zone, 220, 255, cv2.THRESH_BINARY)

            white_ratio = np.sum(bright > 0) / max(cw * ch, 1)

            # Wyraźny tekst: 5-35% białych pikseli
            if not (0.05 <= white_ratio <= 0.35):
                continue

            k = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 3))
            joined = cv2.dilate(bright, k, iterations=1)
            contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                # Wymagaj teksto-podobnych proporcji
                if bw < int(w * 0.08) or bh < 8:
                    continue
                aspect = bw / max(bh, 1)
                if aspect < 1.5:
                    continue

                density = np.sum(bright[by:by + bh, bx:bx + bw] > 0) / max(bw * bh, 1)
                if density < 0.10:
                    continue

                pad = 6
                abs_x = max(0, cx + bx - pad)
                abs_y = max(0, cy + by - pad)
                abs_w = min(w - abs_x, bw + pad * 2)
                abs_h = min(h - abs_y, bh + pad * 2)

                mask = self._create_text_mask(frame, abs_x, abs_y, abs_w, abs_h)

                results.append(WatermarkRegion(
                    x=abs_x, y=abs_y, w=abs_w, h=abs_h,
                    platform="generic",
                    confidence=round(min(0.6, density * 2), 2),
                    is_static=True,
                    mask=mask,
                ))

        return results

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _check_text_shadow(self, zone_gray: np.ndarray, x: int, y: int,
                           w: int, h: int) -> float:
        """Sprawdza czy tekst ma cień (typowe dla TikTok)."""
        if y + h + 3 >= zone_gray.shape[0]:
            return 0.0
        # Piksele tuż pod tekstem powinny być ciemniejsze (cień)
        below = zone_gray[y + h:y + h + 3, x:x + w]
        above = zone_gray[y:y + h, x:x + w]

        mean_below = np.mean(below) if below.size > 0 else 128
        mean_above = np.mean(above) if above.size > 0 else 128

        # Cień = piksele pod tekstem ciemniejsze niż średnia
        if mean_above > mean_below and (mean_above - mean_below) > 20:
            return 1.0
        return 0.0

    def _create_text_mask(self, frame: np.ndarray,
                          x: int, y: int, w: int, h: int) -> np.ndarray:
        """
        Tworzy PRECYZYJNĄ maskę pikseli watermarku (tylko tekst, nie tło).
        
        Podejście: wykryj jasne piksele tekstu + ciemny outline w regionie,
        rozszerz o 3px aby pokryć antyaliasing i cienie.
        Inpainting wypełni TYLKO faktyczne piksele tekstu — tło pozostaje.
        """
        if w <= 0 or h <= 0:
            return np.zeros((max(1, h), max(1, w)), dtype=np.uint8)

        region = frame[y:y + h, x:x + w]
        if region.size == 0:
            return np.zeros((h, w), dtype=np.uint8)

        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

        # Jasne piksele: biały tekst TikTok (>190 jasności)
        _, bright = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY)

        # Ciemne piksele: czarny outline tekstu (<60 jasności)
        _, dark = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)

        # Połącz: biały tekst + czarny outline
        text_mask = cv2.bitwise_or(bright, dark)

        # Rozszerz o 4px aby pokryć antyaliasing i przejścia kolorów
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        text_mask = cv2.dilate(text_mask, k, iterations=1)

        return text_mask

    def _create_color_mask(self, frame: np.ndarray,
                           x: int, y: int, w: int, h: int,
                           lower_hsv: np.ndarray, upper_hsv: np.ndarray) -> np.ndarray:
        """Maska oparta na kolorze (dla Snapchat żółty itp.)."""
        region = frame[y:y + h, x:x + w]
        if region.size == 0:
            return np.zeros((h, w), dtype=np.uint8)

        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lower_hsv, upper_hsv)

        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilated = cv2.dilate(mask, k, iterations=1)
        return dilated

    def _deduplicate(self, regions: list[WatermarkRegion]) -> list[WatermarkRegion]:
        """Usuwa nakładające się regiony, zachowując te z wyższym confidence."""
        if len(regions) <= 1:
            return regions

        # Sortuj malejąco po confidence
        regions.sort(key=lambda r: r.confidence, reverse=True)

        kept = []
        for r in regions:
            overlap = False
            for k in kept:
                # Sprawdź IoU (Intersection over Union)
                ix1 = max(r.x, k.x)
                iy1 = max(r.y, k.y)
                ix2 = min(r.x + r.w, k.x + k.w)
                iy2 = min(r.y + r.h, k.y + k.h)

                if ix1 < ix2 and iy1 < iy2:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    union = r.w * r.h + k.w * k.h - inter
                    iou = inter / max(union, 1)
                    if iou > 0.3:
                        overlap = True
                        break

            if not overlap:
                kept.append(r)

        return kept


# ══════════════════════════════════════════════════════════════════════════════
# ANALIZA WIDEO
# ══════════════════════════════════════════════════════════════════════════════

def get_video_info(path: str) -> dict:
    """Pobiera metadane wideo przez ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,duration,r_frame_rate",
         "-of", "json", path],
        capture_output=True, text=True, timeout=15
    )
    try:
        s = json.loads(r.stdout)["streams"][0]
        fps_parts = s.get("r_frame_rate", "30/1").split("/")
        fps = float(fps_parts[0]) / float(fps_parts[1])
        return {
            "w": int(s["width"]),
            "h": int(s["height"]),
            "duration": float(s.get("duration", 30)),
            "fps": fps,
        }
    except Exception:
        return {"w": 576, "h": 1024, "duration": 30, "fps": 30}


def analyze_video(video_path: str, sample_interval: float = 0.2,
                  debug: bool = False) -> WatermarkAnalysis:
    """
    Pass 1: Próbkuje wideo i zbiera informacje o wszystkich watermarkach.
    """
    info = get_video_info(video_path)
    w, h = info["w"], info["h"]
    duration = info["duration"]
    fps = info["fps"]

    detector = WatermarkDetector(w, h)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"  ❌ Nie mogę otworzyć: {video_path}")
        return WatermarkAnalysis({}, [], [], info, {})

    regions_per_frame = {}
    platform_counts = {}
    all_positions = {}  # platform -> [(t, x, y, w, h), ...]

    t = 0.0
    frame_idx = 0
    total_samples = int(duration / sample_interval)

    print(f"  🔍 Analizuję watermarki... ({total_samples} próbek, co {sample_interval}s)")

    while t < duration:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ret, frame = cap.read()
        if not ret:
            break

        regions = detector.detect_all(frame)

        if regions:
            regions_per_frame[frame_idx] = regions

            for r in regions:
                r.timestamp = round(t, 2)
                platform_counts[r.platform] = platform_counts.get(r.platform, 0) + 1

                if r.platform not in all_positions:
                    all_positions[r.platform] = []
                all_positions[r.platform].append((t, r.x, r.y, r.w, r.h))

        if debug and regions:
            dbg = frame.copy()
            for r in regions:
                color = {
                    "tiktok_username": (0, 0, 255),
                    "tiktok_logo": (255, 0, 0),
                    "tiktok_ui": (0, 255, 0),
                    "snapchat": (0, 255, 255),
                    "capcut": (255, 128, 0),
                    "inshot": (128, 0, 255),
                    "generic": (200, 200, 200),
                }.get(r.platform, (255, 255, 255))
                cv2.rectangle(dbg, (r.x, r.y), (r.x + r.w, r.y + r.h), color, 2)
                label = f"{r.platform} ({r.confidence:.0%})"
                cv2.putText(dbg, label, (r.x, max(12, r.y - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            dbg_path = os.path.join(DEBUG_DIR, f"detect_{frame_idx:04d}_t{t:.1f}.jpg")
            cv2.imwrite(dbg_path, dbg)

        t += sample_interval
        frame_idx += 1

    cap.release()

    # Klasyfikacja: statyczne vs floating
    static_regions = []
    floating_regions = []

    for platform, positions in all_positions.items():
        if len(positions) < 2:
            # Za mało próbek — zakładamy statyczny
            for t_val, px, py, pw, ph in positions:
                static_regions.append(WatermarkRegion(
                    x=px, y=py, w=pw, h=ph,
                    platform=platform, confidence=0.5, is_static=True,
                ))
            continue

        # Sprawdź wariancję pozycji
        xs = [p[1] for p in positions]
        ys = [p[2] for p in positions]
        var_x = np.std(xs)
        var_y = np.std(ys)

        # Jeśli pozycja stabilna (std < 15px) → statyczny
        is_static = var_x < 15 and var_y < 15

        if is_static:
            # Mediana pozycji + max wymiarów
            median_x = int(np.median(xs))
            median_y = int(np.median(ys))
            max_w = int(np.max([p[3] for p in positions]))
            max_h = int(np.max([p[4] for p in positions]))
            static_regions.append(WatermarkRegion(
                x=median_x, y=median_y, w=max_w, h=max_h,
                platform=platform, confidence=0.8, is_static=True,
            ))
        else:
            for t_val, px, py, pw, ph in positions:
                floating_regions.append(WatermarkRegion(
                    x=px, y=py, w=pw, h=ph,
                    platform=platform, confidence=0.7, is_static=False,
                    timestamp=round(t_val, 2),
                ))

    # Raport
    print(f"  📊 Wykryte watermarki:")
    for plat, cnt in sorted(platform_counts.items(), key=lambda x: -x[1]):
        print(f"     • {plat}: {cnt} detekcji")
    print(f"  📌 Statyczne regiony: {len(static_regions)}")
    print(f"  🔄 Floating regiony: {len(floating_regions)}")

    return WatermarkAnalysis(
        regions_per_frame=regions_per_frame,
        static_regions=static_regions,
        floating_regions=floating_regions,
        video_info=info,
        platform_summary=platform_counts,
    )


# ══════════════════════════════════════════════════════════════════════════════
# USUWANIE WATERMARKÓW
# ══════════════════════════════════════════════════════════════════════════════

class WatermarkRemover:
    """Inteligentne usuwanie watermarków z wyborem strategii per-region."""

    def __init__(self, strategy: str = "auto"):
        self.strategy = strategy

    # ── Główna metoda ────────────────────────────────────────────────────────
    def remove_from_video(self, video_path: str, output_path: str,
                          analysis: WatermarkAnalysis) -> bool:
        """Usuwa watermarki z całego wideo."""
        info = analysis.video_info
        has_static = len(analysis.static_regions) > 0
        has_floating = len(analysis.floating_regions) > 0

        if not has_static and not has_floating:
            print("  ℹ️  Brak wykrytych watermarków — kopiuję bez zmian")
            shutil.copy2(video_path, output_path)
            return True

        # Wybierz strategię
        if self.strategy == "delogo":
            return self._remove_ffmpeg_delogo(video_path, output_path, analysis)
        elif self.strategy == "inpaint":
            return self._remove_inpaint(video_path, output_path, analysis)
        else:
            # AUTO: wybierz najlepszą metodę
            if has_floating:
                # Floating watermarki → klatka-po-klatce inpainting
                print("  🧠 Auto: wykryto floating watermark → inpainting klatka-po-klatce")
                return self._remove_inpaint(video_path, output_path, analysis)
            else:
                # Tylko statyczne → szybki ffmpeg delogo
                print("  🧠 Auto: tylko statyczne watermarki → ffmpeg delogo")
                return self._remove_ffmpeg_delogo(video_path, output_path, analysis)

    # ── Strategia 1: OpenCV Inpainting (najlepsza jakość) ────────────────────
    def _remove_inpaint(self, video_path: str, output_path: str,
                        analysis: WatermarkAnalysis) -> bool:
        """Klatka-po-klatce inpainting z precyzyjną maską.
        
        Optymalizacja: detekcja co DETECT_EVERY klatek (nie na każdej!).
        Maska jest cache'owana i reużywana dla klatek pomiędzy.
        """
        info = analysis.video_info
        w, h = info["w"], info["h"]
        fps = info["fps"]
        DETECT_EVERY = 5  # Detekcja co 5 klatek, reużyj maski między nimi

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print("  ❌ Nie mogę otworzyć wideo")
            return False

        # Krok 1: Zapisz wideo bez audio do tymczasowego pliku
        tmp_video = os.path.join(TEMP_DIR, "inpaint_tmp.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp_video, fourcc, fps, (w, h))

        detector = WatermarkDetector(w, h)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_count = 0
        cleaned_count = 0

        # Zbierz statyczne maski (przelicz raz)
        static_mask = np.zeros((h, w), dtype=np.uint8)
        for sr in analysis.static_regions:
            smask = self._get_or_create_mask(None, sr, w, h, detector, use_rect=True)
            y1 = max(0, sr.y)
            y2 = min(h, sr.y + sr.h)
            x1 = max(0, sr.x)
            x2 = min(w, sr.x + sr.w)
            mh, mw = smask.shape[:2]
            copy_h = min(y2 - y1, mh)
            copy_w = min(x2 - x1, mw)
            if copy_h > 0 and copy_w > 0:
                static_mask[y1:y1 + copy_h, x1:x1 + copy_w] = cv2.bitwise_or(
                    static_mask[y1:y1 + copy_h, x1:x1 + copy_w],
                    smask[:copy_h, :copy_w]
                )

        has_static_mask = np.any(static_mask > 0)
        has_floating = len(analysis.floating_regions) > 0

        # Cache dla floating maski — reużywana między detekcjami
        cached_floating_mask = np.zeros((h, w), dtype=np.uint8)

        print(f"  ⚙️  Inpainting: {total_frames} klatek (detekcja co {DETECT_EVERY})...")
        progress_step = max(1, total_frames // 20)

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Buduj maskę dla tej klatki
            frame_mask = static_mask.copy() if has_static_mask else np.zeros((h, w), dtype=np.uint8)

            # Floating: detekcja co DETECT_EVERY klatek, cache między nimi
            if has_floating:
                if frame_count % DETECT_EVERY == 0:
                    # Pełna detekcja na tej klatce
                    cached_floating_mask = np.zeros((h, w), dtype=np.uint8)
                    fresh_regions = detector.detect_all(frame)
                    for fresh in fresh_regions:
                        if fresh.mask is not None:
                            fy1 = max(0, fresh.y)
                            fy2 = min(h, fresh.y + fresh.h)
                            fx1 = max(0, fresh.x)
                            fx2 = min(w, fresh.x + fresh.w)
                            fmh, fmw = fresh.mask.shape[:2]
                            copy_fh = min(fy2 - fy1, fmh)
                            copy_fw = min(fx2 - fx1, fmw)
                            if copy_fh > 0 and copy_fw > 0:
                                cached_floating_mask[fy1:fy1 + copy_fh, fx1:fx1 + copy_fw] = \
                                    cv2.bitwise_or(
                                        cached_floating_mask[fy1:fy1 + copy_fh, fx1:fx1 + copy_fw],
                                        fresh.mask[:copy_fh, :copy_fw]
                                    )

                # Nakładaj cache'owaną floating maskę
                frame_mask = cv2.bitwise_or(frame_mask, cached_floating_mask)

            # Inpainting jeśli maska nie jest pusta
            if np.any(frame_mask > 0):
                mask_area = int(np.sum(frame_mask > 0))

                if mask_area < 6000:
                    # Małe regiony: jedno przejście wystarczy
                    frame = cv2.inpaint(frame, frame_mask, inpaintRadius=10,
                                        flags=cv2.INPAINT_TELEA)
                else:
                    # Duże regiony (np. TikTok 254×124px = ~31000px²):
                    # Wielokrotne przejścia inpaintingu — każde przejście
                    # wypełnia od krawędzi, kolejne iteracje sięgają głębiej
                    work_mask = frame_mask.copy()
                    k_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                    for _ in range(4):
                        frame = cv2.inpaint(frame, work_mask, inpaintRadius=15,
                                            flags=cv2.INPAINT_TELEA)
                        # Eroduj maskę — następne przejście obejmie mniejszy obszar
                        work_mask = cv2.erode(work_mask, k_erode, iterations=3)
                        if not np.any(work_mask > 0):
                            break

                cleaned_count += 1

            writer.write(frame)
            frame_count += 1

            if frame_count % progress_step == 0:
                pct = frame_count / max(total_frames, 1) * 100
                print(f"     {pct:.0f}% ({frame_count}/{total_frames})")

        cap.release()
        writer.release()

        print(f"  🧹 Wyczyszczono {cleaned_count}/{frame_count} klatek")

        # Krok 2: Połącz wyczyszczone wideo z oryginalnym audio
        ok = self._mux_audio(video_path, tmp_video, output_path, info)

        # Cleanup
        try:
            os.remove(tmp_video)
        except OSError:
            pass

        return ok

    # ── Strategia 2: ffmpeg delogo (szybka) ──────────────────────────────────
    def _remove_ffmpeg_delogo(self, video_path: str, output_path: str,
                              analysis: WatermarkAnalysis) -> bool:
        """Szybkie usuwanie statycznych watermarków przez ffmpeg delogo."""
        info = analysis.video_info
        all_regions = analysis.static_regions + analysis.floating_regions

        if not all_regions:
            shutil.copy2(video_path, output_path)
            return True

        # Buduj filtry delogo — jeden per region
        vf_parts = []
        for r in all_regions:
            # delogo: x, y, w, h, show=0
            # Dodaj mały padding dla lepszego blendingu
            pad = 4
            dx = max(0, r.x - pad)
            dy = max(0, r.y - pad)
            dw = min(info["w"] - dx, r.w + pad * 2)
            dh = min(info["h"] - dy, r.h + pad * 2)
            vf_parts.append(f"delogo=x={dx}:y={dy}:w={dw}:h={dh}:show=0")

        vf = ",".join(vf_parts)

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-profile:v", "high", "-level", "4.1",
            "-c:a", "copy",  # Audio bez zmian!
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        print(f"  ⚙️  ffmpeg delogo: {len(all_regions)} region(ów)...")
        r = subprocess.run(cmd, capture_output=True, timeout=600)

        if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 50_000:
            size_mb = os.path.getsize(output_path) / 1024 / 1024
            print(f"  ✅ delogo OK: {size_mb:.1f}MB")
            return True

        err = r.stderr.decode("utf-8", errors="ignore")[-500:] if r.stderr else ""
        print(f"  ❌ ffmpeg delogo error: {err}")

        # Fallback do inpaint
        print(f"  🔄 Fallback → inpainting...")
        return self._remove_inpaint(video_path, output_path, analysis)

    # ── Mux: połącz wideo + audio ────────────────────────────────────────────
    def _mux_audio(self, original_path: str, video_path: str,
                   output_path: str, info: dict) -> bool:
        """Łączy wyczyszczone wideo z oryginalnym audio (stream copy)."""
        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-i", video_path,
            "-i", original_path,
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-profile:v", "high", "-level", "4.1",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            "-shortest",
            output_path,
        ]

        print(f"  🔊 Łączę z oryginalnym audio...")
        r = subprocess.run(cmd, capture_output=True, timeout=600)

        if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 50_000:
            size_mb = os.path.getsize(output_path) / 1024 / 1024
            print(f"  ✅ Mux OK: {size_mb:.1f}MB")
            return True

        err = r.stderr.decode("utf-8", errors="ignore")[-500:] if r.stderr else ""
        print(f"  ❌ Mux error: {err}")
        return False

    # ── Helper: maska z regionu ──────────────────────────────────────────────
    def _get_or_create_mask(self, frame, region: WatermarkRegion,
                            w: int, h: int, detector: WatermarkDetector,
                            use_rect: bool = False) -> np.ndarray:
        """Zwraca maskę regionu — precyzyjną lub prostokątną."""
        if region.mask is not None and not use_rect:
            return region.mask

        # Fallback: prostokątna maska
        rh = min(region.h, h - region.y)
        rw = min(region.w, w - region.x)
        if rh <= 0 or rw <= 0:
            return np.zeros((1, 1), dtype=np.uint8)
        mask = np.ones((rh, rw), dtype=np.uint8) * 255
        return mask


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def process_single_video(input_path: str, output_path: str,
                         strategy: str = "auto",
                         preview: bool = False,
                         dry_run: bool = False) -> bool:
    """Pełny pipeline: analiza → usuwanie → zapis."""
    print(f"\n{'═' * 60}")
    print(f"  📹 {os.path.basename(input_path)}")
    print(f"{'═' * 60}")

    # Krok 1: Info
    info = get_video_info(input_path)
    print(f"  Wymiary: {info['w']}×{info['h']} | {info['duration']:.1f}s | {info['fps']:.0f}fps")

    # Krok 2: Analiza watermarków
    analysis = analyze_video(input_path, sample_interval=0.2, debug=preview)

    if not analysis.platform_summary:
        print(f"  ℹ️  Brak watermarków — film czysty")
        if not dry_run:
            shutil.copy2(input_path, output_path)
            print(f"  📁 Skopiowano: {output_path}")
        return True

    # Krok 3: Raport
    print(f"\n  {'─' * 40}")
    print(f"  📋 RAPORT DETEKCJI:")
    for plat, cnt in sorted(analysis.platform_summary.items(), key=lambda x: -x[1]):
        emoji = {
            "tiktok_username": "🎵",
            "tiktok_logo": "♪",
            "tiktok_ui": "📱",
            "snapchat": "👻",
            "capcut": "✂️",
            "inshot": "📸",
            "generic": "❔",
        }.get(plat, "•")
        print(f"     {emoji} {plat}: {cnt} detekcji")

    for sr in analysis.static_regions:
        print(f"     📌 Statyczny [{sr.platform}]: ({sr.x},{sr.y}) {sr.w}×{sr.h}px")
    print(f"     🔄 Floating: {len(analysis.floating_regions)} pozycji")
    print(f"  {'─' * 40}")

    if dry_run:
        print(f"  🏁 Dry run — koniec (bez zapisu)")
        return True

    # Krok 4: Usuwanie
    print(f"\n  🚀 Strategia: {strategy}")
    remover = WatermarkRemover(strategy=strategy)
    ok = remover.remove_from_video(input_path, output_path, analysis)

    if ok:
        in_mb = os.path.getsize(input_path) / 1024 / 1024
        out_mb = os.path.getsize(output_path) / 1024 / 1024
        ratio = out_mb / max(in_mb, 0.01) * 100
        print(f"\n  ✅ GOTOWE!")
        print(f"     Wejście:  {in_mb:.1f}MB")
        print(f"     Wyjście:  {out_mb:.1f}MB ({ratio:.0f}% oryginału)")
        print(f"     Plik:     {output_path}")
    else:
        print(f"\n  ❌ Przetwarzanie nie powiodło się")

    return ok


def process_folder(folder: str, output_folder: str, strategy: str = "auto",
                   preview: bool = False, dry_run: bool = False,
                   limit: int = 0) -> dict:
    """Przetwarza wszystkie .mp4 z folderu."""
    os.makedirs(output_folder, exist_ok=True)

    videos = [e for e in os.scandir(folder)
              if e.is_file() and e.name.lower().endswith(".mp4")]

    if limit > 0:
        videos = videos[:limit]

    print(f"📁 Folder: {folder}")
    print(f"📊 Filmów do przetworzenia: {len(videos)}")

    results = {"done": 0, "skipped": 0, "failed": 0}

    for i, entry in enumerate(videos, 1):
        slug = re.sub(r'[^\w]+', '_', entry.name)[:40]
        out_path = os.path.join(output_folder, f"clean_{slug}")

        if os.path.exists(out_path) and os.path.getsize(out_path) > 50_000:
            print(f"\n[{i}/{len(videos)}] ⏭️  Już istnieje: {entry.name[:50]}")
            results["skipped"] += 1
            continue

        print(f"\n[{i}/{len(videos)}] Przetwarzam: {entry.name[:50]}")
        ok = process_single_video(entry.path, out_path, strategy, preview, dry_run)

        if ok:
            results["done"] += 1
        else:
            results["failed"] += 1

    print(f"\n{'═' * 60}")
    print(f"📊 PODSUMOWANIE: ✅ {results['done']} | ⏭️ {results['skipped']} | ❌ {results['failed']}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="🧹 Smart Watermark Remover — inteligentne usuwanie znaków wodnych",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady:
  python smart_watermark_remover.py film.mp4
  python smart_watermark_remover.py film.mp4 --strategy inpaint --preview
  python smart_watermark_remover.py --folder "C:\\Videos" --strategy auto
  python smart_watermark_remover.py film.mp4 --dry-run
        """
    )
    parser.add_argument("input", nargs="?", default=None,
                        help="Ścieżka do pliku wideo")
    parser.add_argument("--folder", default=None,
                        help="Folder z filmami do przetworzenia")
    parser.add_argument("--output", "-o", default=None,
                        help="Ścieżka wyjściowa (plik lub folder)")
    parser.add_argument("--strategy", "-s", default="auto",
                        choices=["auto", "inpaint", "delogo"],
                        help="Strategia usuwania (domyślnie: auto)")
    parser.add_argument("--preview", action="store_true",
                        help="Zapisz klatki debug z zaznaczonymi watermarkami")
    parser.add_argument("--dry-run", action="store_true",
                        help="Tylko analiza — bez zapisu wideo")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max filmów do przetworzenia (0 = bez limitu)")

    args = parser.parse_args()

    print("═" * 60)
    print("  🧹 SMART WATERMARK REMOVER")
    print(f"  Strategia: {args.strategy}")
    if args.preview:
        print(f"  Debug frames: {DEBUG_DIR}")
    print("═" * 60)

    if args.folder:
        out_folder = args.output or os.path.join(args.folder, "cleaned")
        process_folder(args.folder, out_folder, args.strategy,
                       args.preview, args.dry_run, args.limit)

    elif args.input:
        if not os.path.exists(args.input):
            print(f"❌ Plik nie istnieje: {args.input}")
            sys.exit(1)

        if args.output:
            out_path = args.output
        else:
            base, ext = os.path.splitext(args.input)
            out_path = f"{base}_clean{ext}"

        process_single_video(args.input, out_path, args.strategy,
                             args.preview, args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)

    if args.preview:
        print(f"\n🔍 Klatki debug zapisane w: {DEBUG_DIR}")


if __name__ == "__main__":
    main()
