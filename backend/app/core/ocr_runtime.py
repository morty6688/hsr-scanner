"""Opt-in project-local Paddle GPU runtime; no startup downloads/installations."""
import json
import os
from pathlib import Path
import sys

from app.constant import LOCAL_DATA_FOLDER

_dll_handles = []


def configure_runtime():
    root = Path(LOCAL_DATA_FOLDER)
    config = root / 'ocr-runtime.json'
    mode = os.environ.get('HSR_OCR_DEVICE')
    if mode is None:
        mode = json.loads(config.read_text(encoding='utf-8')).get('device', 'cpu') if config.is_file() else 'cpu'
    if mode not in ('cpu', 'gpu', 'auto'):
        raise ValueError('OCR device 必须为 cpu、gpu 或 auto')
    runtime = root / 'gpu-runtime'
    if mode == 'gpu' and not (runtime / 'paddle').is_dir():
        raise RuntimeError('缺少 GPU OCR 运行库，请手动运行 tools/install-gpu.ps1')
    if mode != 'cpu' and (runtime / 'paddle').is_dir():
        sys.path.insert(0, str(runtime))
        directories = sorted({p.parent for p in runtime.rglob('*.dll')})
        # Keep handles alive for Python 3.8+ DLL discovery. PATH also covers
        # CUDA libraries opened dynamically by Paddle/cuDNN with LoadLibrary.
        os.environ['PATH'] = os.pathsep.join(map(str, directories)) + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            _dll_handles.extend(os.add_dll_directory(str(p)) for p in directories)
    return mode
