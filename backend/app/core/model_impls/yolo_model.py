from typing import Any

from pathlib import Path
import torch
from loguru import logger
from ultralytics import YOLO

from app.core.interfaces.model_interface import ModelInterface


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
        boxes = detection_result[0].boxes.xywhn if len(detection_result) > 0 else []
        classes = detection_result[0].boxes.cls if len(detection_result) > 0 else []
        confidences = detection_result[0].boxes.conf if len(detection_result) > 0 else []

        sub_regions = {}

        for box, cls, confidence in zip(boxes, classes, confidences):
            x_center, y_center, width, height = box[:4]
            cls = self.model.names[int(cls)]
            confidence = float(confidence)
            if confidence < (0.5 if cls == 'relic-sub-stat' else 0.8):
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
