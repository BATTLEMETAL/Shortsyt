"""
Debug: szuka kursora ataku LoL w klatkach wideo.
Wyswietla pixel clusters ktore moga byc kursorem.
"""
import cv2
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smart_camera import extract_sample_frames

VIDEO = r'C:\Users\mz100\PycharmProjects\shortsyt\lol_agent\lol_temp\katarina_pentakill_src.mp4'
CLIP_START = 0.0
CLIP_END   = 22.0
N_FRAMES   = 60
SCALE_W    = 384

frames = extract_sample_frames(VIDEO, CLIP_START, CLIP_END, N_FRAMES, SCALE_W, 216)
t_points = np.linspace(0.0, CLIP_END - CLIP_START, len(frames))

hud_cutoff = int(216 * 0.80)
top_cutoff = int(216 * 0.08)
scale_factor = 1920 / SCALE_W

print(f"Zaladowano {len(frames)} klatek")
print("=" * 70)
print("Szukam potencjalnych kursatorow (non-horizontal orange/red clusters)...")
print()

for i, frame in enumerate(frames):
    t = t_points[i]
    f = frame.astype(np.int16)
    r, g, b = f[:,:,0], f[:,:,1], f[:,:,2]
    h, w = r.shape

    excl = np.ones((h, w), dtype=bool)
    excl[:top_cutoff, :] = False
    excl[hud_cutoff:, :] = False
    excl[:, :6] = False
    excl[:, -6:] = False

    # Szerokie proby na "nie-poziome" jasne kolory
    for label, mask_def in [
        ("ORANGE(G95)", (r>195) & (g>95) & (g<210) & (b<75) & ((r-b)>130)),
        ("ORANGE(G70)", (r>190) & (g>70) & (g<210) & (b<75) & ((r-b)>120)),
        ("RED_CURSOR",  (r>195) & (g>30) & (g<95)  & (b<60) & ((r-b)>140)),
        ("YELLOW",      (r>210) & (g>180) & (b<80)  & ((r-g)<80)),
    ]:
        mask = mask_def & excl
        n = int(mask.sum())
        if n < 3 or n > 200:
            continue

        rows = np.where(mask.sum(axis=1) > 0)[0]
        cols = np.where(mask.sum(axis=0) > 0)[0]
        if len(rows) == 0 or len(cols) == 0:
            continue

        row_span = int(rows[-1] - rows[0]) + 1
        col_span = int(cols[-1] - cols[0]) + 1

        # Odfiltruj poziome linie (HP bary): col_span > 5 * row_span
        if col_span > 5 * max(row_span, 1):
            continue

        cx = int(np.median(cols))
        cy = int(np.median(rows))
        src_x = int(cx * scale_factor)

        # Sredni kolor w klastrze
        r_vals = r[mask]
        g_vals = g[mask]
        b_vals = b[mask]

        print(f"t={t:5.1f}s | {label:14s} | n={n:3d}px | "
              f"span={col_span}x{row_span} | "
              f"scaled_x={cx:3d} (src={src_x:4d}px) | "
              f"RGB=({int(r_vals.mean())},{int(g_vals.mean())},{int(b_vals.mean())})")

print()
print("DONE")
