import os, sys, subprocess, multiprocessing
from typing import List, Tuple

_CACHED_ENCODER = None
_CACHED_SUMMARY = None

def detect_hardware() -> Tuple[str, str]:
    global _CACHED_ENCODER, _CACHED_SUMMARY
    if _CACHED_ENCODER is not None:
        return _CACHED_ENCODER, _CACHED_SUMMARY

    cpu_cores = multiprocessing.cpu_count()
    detected_encoder = 'libx264'
    gpu_name = 'CPU'

    try:
        r = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=5)
        enc_output = r.stdout
    except Exception:
        enc_output = ''

    if 'h264_nvenc' in enc_output:
        try:
            r_smi = subprocess.run(
                ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                capture_output=True, text=True, timeout=3
            )
            if r_smi.returncode == 0 and r_smi.stdout.strip():
                gpu_name = r_smi.stdout.strip().split('\n')[0]
                detected_encoder = 'h264_nvenc'
            else:
                detected_encoder = 'h264_nvenc'
                gpu_name = 'NVIDIA GPU (NVENC)'
        except Exception:
            detected_encoder = 'h264_nvenc'
            gpu_name = 'NVIDIA GPU (NVENC)'

    elif 'h264_amf' in enc_output:
        detected_encoder = 'h264_amf'
        gpu_name = 'AMD GPU (AMF)'

    elif 'h264_qsv' in enc_output:
        detected_encoder = 'h264_qsv'
        gpu_name = 'Intel GPU (QuickSync)'

    _CACHED_ENCODER = detected_encoder
    _CACHED_SUMMARY = f'{gpu_name} [{detected_encoder}] | {cpu_cores} CPU Cores'
    return _CACHED_ENCODER, _CACHED_SUMMARY

def get_optimal_encoder_args(quality: str = 'high') -> List[str]:
    enc, _ = detect_hardware()

    if enc == 'h264_nvenc':
        if quality == 'high':
            cq = '18'
        elif quality == 'draft':
            cq = '23'
        else:  # ultra-fast preview
            cq = '28'
        return ['-c:v', 'h264_nvenc', '-preset', 'p4', '-tune', 'hq', '-cq', cq, '-b:v', '0', '-pix_fmt', 'yuv420p']

    elif enc == 'h264_amf':
        bitrate = '18M' if quality == 'high' else ('12M' if quality == 'draft' else '8M')
        return ['-c:v', 'h264_amf', '-quality', 'speed', '-rc', 'cbr', '-b:v', bitrate, '-pix_fmt', 'yuv420p']

    elif enc == 'h264_qsv':
        q = '18' if quality == 'high' else ('22' if quality == 'draft' else '26')
        return ['-c:v', 'h264_qsv', '-preset', 'veryfast', '-global_quality', q, '-pix_fmt', 'yuv420p']

    else:
        crf = '18' if quality == 'high' else ('22' if quality == 'draft' else '26')
        return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', crf, '-threads', '0', '-pix_fmt', 'yuv420p']

if __name__ == '__main__':
    enc, summary = detect_hardware()
    print('Hardware detected:', summary)
    print('Optimal encoder args:', get_optimal_encoder_args())
