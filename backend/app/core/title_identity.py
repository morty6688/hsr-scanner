"""Resolve unsupported title glyphs using two independently read UI labels."""
from app.core.batch_ocr import text_rows
from app.core.panel_cache import rectangle


PARTS = {'头部':'head', '手部':'hand', '躯干':'body', '脚部':'feet', '位面球':'sphere', '连结绳':'rope'}


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


def identify_from_labels(model, matcher, context):
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
    if not any(score >= .95 and name in {d.get('name') for d in matcher.relic_sets.values()}
               for name,score in set_labels):
        return None
    part_image = image[max(0,my-int(height*.18)):my, max(0,tx):min(width,tx+int(tw*.38))]
    if not part_image.size:
        return None
    result = model.predict(part_image)
    part_labels = [line[1] for page in result or [] for line in page or []]
    identity = exact_identity(matcher, set_labels, part_labels)
    if identity is not None:
        context.data['title_identity_evidence'] = dict(set_labels=set_labels, part_labels=part_labels)
    return identity
