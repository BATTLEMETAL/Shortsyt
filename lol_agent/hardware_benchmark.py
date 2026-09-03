"""
Shortsyt — Skaner Systemu i Benchmark Sprzętowy
Automatycznie bada podzespoły komputera (CPU, GPU, VRAM, RAM, enkodery FFmpeg)
i generuje zoptymalizowany profil wydajnościowy dla renderera oraz silnika AI/OCR.
"""
import os
import sys
import json
import platform
import subprocess
import multiprocessing
import ctypes
from pathlib import Path
from typing import Dict, Any, Tuple

PROFILE_FILE = Path(__file__).resolve().parent.parent / "data" / "system_hardware_profile.json"


def _get_ram_info_gb() -> Tuple[float, float]:
    """Zwraca (całkowity RAM GB, dostępny RAM GB)."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return round(vm.total / (1024**3), 1), round(vm.available / (1024**3), 1)
    except Exception:
        pass

    # Windows Native fallback via GlobalMemoryStatusEx
    if platform.system() == "Windows":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024**3), 1), round(stat.ullAvailPhys / (1024**3), 1)
        except Exception:
            pass

    return 16.0, 8.0  # Safe default


def _get_gpu_info() -> Dict[str, Any]:
    """Wykrywa dedykowaną kartę graficzną, pamięć VRAM i enkodery."""
    gpu_info = {
        "name": "Zintegrowana grafika / CPU",
        "vendor": "CPU",
        "vram_gb": 0.0,
        "has_nvidia": False,
        "has_amd": False,
        "has_intel": False,
        "encoder": "libx264",
    }

    # 1. Sprawdź nvidia-smi
    try:
        r_smi = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3
        )
        if r_smi.returncode == 0 and r_smi.stdout.strip():
            lines = r_smi.stdout.strip().split("\n")
            if lines:
                parts = lines[0].split(",")
                gpu_name = parts[0].strip()
                vram_mb = float(parts[1].strip()) if len(parts) > 1 else 4096.0
                gpu_info["name"] = gpu_name
                gpu_info["vendor"] = "NVIDIA"
                gpu_info["vram_gb"] = round(vram_mb / 1024.0, 1)
                gpu_info["has_nvidia"] = True
                gpu_info["encoder"] = "h264_nvenc"
                return gpu_info
    except Exception:
        pass

    # 2. Sprawdź enkodery FFmpeg
    try:
        r_ff = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=4)
        ff_out = r_ff.stdout or ""
        if "h264_nvenc" in ff_out:
            gpu_info["has_nvidia"] = True
            gpu_info["encoder"] = "h264_nvenc"
            gpu_info["vendor"] = "NVIDIA"
            gpu_info["name"] = "NVIDIA GeForce GPU (NVENC)"
            gpu_info["vram_gb"] = 6.0
            return gpu_info
        elif "h264_amf" in ff_out:
            gpu_info["has_amd"] = True
            gpu_info["encoder"] = "h264_amf"
            gpu_info["vendor"] = "AMD"
            gpu_info["name"] = "AMD Radeon GPU (AMF)"
            gpu_info["vram_gb"] = 4.0
            return gpu_info
        elif "h264_qsv" in ff_out:
            gpu_info["has_intel"] = True
            gpu_info["encoder"] = "h264_qsv"
            gpu_info["vendor"] = "Intel"
            gpu_info["name"] = "Intel GPU (QuickSync)"
            gpu_info["vram_gb"] = 2.0
            return gpu_info
    except Exception:
        pass

    return gpu_info


def _get_cpu_name() -> str:
    """Pobiera czytelną nazwę procesora."""
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            if cpu_name:
                return cpu_name.strip()
        except Exception:
            pass
    return platform.processor() or f"{multiprocessing.cpu_count()} Cores CPU"


def benchmark_and_tune_system() -> Dict[str, Any]:
    """
    Skanuje system, klasyfikuje wydajność PC (Tier 1 / 2 / 3) i zapisuje optymalne parametry renderera.
    """
    cores = multiprocessing.cpu_count()
    cpu_name = _get_cpu_name()
    ram_total_gb, ram_avail_gb = _get_ram_info_gb()
    gpu_info = _get_gpu_info()

    # Klasyfikacja Tieru:
    # Tier 1: Mocny PC (High-End)
    # Tier 2: Średni PC (Mid-Range)
    # Tier 3: Słaby / Podstawowy PC (Entry-Level)
    
    if (gpu_info["has_nvidia"] and gpu_info["vram_gb"] >= 5.5) or (cores >= 8 and ram_total_gb >= 15.0 and gpu_info["encoder"] != "libx264"):
        tier = "high"
        tier_label = "Mocny PC (High-End 🚀)"
        tier_description = "Maksymalna wydajność — akceleracja sprzętowa GPU NVENC, 60 FPS, najwyższa jakość CRF 17, równoległy OCR."
        
        encoder_args = ["-c:v", gpu_info["encoder"], "-preset", "p5", "-tune", "hq", "-cq", "17", "-b:v", "0", "-pix_fmt", "yuv420p"]
        max_ocr_workers = min(12, cores)
        render_fps = 60
        ocr_sample_fps = 3.0
        render_threads = 0  # auto
        enable_heavy_filters = True

    elif (gpu_info["encoder"] in ("h264_nvenc", "h264_amf", "h264_qsv")) or (cores >= 6 and ram_total_gb >= 11.0):
        tier = "medium"
        tier_label = "Średni PC (Zbalansowany ⚡)"
        tier_description = "Optymalna płynność i jakość — akceleracja GPU, 60 FPS, zrównoważony czas renderowania."
        
        if gpu_info["encoder"] == "h264_nvenc":
            encoder_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"]
        elif gpu_info["encoder"] == "h264_amf":
            encoder_args = ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cbr", "-b:v", "14M", "-pix_fmt", "yuv420p"]
        elif gpu_info["encoder"] == "h264_qsv":
            encoder_args = ["-c:v", "h264_qsv", "-preset", "fast", "-global_quality", "20", "-pix_fmt", "yuv420p"]
        else:
            encoder_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", str(min(8, cores)), "-pix_fmt", "yuv420p"]

        max_ocr_workers = min(6, cores)
        render_fps = 60
        ocr_sample_fps = 2.0
        render_threads = min(8, cores)
        enable_heavy_filters = True

    else:
        tier = "low"
        tier_label = "Podstawowy / Słaby PC (Oszczędny 🛡️)"
        tier_description = "Profil ultra-lekki — zminimalizowane obciążenie procesora, szybki preset 'veryfast', próbkowanie klatek 1.5 fps."
        
        encoder_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-threads", str(max(2, cores - 1)), "-pix_fmt", "yuv420p"]
        max_ocr_workers = max(2, min(4, cores - 1))
        render_fps = 60
        ocr_sample_fps = 1.5
        render_threads = max(2, cores - 1)
        enable_heavy_filters = False

    profile = {
        "scanned_at": _get_now_iso(),
        "tier": tier,
        "tier_label": tier_label,
        "tier_description": tier_description,
        "hardware": {
            "cpu_name": cpu_name,
            "cpu_cores": cores,
            "ram_total_gb": ram_total_gb,
            "ram_available_gb": ram_avail_gb,
            "gpu_name": gpu_info["name"],
            "gpu_vendor": gpu_info["vendor"],
            "vram_gb": gpu_info["vram_gb"],
            "detected_encoder": gpu_info["encoder"],
            "os_version": f"{platform.system()} {platform.release()}",
        },
        "tuned_settings": {
            "encoder": gpu_info["encoder"],
            "encoder_args": encoder_args,
            "render_fps": render_fps,
            "render_threads": render_threads,
            "ocr_sample_fps": ocr_sample_fps,
            "max_ocr_workers": max_ocr_workers,
            "enable_heavy_filters": enable_heavy_filters,
        }
    }

    # Zapisz profil
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    return profile


def load_tuned_hardware_profile() -> Dict[str, Any]:
    """Wczytuje zapisany profil sprzętowy lub uruchamia skanowanie jeśli brak."""
    if PROFILE_FILE.exists():
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return benchmark_and_tune_system()


def _get_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    p = benchmark_and_tune_system()
    print("=== WYNIK SKANU SYSTEMU ===")
    print(f"Tier: {p['tier_label']}")
    print(f"CPU: {p['hardware']['cpu_name']} ({p['hardware']['cpu_cores']} rdzeni)")
    print(f"RAM: {p['hardware']['ram_total_gb']} GB")
    print(f"GPU: {p['hardware']['gpu_name']} (Enkoder: {p['hardware']['detected_encoder']})")
    print("Parametry renderera:", " ".join(p['tuned_settings']['encoder_args']))
