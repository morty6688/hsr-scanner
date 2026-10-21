from pathlib import Path

from typing import Any, Optional, Union, List

from app.core.ocr_runtime import configure_runtime

OCR_DEVICE = configure_runtime()
from paddleocr import PaddleOCR
import paddle
from loguru import logger
import cv2
import numpy as np
import copy

from app.constant import PADDLE_DET_FOLDER, PADDLE_CLS_FOLDER, PADDLE_REC_FOLDER, PADDLE_FOLDER
from app.core.interfaces.model_interface import ModelInterface


class OCRModel(ModelInterface[Any, Union[List[Union[None, List[List], List]], List]]):
    @staticmethod
    def get_name() -> str:
        return "ocr_model"

    def __init__(self):
        self.model: Optional[PaddleOCR] = None
        self.trace = []
        self.device = 'cpu'

    def load(self) -> None:
        """Initialize OCR settings if necessary."""
        det = Path(PADDLE_FOLDER) / 'ch/det'
        rec = Path(PADDLE_FOLDER) / 'ch/rec'
        for folder in (det, rec, Path(PADDLE_CLS_FOLDER)):
            for filename in ('inference.pdmodel', 'inference.pdiparams'):
                if not (folder / filename).is_file():
                    raise FileNotFoundError(f'缺少本地模型: {folder / filename}；请手动运行 tools/prepare_local_assets.py')
        available = paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0
        if OCR_DEVICE == 'gpu' and not available:
            raise RuntimeError('GPU OCR 已启用，但 Paddle 无法使用 CUDA；请检查运行库，或设置 HSR_OCR_DEVICE=cpu')
        use_gpu = OCR_DEVICE != 'cpu' and available
        self.device = 'gpu' if use_gpu else 'cpu'
        logger.info(f'OCR device: {self.device}; Paddle {paddle.__version__}')
        self.model = PaddleOCR(
            lang='ch',
            use_gpu=use_gpu,
            gpu_id=0,
            gpu_mem=512,
            enable_mkldnn=False,
            show_log=False,
            det_model_dir=str(det),
            cls_model_dir=PADDLE_CLS_FOLDER,
            rec_model_dir=str(rec)
        )

    def predict(self, input_data: Any, force_reread=False) -> Union[List[Union[None, List[List], List]], List]:
        """Perform OCR on the input data."""
        result = self.model.ocr(input_data, cls=False)
        original = copy.deepcopy(result)
        repaired = False
        # Re-read low-confidence detected lines as isolated, high-contrast text.
        # Keep coordinates in the original image for row/color validation.
        for page in result or []:
            for line in page or []:
                if float(line[1][1]) >= .95 and not force_reread:
                    continue
                points = np.asarray(line[0])
                x1, y1 = np.maximum(points.min(axis=0).astype(int) - 3, 0)
                x2, y2 = np.minimum(points.max(axis=0).astype(int) + 4, [input_data.shape[1], input_data.shape[0]])
                crop = input_data[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
                variant = cv2.cvtColor(255 - gray, cv2.COLOR_GRAY2BGR)
                variant = cv2.copyMakeBorder(variant, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255))
                reread = self.model.ocr(variant, det=False, cls=False)
                if reread and reread[0] and float(reread[0][0][1]) >= .95:
                    line[1] = reread[0][0]
                    repaired = True
        if repaired:
            self.trace.append(original)
        self.trace.append(result)
        return result
