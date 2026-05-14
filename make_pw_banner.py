"""
make_pw_banner.py — Generator baneru YouTube dla Salon Pretty Woman
Uwzględnia strefy bezpieczne YouTube:
  - TV (cały obraz):     2560x1440
  - Desktop/web:         2560x423  (y: 508–931)
  - Wszystkie urządzenia: 1546x423  (x: 507–2053, y: 508–931)
Cały kluczowy content musi być w y: 508–931.
"""
import os, random, sys
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding='utf-8')

OUTPUT = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman\banner_prettywoman.png"
W, H = 2560, 1440

# YouTube safe zones
SAFE_Y1, SAFE_Y2 = 508, 931   # strefa bezpieczna pionowo
SAFE_CY = (SAFE_Y1 + SAFE_Y2) // 2  # = 719

# ─── Kolory ───────────────────────────────────────────────────────────────────
BG_TOP    = (12,  5,  18)
BG_MID    = (28, 10,  26)
BG_BOT    = (18,  6,  20)
GOLD      = (212, 175,  55)
GOLD_LT   = (245, 215, 120)
ROSE      = (200,  85, 130)
CREAM     = (255, 248, 238)

def lerp(c1, c2, t):
    return tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))

# ─── Tło (gradient pionowy) ───────────────────────────────────────────────────
img  = Image.new("RGB", (W, H))
draw = ImageDraw.Draw(img)

for y in range(H):
    t = y / H
    if t < 0.35:
        c = lerp(BG_TOP, BG_MID, t/0.35)
    else:
        c = lerp(BG_MID, BG_BOT, (t-0.35)/0.65)
    draw.line([(0,y),(W,y)], fill=c)

# ─── Poświaty (RGBA overlay) ───────────────────────────────────────────────────
glow = Image.new("RGBA", (W, H), (0,0,0,0))
gd   = ImageDraw.Draw(glow)

def radial_glow(d, cx, cy, radius, color, max_alpha):
    for r in range(radius, 0, -6):
        a = int(max_alpha * (r / radius))
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*color, a))

# Centralny złoty blask w centrum safe zone
radial_glow(gd, W//2, SAFE_CY, 520, GOLD_LT, 28)
# Akcenty po bokach (widoczne na TV)
radial_glow(gd, 180,    SAFE_CY, 280, ROSE,    18)
radial_glow(gd, W-180,  SAFE_CY, 280, GOLD,    18)
# Górny i dolny blask (TV decoration, poza safe zone)
radial_glow(gd, W//2,  180,  400, (80, 20, 60), 15)
radial_glow(gd, W//2, 1260,  400, (80, 20, 60), 15)

img  = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
draw = ImageDraw.Draw(img)

# ─── Linie dekoracyjne ────────────────────────────────────────────────────────
# Nad i pod strefą bezpieczną (widoczne wszędzie)
for off, w, a in [(0,2,255),(6,1,130),(12,1,60)]:
    g = tuple(int(x * a/255) for x in GOLD)
    draw.line([(60, SAFE_Y1-off), (W-60, SAFE_Y1-off)], fill=g, width=w)
    draw.line([(60, SAFE_Y2+off), (W-60, SAFE_Y2+off)], fill=g, width=w)

# Różowy pasek akcentujący (środek strefy)
accent_y = SAFE_CY + 88
draw.line([(W//2 - 560, accent_y), (W//2 + 560, accent_y)], fill=ROSE, width=3)
draw.line([(W//2 - 400, accent_y+6), (W//2 + 400, accent_y+6)], fill=(*ROSE, 120), width=1)

# ─── Diamenty dekoracyjne ────────────────────────────────────────────────────
def diamond(draw, cx, cy, s, col):
    draw.polygon([(cx,cy-s),(cx+s,cy),(cx,cy+s),(cx-s,cy)], fill=col)

diamond(draw, W//2,      SAFE_Y1-26, 11, GOLD)
diamond(draw, W//2,      SAFE_Y2+26, 11, GOLD)
diamond(draw, 60,        SAFE_CY,     8, GOLD_LT)
diamond(draw, W-60,      SAFE_CY,     8, GOLD_LT)
diamond(draw, W//2-700,  SAFE_CY,     5, (*ROSE,180))
diamond(draw, W//2+700,  SAFE_CY,     5, (*ROSE,180))

# ─── Gwiazdki ────────────────────────────────────────────────────────────────
random.seed(99)
for _ in range(140):
    rx, ry, rs = random.randint(0,W), random.randint(0,H), random.randint(1,3)
    col = GOLD_LT if random.random()>0.5 else ROSE
    a   = random.randint(30, 160)
    draw.ellipse([rx-rs,ry-rs,rx+rs,ry+rs], fill=(*col,a))

# ─── Fonty ───────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    paths = [
        "C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/arialbd.ttf"  if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()

fnt_salon = load_font(82)        # "SALON"
fnt_main  = load_font(210, True) # "PRETTY WOMAN"
fnt_sub   = load_font(50)        # tagline
fnt_handle= load_font(40)        # @handle

# ─── Rysowanie tekstu (wyśrodkowany poziomo) ──────────────────────────────────
def centered(draw, y, text, font, fill, shadow=True):
    bb = draw.textbbox((0,0), text, font=font)
    tw = bb[2]-bb[0]
    x  = (W - tw) // 2
    if shadow:
        draw.text((x+3, y+3), text, font=font, fill=(0,0,0))
    draw.text((x, y), text, font=font, fill=fill)
    return tw, x   # zwróć szerokość i pozycję x

# Rozkład w safe zone (y: 508–931, środek 719):
#   "SALON"        → y=525   (tuż nad)
#   "PRETTY WOMAN" → y=600   (główny, duży)
#   złota linia    → y=823
#   różowy pasek   → y=831
#   tagline        → y=840
#   @handle        → y=893
centered(draw, 528,  "S  A  L  O  N",                                     fnt_salon, GOLD_LT)
centered(draw, 600,  "PRETTY WOMAN",                                       fnt_main,  CREAM)

# Linia podkreślenia pod PRETTY WOMAN
bb2   = draw.textbbox((0,0), "PRETTY WOMAN", font=fnt_main)
tw2   = bb2[2]-bb2[0]
lx2   = (W - tw2) // 2
draw.line([(lx2, 825), (lx2+tw2, 825)], fill=GOLD, width=3)

centered(draw, 845,  "Afroloki  •  Warkoczyki  •  Szkolenia  •  Świdnica", fnt_sub,   ROSE)
centered(draw, 892,  "@SalonPrettyWoman",                                  fnt_handle, GOLD_LT, shadow=False)

# ─── Zapis ───────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
img.save(OUTPUT, "PNG")
print(f"GOTOWE: {OUTPUT}  ({W}x{H}px)")
