"""Session-local OCR region cache guarded by two static panel anchors."""
import numpy as np

NAMES = ('relic-title', 'relic-main-stat', 'relic-sub-stat')


def gold(image):
    b, g, r = (image[:, :, i].astype(int) for i in range(3))
    return (r > 130) & (g > 80) & (r - b > 55) & (g - b > 25)


def rectangle(box):
    x = box['x_center'] - box['width'] // 2
    y = box['y_center'] - box['height'] // 2
    return [x, y, box['width'], box['height']]


def anchor_pixels(image, expected):
    if min(expected.shape) <= 5:
        return gold(image)
    # The close button is a neutral-white X, independent of relic highlights.
    pixels = image.astype(np.int16)
    return (pixels.min(axis=2) >= 180) & (pixels.max(axis=2)-pixels.min(axis=2) < 45)


def anchor_matches(actual, expected):
    """Compare the fixed line, not changing background pixels around it."""
    if actual.shape != expected.shape or not expected.size:
        return False
    if min(expected.shape) > 5:
        count = np.count_nonzero(expected)
        union = np.count_nonzero(actual | expected)
        return bool(count >= 20 and union and np.count_nonzero(actual & expected)/union >= .85)
    horizontal = expected.shape[1] >= expected.shape[0]
    reference = expected if horizontal else expected.T
    observed = actual if horizontal else actual.T
    index = int(np.argmax(reference.sum(axis=1)))
    support = reference[index]
    if np.count_nonzero(support) < reference.shape[1] * .55:
        return False
    # One pixel of rasterization tolerance, never relocate the panel or update
    # the original reference from newly observed background colors.
    for line in observed[max(0, index-1):min(len(observed), index+2)]:
        if np.count_nonzero(line & support) / np.count_nonzero(support) >= .85:
            return True
    return False


class PanelCache:
    def __init__(self):
        self.clear()

    def clear(self):
        self.regions = {}
        self.anchors = []
        self.window = None
        self.uses = 0

    def remember(self, image, window, regions):
        self.clear()
        if any(name not in regions for name in NAMES):
            return
        height, width = image.shape[:2]
        title = regions['relic-title']['box']
        tx, ty, tw, th = rectangle(title)
        # The main-stat gold stripe is conditional game highlighting, NOT layout.
        searches = [(tx, ty + th - th // 4, tw, max(th // 2, 12), 'horizontal')]
        for x, y, w, h, orientation in searches:
            if min(x, y) < 0 or x+w > width or y+h > height or min(w, h) < 3:
                self.clear(); return
            mask = gold(image[y:y+h, x:x+w])
            counts = mask.sum(axis=1 if orientation == 'horizontal' else 0)
            index = int(np.argmax(counts))
            if counts[index] < (w if orientation == 'horizontal' else h) * .55:
                self.clear(); return
            if orientation == 'horizontal':
                y += max(0, index-2); h = min(5, mask.shape[0] - max(0, index-2))
            else:
                x += max(0, index-2); w = min(5, mask.shape[1] - max(0, index-2))
            self.anchors.append(([x, y, w, h], gold(image[y:y+h, x:x+w]).copy()))
        x, y = int(width*.94), int(height*.015)
        right, bottom = int(width*.995), int(height*.10)
        crop = image[y:bottom, x:right]
        mask = anchor_pixels(crop, np.zeros((6,6), dtype=bool))
        ys, xs = np.nonzero(mask)
        if len(xs) < 20:
            self.clear(); return
        bx, by = max(0, int(xs.min())-2), max(0, int(ys.min())-2)
        ex, ey = min(crop.shape[1], int(xs.max())+3), min(crop.shape[0], int(ys.max())+3)
        if min(ex-bx, ey-by) <= 5 or not .65 <= (ex-bx)/(ey-by) <= 1.5:
            self.clear(); return
        self.anchors.append(([x+bx, y+by, ex-bx, ey-by], mask[by:ey, bx:ex].copy()))
        for name in NAMES:
            region = regions[name]
            self.regions[name] = {key: region[key] for key in ('box', 'confidence', 'crop_rect', 'unpadded_rect') if key in region}
        self.window = dict(window)

    def reuse(self, image, window, allow_expired=False):
        if not self.regions or self.window != dict(window):
            self.clear(); return None
        if self.uses >= 24 and not allow_expired:
            return None
        height, width = image.shape[:2]
        for (x, y, w, h), expected in self.anchors:
            if x+w > width or y+h > height:
                self.clear(); return None
            actual = anchor_pixels(image[y:y+h, x:x+w], expected)
            if not anchor_matches(actual, expected):
                self.clear(); return None
        result = {}
        for name, saved in self.regions.items():
            region = dict(saved)
            for field, rect_key in [('image', 'crop_rect'), ('image_unpadded', 'unpadded_rect')]:
                x, y, w, h = saved.get(rect_key, rectangle(saved['box']))
                if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
                    self.clear(); return None
                region[field] = image[y:y+h, x:x+w]
            result[name] = region
        self.uses = 1 if allow_expired and self.uses >= 24 else self.uses + 1
        return result
