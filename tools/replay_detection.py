"""Replay saved images through local detection and OCR without game input."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import cv2
from fastapi.testclient import TestClient
from main import app
from app.core.managers.model_manager import ModelManager
from app.core.managers.stage_manager import StageManager
from app.core.model_impls.yolo_model import YOLOModel
from app.core.data_models.model_io import WindowInfoOutput
from app.core.data_models.pipeline_context import PipelineContext
from app.constant import AUTO_DETECT_RELIC_BOX

with TestClient(app):
    for name in sys.argv[1:]:
        image = cv2.imread(name)
        if image is None:
            raise ValueError('Cannot read: ' + name)
        shot = dict(image=image, window_info=WindowInfoOutput(width=image.shape[1], height=image.shape[0], left=0, top=0))
        regions = ModelManager().get_model(YOLOModel).predict(shot)
        context = PipelineContext(pipeline_id='replay', meta_data={AUTO_DETECT_RELIC_BOX: True},
            data={'screenshot_stage': shot, 'detection_stage': regions})
        result = asyncio.run(StageManager().get_stage('ocr_stage').process(context))
        print(json.dumps(dict(file=name, confidence={k: v['confidence'] for k, v in regions.items()},
            success=result.success, error=result.error,
            relic=result.data.model_dump() if result.success else None), ensure_ascii=False))
