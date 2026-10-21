import unittest
import numpy as np
from app.core.panel_cache import PanelCache


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((300, 400, 3), dtype=np.uint8)
        self.image[77:80, 200:360] = [30, 160, 230]
        self.image[110:130, 200:203] = [30, 160, 230]
        self.window = dict(width=400, height=300, left=0, top=0)
        self.regions = {name: dict(box=dict(x_center=x, y_center=y, width=w, height=h), confidence=.9)
            for name, x,y,w,h in [('relic-title',280,60,160,40), ('relic-main-stat',290,120,140,20), ('relic-sub-stat',290,180,140,80)]}
        self.cache = PanelCache()
        self.cache.remember(self.image, self.window, self.regions)

    def test_reuses_coordinates_but_crops_new_pixels(self):
        new = self.image.copy(); new[180, 290] = 255
        result = self.cache.reuse(new, self.window)
        self.assertIsNotNone(result)
        self.assertEqual(result['relic-sub-stat']['image'][40, 70].tolist(), [255]*3)
        self.assertNotIn('discard-icon', result)

    def test_window_move_or_size_change_invalidates(self):
        self.assertIsNone(self.cache.reuse(self.image, dict(self.window, left=1)))
        self.assertFalse(self.cache.regions)

    def test_missing_anchor_invalidates(self):
        self.assertIsNone(self.cache.reuse(np.zeros_like(self.image), self.window))

    def test_periodic_refresh(self):
        for _ in range(24):
            self.assertIsNotNone(self.cache.reuse(self.image, self.window))
        self.assertIsNone(self.cache.reuse(self.image, self.window))

    def test_incomplete_detection_never_cached(self):
        del self.regions['relic-sub-stat']
        self.cache.remember(self.image, self.window, self.regions)
        self.assertIsNone(self.cache.reuse(self.image, self.window))

    def test_failed_periodic_refresh_can_reuse_only_with_valid_anchors(self):
        self.cache.uses = 24
        self.assertIsNone(self.cache.reuse(self.image, self.window))
        self.assertIsNotNone(self.cache.reuse(self.image, self.window, allow_expired=True))
        self.cache.uses = 24
        self.assertIsNone(self.cache.reuse(np.zeros_like(self.image), self.window, allow_expired=True))
