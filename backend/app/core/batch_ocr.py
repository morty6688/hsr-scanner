"""Segment fixed horizontal UI text with pixel projections, then batch recognition."""
import cv2
import numpy as np


def text_rows(image, golden=False, expected=None):
    b, g, r = [image[:, :, i].astype(int) for i in range(3)]
    mask = ((r > 130) & (g > 80) & (r-b > 55) & (g-b > 25)) if golden else (
        (image.max(axis=2).astype(int)-image.min(axis=2) < 35) & (image.min(axis=2) > 70))
    occupied = mask.sum(axis=1) >= 3
    indices = np.flatnonzero(occupied)
    groups = []
    for y in indices:
        if groups and y - groups[-1][-1] <= 3:
            groups[-1].append(y)
        else:
            groups.append([y])
    result = []
    for group in groups:
        y1, y2 = group[0], group[-1]+1
        if y2-y1 < max(7, image.shape[0]*.025):
            continue
        xs = np.flatnonzero(mask[y1:y2].any(axis=0))
        if len(xs) < 3:
            continue
        x1, x2 = int(xs[0]), int(xs[-1])+1
        # Reject horizontal rules and clipping at a region boundary.
        if y2-y1 < (x2-x1)*.025 or y1 == 0 or y2 == image.shape[0]:
            continue
        x1, y1 = max(0, x1-3), max(0, y1-3)
        x2, y2 = min(image.shape[1], x2+3), min(image.shape[0], y2+3)
        result.append([int(x1), int(y1), int(x2), int(y2)])
    if expected is not None and len(result) != expected:
        raise ValueError('批量 OCR 行数不符')
    return result


def batch_read(model, title, main, subs):
    split_main, split_sub = int(main.shape[1]*.7), int(subs.shape[1]*.7)
    images = [title, main[:, :split_main], main[:, split_main:], subs[:, :split_sub], subs[:, split_sub:]]
    boxes = [text_rows(img, golden=i < 3, expected=1 if i < 3 else 4) for i, img in enumerate(images)]
    # Names and values must occupy the same rows; never pair by count alone.
    for name, value in zip(boxes[3], boxes[4]):
        if abs((name[1]+name[3])-(value[1]+value[3]))/2 > max(name[3]-name[1], value[3]-value[1])*.35:
            raise ValueError('副属性名称与数值行未对齐')
    crops = []
    for img, rects in zip(images, boxes):
        for x1,y1,x2,y2 in rects:
            gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            gray = 255 - cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
            crop = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            crops.append(cv2.copyMakeBorder(crop, 5, 5, 5, 5, cv2.BORDER_CONSTANT, value=(255,255,255)))
    texts, _ = model.model.text_recognizer(crops)
    if len(texts) != len(crops):
        raise ValueError('批量 OCR 返回数量不符')
    groups = []
    index = 0
    for rects in boxes:
        lines = []
        for x1,y1,x2,y2 in rects:
            text, score = texts[index]; index += 1
            if score < .95:
                raise ValueError('批量 OCR 置信度不足')
            lines.append([[[x1,y1],[x2,y1],[x2,y2],[x1,y2]], (text, float(score))])
        groups.append([lines])
    return groups, images[3]
