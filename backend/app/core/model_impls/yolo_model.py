from typing import Any

from pathlib import Path
import torch
from loguru import logger
from ultralytics import YOLO

from app.core.interfaces.model_interface import ModelInterface
from app.core.panel_cache import gold


def preview_main_valid(box, candidates, names, image):
    """Weak main text boxes need independent geometry and the fixed gold stripe."""
    x, y, w, h = map(float, box)
    if min(w, h) <= 0:
        return False
    sub = next((b for b, c, p in candidates if names[int(c)] == 'relic-sub-stat' and float(p) >= .8), None)
    title = next((b for b, c, p in candidates if names[int(c)] == 'relic-title' and float(p) >= .8), None)
    if sub is None or title is None:
        return False
    sx, sy, sw, sh = map(float, sub)
    if not (abs(sx-x) < w*.2 and .7 < sw/w < 1.3 and h < sy-y < h*5 and float(title[1]) < y-h):
        return False
    ih, iw = image.shape[:2]
    left, right = int((x-w*.75)*iw), int((x-w*.5)*iw)
    top, bottom = int((y-h*.5)*ih), int((y+h*.5)*ih)
    if min(left, top) < 0 or right > iw or bottom > ih or right <= left or bottom <= top:
        return False
    mask = gold(image[top:bottom, left:right])
    return bool(mask.sum(axis=0).max() >= mask.shape[0]*.6)


class YOLOModel(ModelInterface[Any, Any]):
    """YOLO model for object detection."""

    @staticmethod
    def get_name() -> str:
        return "yolo_model"

    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None

    def load(self) -> None:
        """Load the YOLO model."""
        if not Path(self.model_path).is_file():
            raise FileNotFoundError(f"缺少本地检测模型: {self.model_path}")
        self.model = YOLO(self.model_path)
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(device)
        logger.debug(f"YOLO model loaded on device: {device}")

    def predict(self, input_data: Any) -> Any:
        """Perform object detection on the input data."""
        img_np = input_data['image']
        window_h = input_data['window_info'].height
        window_w = input_data['window_info'].width

        # Lower-confidence substat boxes are usable for preview only. Other
        # regions, especially the discard target, retain the original threshold.
        detection_result = self.model.predict(source=img_np, imgsz=640, conf=0.5, save=False, verbose=False)
        candidates = [(box, cls, confidence) for result in detection_result
                      for box, cls, confidence in zip(result.boxes.xywhn, result.boxes.cls, result.boxes.conf)]
        required = {'relic-title', 'relic-main-stat', 'relic-sub-stat'}
        found = {self.model.names[int(cls)] for _, cls, confidence in candidates
                 if float(confidence) >= (.5 if self.model.names[int(cls)] == 'relic-sub-stat' else .8)}
        missing = required - found
        # First-item bootstrap has no cache to fall back to. Retry only missing
        # text regions at higher resolution; never replace established boxes or
        # use this preview-only recovery for the discard click target.
        if missing and input_data.get('allow_multiscale', False):
            recovered = self.model.predict(source=img_np, imgsz=1280, conf=.5, save=False, verbose=False)
            candidates += [(box, cls, confidence) for result in recovered
                           for box, cls, confidence in zip(result.boxes.xywhn, result.boxes.cls, result.boxes.conf)
                           if self.model.names[int(cls)] in missing]

        sub_regions = {}
        strong_main = any(self.model.names[int(c)] == 'relic-main-stat' and float(p) >= .8 for _, c, p in candidates)

        for box, cls, confidence in candidates:
            x_center, y_center, width, height = box[:4]
            cls = self.model.names[int(cls)]
            confidence = float(confidence)
            if confidence < (0.5 if cls == 'relic-sub-stat' else 0.8):
                if not (input_data.get('allow_multiscale', False) and cls == 'relic-main-stat'
                        and not strong_main and confidence >= .65
                        and preview_main_valid(box, candidates, self.model.names, img_np)):
                    continue

            # Transform image using original dimensions
            x1 = int((x_center - width / 2) * window_w)
            y1 = int((y_center - height / 2) * window_h)
            x2 = int((x_center + width / 2) * window_w)
            y2 = int((y_center + height / 2) * window_h)

            x_center = int(x_center * window_w)
            y_center = int(y_center * window_h)
            width = int(width * window_w)
            height = int(height * window_h)
            unpadded = img_np[y1:y2, x1:x2]
            unpadded_rect = [x1, y1, x2-x1, y2-y1]

            if cls == 'relic-main-stat' and cls in missing and input_data.get('allow_multiscale', False):
                # The higher-resolution legacy box may stop before the percent
                # sign. Preserve a small margin instead of guessing a missing %.
                x1 = max(0, x1 - round(width * .04))
                x2 = min(window_w, x2 + round(width * .08))
                y1 = max(0, y1 - round(height * .15))
                y2 = min(window_h, y2 + round(height * .15))
                x_center, y_center = (x1+x2)//2, (y1+y2)//2
                width, height = x2-x1, y2-y1

            if cls == 'relic-sub-stat':
                # Legacy detector often clips the top of the first numeric row.
                padding = max(2, round(height * .1))
                y1 = max(0, y1 - padding)
                y2 = min(window_h, y2 + padding // 2)
                y_center = (y1 + y2) // 2
                height = y2 - y1

            sub_region_img = img_np[y1:y2, x1:x2]

            logger.debug(
                f"Detected {cls} with x_center: {x_center}, y_center: {y_center}, width: {width}, height: {height}")

            if cls not in sub_regions:
                sub_regions[cls] = {
                    'crop_rect': [x1, y1, x2-x1, y2-y1],
                    'unpadded_rect': unpadded_rect,
                    'image_unpadded': unpadded,
                    'confidence': confidence,
                    'image': sub_region_img,
                    'box': {
                        'x_center': x_center,
                        'y_center': y_center,
                        'width': width,
                        'height': height
                    }
                }

        sub = sub_regions.get('relic-sub-stat')
        main = sub_regions.get('relic-main-stat')
        if sub and sub['confidence'] < .8:
            # Preview fallback must remain below and aligned with the main stat.
            b = sub['box']; a = main['box'] if main else None
            if (not a or abs(b['x_center'] - a['x_center']) > a['width'] * .2
                    or not .7 <= b['width'] / a['width'] <= 1.3
                    or not a['height'] < b['y_center'] - a['y_center'] < a['height'] * 4
                    or not a['height'] * 2 <= b['height'] <= a['height'] * 6):
                del sub_regions['relic-sub-stat']
        return sub_regions
