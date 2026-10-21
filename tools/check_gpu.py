"""Exercise CUDA and local OCR models without game input or downloads."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.model_impls.ocr_model import OCRModel
import paddle
import numpy as np
import cv2

assert paddle.is_compiled_with_cuda(), 'CPU Paddle was loaded'
assert paddle.device.cuda.device_count() > 0, 'No CUDA device available'
paddle.set_device('gpu:0')
assert float((paddle.ones([2, 2]) @ paddle.ones([2, 2])).sum().numpy()) == 8
model = OCRModel()
model.load()
assert model.device == 'gpu'
image = np.zeros((100, 320, 3), dtype=np.uint8)
cv2.putText(image, '12345', (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
result = model.predict(image)
assert any('12345' == line[1][0] for page in result or [] for line in page or []), result
print('GPU_OCR_OK', paddle.__version__, paddle.version.cuda(), paddle.version.cudnn())
