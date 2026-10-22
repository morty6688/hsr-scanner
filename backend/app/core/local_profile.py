"""Local, fail-closed visual state recognition using calibrated template pairs."""
import json
from pathlib import Path

import cv2
import numpy as np

from app.constant import LOCAL_DATA_FOLDER


def grey_glyph_error(reference, crop):
    """Compare a disabled grey glyph at the same location, not the surrounding ring."""
    ys, xs = np.where(reference)
    if len(xs) < 20:
        return 1.0
    x1, x2 = max(0, xs.min()-2), min(crop.shape[1], xs.max()+3)
    y1, y2 = max(0, ys.min()-2), min(crop.shape[0], ys.max()+3)
    pixels = crop[y1:y2, x1:x2].astype(np.int16)
    actual = (pixels.max(axis=2)-pixels.min(axis=2) < 20) & (pixels.min(axis=2) >= 45) & (pixels.max(axis=2) <= 170)
    expected = reference[y1:y2, x1:x2]
    # Grey antialiasing shrinks glyph edges. Permit one pixel in both directions,
    # while requiring both shapes to account for each other's foreground.
    if not np.any(actual):
        return 1.0
    kernel = np.ones((3, 3), np.uint8)
    expanded_actual = cv2.dilate(actual.astype(np.uint8), kernel).astype(bool)
    expanded_expected = cv2.dilate(expected.astype(np.uint8), kernel).astype(bool)
    coverage = min(np.count_nonzero(expected & expanded_actual)/np.count_nonzero(expected),
                   np.count_nonzero(actual & expanded_expected)/np.count_nonzero(actual))
    return 1-float(coverage)


def equipped_text_matches(template, crop):
    """Use the fixed gold label in a positive equipment template; never infer false from absence."""
    from app.core.panel_cache import gold
    expected = gold(template)
    joined = cv2.dilate(expected.astype(np.uint8), np.ones((3, 21), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined)
    candidates = []
    for x, y, w, h, _ in stats[1:count]:
        ink = np.count_nonzero(expected[y:y+h, x:x+w])
        if w >= 2*h and h >= 12 and ink >= 100:
            candidates.append((ink, x, y, w, h))
    if not candidates:
        return False
    _, x, y, w, h = max(candidates)
    a, b = expected[y:y+h, x:x+w], gold(crop)[y:y+h, x:x+w]
    union = np.count_nonzero(a | b)
    return bool(union and np.count_nonzero(a & b)/union >= .9)


def read_profile():
    path = Path(LOCAL_DATA_FOLDER) / 'recognition.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def equipment_background_error(template, crop):
    """Compare blue panel backgrounds cell by cell, excluding changing white lore.

    Both positive and negative templates participate in the usual margin check.
    Missing blue background is unknown, not evidence of an unequipped relic.
    """
    def describe(image):
        cells = []
        for row in np.array_split(image, 3):
            for cell in np.array_split(row, 6, axis=1):
                pixels = cell.astype(float)
                blue = (pixels[:, :, 0]-pixels[:, :, 2] > 20) & (pixels[:, :, 1]-pixels[:, :, 2] > 10)
                if not blue.size or blue.mean() < .4:
                    return None
                cells.append(np.median(pixels[blue], axis=0))
        return np.asarray(cells)
    if min(template.shape[:2]) < 18:
        return 1.0
    a, b = describe(template), describe(crop)
    return float(np.mean(np.abs(a-b)))/255 if a is not None and b is not None else 1.0


def recognize_states(image, relic, profile=None):
    profile = read_profile() if profile is None else profile
    relic['recognition_verified'] = False
    relic['state_conflict'] = False
    relic['state_evidence'] = {}
    for key in ('locked', 'equipped', 'discarded', 'rarity'):
        relic[key] = None
    # This personal build is explicitly restricted to the user's five-star inventory.
    relic['rarity'] = 5
    relic['rarity_source'] = 'user_assumed'
    if profile.get('size') != [image.shape[1], image.shape[0]]:
        relic['state_evidence']['profile'] = '尚未校准或截图尺寸不一致'
        return relic
    def match(region, key, allow_grey=False):
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
            if not path.is_file():
                continue
            template = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if template is None or template.shape != crop.shape:
                continue
            if region.get('mode') == 'glyph':
                def glyph(pixels):
                    return (pixels.min(axis=2) >= 180) & (pixels.max(axis=2).astype(int)-pixels.min(axis=2) < 45)
                a, b = glyph(template), glyph(crop)
                union = np.count_nonzero(a | b)
                error = 1-float(np.count_nonzero(a & b))/union if union >= 10 else 1.0
                if allow_grey and value == 'false':
                    error = min(error, grey_glyph_error(a, crop))
            else:
                error = float(np.mean(np.abs(template.astype(float) - crop.astype(float)))) / 255
                if key == 'equipped':
                    error = min(error, equipment_background_error(template, crop))
                if key == 'equipped' and value == 'true' and equipped_text_matches(template, crop):
                    error = 0.0
            scores.append((error, value))
        scores.sort()
        limit, margin = (.12, .15) if region.get('mode') == 'glyph' else (.025, .025)
        relic['state_evidence'][key] = dict(scores={value: round(error, 4) for error, value in scores}, mode=region.get('mode', 'color'))
        if len(scores) < 2 or scores[0][0] > limit or scores[1][0] - scores[0][0] < margin:
            return None
        return scores[0][1]
    for key in ('discarded', 'locked', 'equipped'):
        result = match(profile.get(key), key)
        relic[key] = {'true': True, 'false': False}.get(result)
    # First identify both normal icons independently. Only a positively selected
    # counterpart permits a second pass for the disabled grey, unselected glyph.
    if relic['locked'] is True and relic['discarded'] is True:
        relic['locked'] = relic['discarded'] = None
        relic['state_conflict'] = True
        relic['state_evidence']['conflict'] = '锁定与弃置同时识别为选中'
    else:
        for key, counterpart in (('locked', 'discarded'), ('discarded', 'locked')):
            if relic[key] is None and relic[counterpart] is True:
                result = match(profile.get(key), key, allow_grey=True)
                if result == 'false':
                    relic[key] = False
                    relic['state_evidence'][key]['source'] = 'disabled_grey_glyph'
    for index, (sub, region) in enumerate(zip(relic.get('relic_sub_stat') or [], profile.get('activation', []))):
        if not region:
            continue
        state = match(region, 'activation' + str(index))
        sub['activation'] = state if state in ('active', 'pending') else 'unknown'
    if relic.get('pending_unlock_cost') is None:
        relic['pending_unlock_cost'] = profile.get('pending_unlock_cost')
    relic['recognition_verified'] = (not relic['state_conflict'] and
        profile.get('client_verified') is True and relic.get('confidence', 0) >= .95)
    return relic
