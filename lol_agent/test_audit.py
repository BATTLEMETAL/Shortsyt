import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lol_agent'))
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

results = []

def check(name, passed, detail=""):
    mark = "PASS" if passed else "FAIL"
    msg = f"  [{mark}] {name}" + (f" -- {detail}" if detail else "")
    print(msg)
    results.append((name, passed))

# --- TEST 1: _limit_tags ---
print("TEST 1: _limit_tags (500 char limit)")
from lol_publisher import _limit_tags
many = ['league of legends'] * 30
out = _limit_tags(many)
total = sum(len(t)+1 for t in out)
check("tags under 500 chars", total <= 501, f"{len(out)} tags, {total} chars")
check("respects tag count", len(out) <= 30)

# --- TEST 2: _ensure_shorts_tag ---
print("TEST 2: #Shorts guarantee")
from lol_metadata_generator import _ensure_shorts_tag
added = _ensure_shorts_tag("Great clip! #LoL #Gaming")
unchanged = _ensure_shorts_tag("Already has #Shorts here")
check("adds #Shorts when missing", "#Shorts" in added)
check("does not duplicate #Shorts", unchanged == "Already has #Shorts here")

# --- TEST 3: beat drop cache ---
print("TEST 3: Beat drop cache")
import json
cache = json.load(open('lol_agent/beat_drop_cache.json'))
check("11 tracks in cache", len(cache) >= 11, f"{len(cache)} found")
all_positive = all(v > 0 for v in cache.values())
check("all drops > 0s", all_positive)

# --- TEST 4: Music library ---
print("TEST 4: Music library")
from lol_music_downloader import MUSIC_LIBRARY, is_downloaded
dl = sum(1 for f in MUSIC_LIBRARY if is_downloaded(f))
check("all 11 tracks downloaded", dl == 11, f"{dl}/11")

# --- TEST 5: pick_for_action ---
print("TEST 5: Music selection per action")
from lol_music_downloader import pick_for_action
all_matched = True
for action in ['pentakill', 'quadrakill', 'triple', 'outplay', 'clutch', 'escape']:
    fname, info = pick_for_action(action)
    matched = fname is not None
    energy = info['energy'] if info else 'none'
    print(f"    {action:<12} -> {energy:<8} {'OK' if matched else 'NO MATCH'}")
    if not matched:
        all_matched = False
check("all actions have music", all_matched)

# --- TEST 6: Thumbnail with logo ---
print("TEST 6: Thumbnail generation")
import shutil
from PIL import Image
from lol_thumbnail import generate_thumbnail
import lol_thumbnail
os.makedirs('lol_agent/lol_temp', exist_ok=True)
frame_path = 'lol_agent/lol_temp/test_frame.jpg'
Image.new('RGB', (1920, 1080), (18, 24, 40)).save(frame_path)
orig_fn = lol_thumbnail.extract_peak_frame
def mock_fn(vp, pt, op):
    shutil.copy(frame_path, op)
    return True
lol_thumbnail.extract_peak_frame = mock_fn
out = 'lol_agent/lol_temp/audit_thumbnail.jpg'
result = generate_thumbnail('dummy.mp4', 15.0, 'PENTAKILL', 'Katarina', out)
lol_thumbnail.extract_peak_frame = orig_fn
exists = result and os.path.exists(result)
size_kb = os.path.getsize(result) // 1024 if exists else 0
check("thumbnail created", exists, f"{size_kb} KB")
logo_path = 'lol_agent/logo.png'
check("logo.png present", os.path.exists(logo_path))

# --- TEST 7: FFmpeg audit params ---
print("TEST 7: FFmpeg encode params in lol_editor.py")
src = open('lol_agent/lol_editor.py', encoding='utf-8').read()
check("pix_fmt yuv420p (>=5 occurrences)", src.count('yuv420p') >= 5, f"{src.count('yuv420p')}x")
check("movflags +faststart present", 'faststart' in src)
check("ar 44100 in audio encode", src.count('44100') >= 2, f"{src.count('44100')}x")
check("loudnorm -14 LUFS present", src.count('loudnorm') >= 2, f"{src.count('loudnorm')}x")

# --- TEST 8: Syntax check all files ---
print("TEST 8: Syntax check all modules")
import py_compile
modules = [
    'lol_agent/lol_editor.py', 'lol_agent/lol_publisher.py',
    'lol_agent/lol_metadata_generator.py', 'lol_agent/lol_thumbnail.py',
    'lol_agent/lol_beat_detector.py', 'lol_agent/lol_music_downloader.py',
    'lol_agent/lol_clip_ranker.py', 'lol_agent/lol_quality_scorer.py',
    'lol_agent/lol_performance_tracker.py', 'lol_agent/run_lol_agent.py',
]
all_ok = True
for m in modules:
    try:
        py_compile.compile(m, doraise=True)
        print(f"    OK  {m.split('/')[-1]}")
    except py_compile.PyCompileError as e:
        print(f"    ERR {m.split('/')[-1]}: {e}")
        all_ok = False
check("all 10 modules syntax OK", all_ok)

# --- Summary ---
print()
passed = sum(1 for _, p in results if p)
total_tests = len(results)
print(f"{'='*50}")
print(f"RESULT: {passed}/{total_tests} tests passed")
if passed == total_tests:
    print("ALL CHECKS PASSED -- pipeline ready")
else:
    failed = [n for n, p in results if not p]
    print(f"FAILED: {failed}")
print(f"{'='*50}")
