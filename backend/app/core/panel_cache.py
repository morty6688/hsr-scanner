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
        main = regions['relic-main-stat']['box']
        tx, ty, tw, th = rectangle(title)
        mx, my, mw, mh = rectangle(main)
        # Title underline and the narrow vertical stripe left of the main stat
        # remain fixed as the selected relic's text, icon and artwork change.
        searches = [(tx, ty + th - th // 4, tw, max(th // 2, 12), 'horizontal'),
                    (mx - mw // 5, my, mw // 5, mh, 'vertical')]
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
            actual = gold(image[y:y+h, x:x+w])
            union = np.count_nonzero(actual | expected)
            if not union or np.count_nonzero(actual & expected) / union < .85:
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
