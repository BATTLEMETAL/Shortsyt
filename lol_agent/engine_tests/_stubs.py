"""Atrapy modułów, których nie ma poza komputerem Michała (konfiguracja, GPU), żeby testy logiki działały wszędzie."""
import sys, types, os, tempfile

def install(need_numpy_stub=False):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path: sys.path.insert(0, here)
    tmp = tempfile.mkdtemp(prefix="flikcut_test_")
    cfg = types.ModuleType("lol_config")
    cfg.LOL_MUSIC_DIR = tmp; cfg.LOL_TEMP_DIR = tmp
    cfg.OUTPUT_WIDTH, cfg.OUTPUT_HEIGHT, cfg.OUTPUT_FPS = 1080, 1920, 60
    cfg.MUSIC_VOLUME, cfg.GAME_AUDIO_VOLUME, cfg.SHORT_MAX_DURATION, cfg.SMOOTH_SLOWMO = 0.85, 0.65, 30.0, False
    cfg.ACTION_LABELS = {}
    sys.modules.setdefault("lol_config", cfg)
    hw = types.ModuleType("hardware_accel")
    hw.get_optimal_encoder_args = lambda quality="high": ["-c:v", "libx264", "-preset", "veryfast"]
    hw.detect_hardware = lambda: ("libx264", "cpu")
    sys.modules.setdefault("hardware_accel", hw)
    if need_numpy_stub and "numpy" not in sys.modules:
        try:
            import numpy  # noqa: F401
        except ImportError:
            np = types.ModuleType("numpy"); np.linspace = lambda a, b, n: [a + (b - a) * i / max(1, n - 1) for i in range(n)]
            np.ndarray = object
            sys.modules["numpy"] = np
    return tmp
