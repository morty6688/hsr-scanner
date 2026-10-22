"""Resolve unsupported title glyphs using two independently read UI labels."""
from app.core.batch_ocr import text_rows
from app.core.panel_cache import rectangle
import cv2
import numpy as np


PARTS = {'头部':'head', '手部':'hand', '躯干':'body', '脚部':'feet', '位面球':'sphere', '连结绳':'rope'}


def omitted_characters(expected, observed):
    """One missing Chinese character only; no substitutions or fuzzy distances."""
    if not observed or len(observed) < 5 or len(expected) != len(observed)+1:
        return set()
    return {c for i, c in enumerate(expected) if '\u4e00' <= c <= '\u9fff'
            and expected[:i]+expected[i+1:] == observed}


def cross_checked_identity(matcher, set_labels, part_labels, title_text):
    exact = exact_identity(matcher, set_labels, part_labels)
    if exact is not None:
        return exact
    parts = {PARTS[name] for name, score in part_labels if score >= .95 and name in PARTS}
    if len(parts) != 1 or not title_text:
        return None
    part = next(iter(parts))
    candidates = set()
    for details in matcher.relic_sets.values():
        title = details.get('parts_cn', {}).get(part)
        if not title:
            continue
        missing_title = omitted_characters(title, title_text)
        for label, confidence in set_labels:
            if confidence >= .95 and missing_title & omitted_characters(details['name'], label):
                candidates.add(details['parts'][part])
    return matcher.match_relic_part(next(iter(candidates))) if len(candidates) == 1 else None


def exact_identity(matcher, set_labels, part_labels):
    sets = {name for name, score in set_labels if score >= .95}
    parts = {PARTS[name] for name, score in part_labels if score >= .95 and name in PARTS}
    if len(parts) != 1:
        return None
    matches = []
    for details in matcher.relic_sets.values():
        if details.get('name') in sets:
            for part in parts:
                if part in details.get('parts', {}):
                    matches.append(details['parts'][part])
    return matcher.match_relic_part(matches[0]) if len(matches) == 1 else None


def read_part_labels(model, image):
    result = model.predict(image)
    lines = [line for page in result or [] for line in page or []]
    labels = [line[1] for line in lines]
    if any(name in PARTS and score >= .95 for name, score in labels):
        return labels
    # Re-read only a recognized but uncertain part label, isolating its white
    # glyphs from the gold artwork. Keep the same .95 acceptance threshold.
    variants = []
    for points, (name, score) in lines:
        if name not in PARTS:
            continue
        points = np.asarray(points).astype(int)
        x1, y1 = np.maximum(points.min(axis=0)-3, 0)
        x2, y2 = np.minimum(points.max(axis=0)+4, [image.shape[1], image.shape[0]])
        crop = image[y1:y2, x1:x2].astype(np.int16)
        if not crop.size:
            continue
        mask = ((crop.max(axis=2)-crop.min(axis=2) < 35) & (crop.min(axis=2) > 150)).astype(np.uint8)*255
        variants.extend([cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR), cv2.cvtColor(255-mask, cv2.COLOR_GRAY2BGR)])
    if variants:
        reread, _ = model.model.text_recognizer(variants)
        labels += reread
    return labels


def identify_from_labels(model, matcher, context, title_text=None):
    regions = context.data.get('detection_stage', {})
    if any(n not in regions for n in ('relic-title','relic-main-stat','relic-sub-stat')):
        return None
    image = context.data['screenshot_stage']['image']
    height, width = image.shape[:2]
    tx, _, tw, _ = rectangle(regions['relic-title']['box'])
    _, my, _, _ = rectangle(regions['relic-main-stat']['box'])
    _, sy, _, sh = rectangle(regions['relic-sub-stat']['box'])
    bottom = sy+sh
    set_image = image[max(0,bottom):min(height,bottom+int(height*.14)), max(0,tx):width]
    try:
        rows = text_rows(set_image, golden=True)
    except (ValueError, IndexError):
        return None
    if len(rows) != 1:
        return None
    x1,y1,x2,y2 = rows[0]
    set_labels, _ = model.model.text_recognizer([set_image[y1:y2,x1:x2]])
    if not any(score >= .95 and any(name == d.get('name') or
               omitted_characters(d['name'], name) for d in matcher.relic_sets.values())
               for name, score in set_labels):
        return None
    part_image = image[max(0,my-int(height*.18)):my, max(0,tx):min(width,tx+int(tw*.38))]
    if not part_image.size:
        return None
    part_labels = read_part_labels(model, part_image)
    identity = cross_checked_identity(matcher, set_labels, part_labels, title_text)
    if identity is not None:
        context.data['title_identity_evidence'] = dict(set_labels=set_labels, part_labels=part_labels,
            title_text=title_text, method='exact_set_part' if exact_identity(matcher, set_labels, part_labels)
            is not None else 'same_character_omitted_in_title_and_set')
    return identity
