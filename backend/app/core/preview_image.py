"""Small previews; retain original PNGs for inspection and replay."""
import cv2
import numpy as np
from uuid import uuid4


def thumbnail_file(original):
    folder = original.parent / 'thumbnails'
    folder.mkdir(exist_ok=True)
    target = folder / (original.stem + '.jpg')
    if not target.exists():
        image = cv2.imdecode(np.fromfile(str(original), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('无法读取预览截图')
        ratio = min(1, 320/image.shape[1], 640/image.shape[0])
        image = cv2.resize(image, (max(1,round(image.shape[1]*ratio)), max(1,round(image.shape[0]*ratio))), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise ValueError('无法生成预览截图')
        temp = folder / (uuid4().hex + '.tmp')
        temp.write_bytes(encoded.tobytes())
        temp.replace(target)
    return target
