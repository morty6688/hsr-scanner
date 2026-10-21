"""Conservative color + explicit unlock-text recognition on OCR text boxes."""
import re
import numpy as np

PENDING = re.compile(r'[（(]\+3可激活[）)]')


def merge_rows(result):
    """Join OCR fragments of the same line, e.g. stat name + unlock suffix."""
    lines = sorted((result or [None])[0] or [], key=lambda line: np.asarray(line[0])[:, 1].mean())
    rows = []
    for line in lines:
        points = np.asarray(line[0])
        center = points[:, 1].mean()
        height = points[:, 1].max() - points[:, 1].min()
        if rows and abs(center - rows[-1][0]) < max(height, rows[-1][1]) * .5:
            rows[-1][2].append(line)
        else:
            rows.append([center, height, [line]])
    merged = []
    for _, _, fragments in rows:
        fragments.sort(key=lambda line: np.asarray(line[0])[:, 0].min())
        points = np.concatenate([np.asarray(line[0]) for line in fragments])
        x1, y1 = points.min(axis=0); x2, y2 = points.max(axis=0)
        merged.append([[[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            (''.join(line[1][0] for line in fragments), min(line[1][1] for line in fragments))])
    return [merged]


def clean_name(text):
    return PENDING.sub('', ''.join(text.split()))


def activation(image, line, index, count):
    text, confidence = line[1]
    if confidence < .95:
        return 'unknown'
    points = np.asarray(line[0])
    x1, y1 = np.maximum(points.min(axis=0).astype(int), 0)
    x2, y2 = np.minimum(points.max(axis=0).astype(int) + 1, [image.shape[1], image.shape[0]])
    crop = image[y1:y2, x1:x2]
    if crop.size < 30:
        return 'unknown'
    # White and grey glyphs are neutral; colored backgrounds must not count.
    neutral = crop.max(axis=2).astype(float) - crop.min(axis=2) < 25
    values = crop.mean(axis=2)[neutral]
    if len(values) < 10:
        return 'unknown'
    bright = float(np.percentile(values, 95))
    pending = PENDING.search(''.join(text.split())) is not None
    if pending:
        return 'pending' if count == 4 and index == 3 and 65 <= bright <= 180 else 'unknown'
    return 'active' if bright >= 210 else 'unknown'
