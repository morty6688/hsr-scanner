"""Local, fail-closed visual state recognition using calibrated template pairs."""
import json
from pathlib import Path

import cv2
import numpy as np

from app.constant import LOCAL_DATA_FOLDER


def read_profile():
    path = Path(LOCAL_DATA_FOLDER) / 'recognition.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def recognize_states(image, relic):
    profile = read_profile()
    if profile.get('size') != [image.shape[1], image.shape[0]]:
        return relic
    def match(region):
        if not region:
            return None
        x, y, w, h = region['rect']
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > image.shape[1] or y+h > image.shape[0]:
            return None
        crop = image[y:y+h, x:x+w]
        scores = []
        for value, file in region['templates'].items():
            path = (Path(LOCAL_DATA_FOLDER) / file).resolve()
            if Path(LOCAL_DATA_FOLDER).resolve() not in path.parents:
                return None
            template = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if template is None or template.shape != crop.shape:
                continue
            error = float(np.mean(np.abs(template.astype(float) - crop.astype(float)))) / 255
            scores.append((error, value))
        scores.sort()
        if len(scores) < 2 or scores[0][0] > .025 or scores[1][0] - scores[0][0] < .025:
            return None
        return scores[0][1]
    for key in ('locked', 'equipped', 'discarded'):
        result = match(profile.get(key))
        relic[key] = {'true': True, 'false': False}.get(result)
    rarity = match(profile.get('rarity'))
    relic['rarity'] = int(rarity) if rarity and rarity.isdigit() else None
    for sub, region in zip(relic.get('relic_sub_stat') or [], profile.get('activation', [])):
        state = match(region)
        sub['activation'] = state if state in ('active', 'pending') else 'unknown'
    if relic.get('pending_unlock_cost') is None:
        relic['pending_unlock_cost'] = profile.get('pending_unlock_cost')
    relic['recognition_verified'] = profile.get('client_verified') is True and relic.get('confidence', 0) >= .95
    return relic
