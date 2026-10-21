"""Offline startup/inference smoke test; no game capture or game input."""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
original_connect = socket.socket.connect


def offline_connect(sock, address):
    if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1', 'localhost'):
        return original_connect(sock, address)
    raise RuntimeError(f'External networking forbidden during offline smoke test: {address}')


socket.socket.connect = offline_connect

from fastapi.testclient import TestClient
from main import app
from app.core.managers.model_manager import ModelManager
from app.core.model_impls.ocr_model import OCRModel
from app.core.model_impls.yolo_model import YOLOModel
from app.core.data_models.model_io import WindowInfoOutput
import numpy as np

with TestClient(app) as client:
    assert client.get('/review').status_code == 200
    assert client.get('/rating-template/init').status_code == 200
    assert client.post('/review/execute', json={'session_id': 'invalid', 'selected': ['0']}).status_code == 409
    blank = np.zeros((720, 1280, 3), dtype=np.uint8)
    ModelManager().get_model(OCRModel).predict(blank)
    ModelManager().get_model(YOLOModel).predict(dict(image=blank, window_info=WindowInfoOutput(width=1280, height=720, left=0, top=0)))
print('OFFLINE_BACKEND_AND_INFERENCE_OK')
