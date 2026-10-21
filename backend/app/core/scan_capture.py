"""Immutable scan frames and conservative, session-local panel capture bounds."""
import asyncio
import copy
import cv2
import numpy as np

from app.core.panel_cache import rectangle, anchor_pixels, anchor_matches


class PanelLayoutMismatch(InterruptedError):
    pass


async def run_native(function):
    task = asyncio.create_task(asyncio.to_thread(function))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class ScanCapture:
    def __init__(self, context, cache, profile):
        shot = context.data['screenshot_stage']
        self.window = shot['window_info'].model_dump()
        image = shot['image']
        height, width = image.shape[:2]
        regions = context.data['detection_stage']
        self.text_rects = [list(regions[n].get('crop_rect', rectangle(regions[n]['box'])))
                           for n in ('relic-title', 'relic-main-stat', 'relic-sub-stat') if n in regions]
        if len(self.text_rects) != 3 or not cache.anchors:
            raise ValueError('无法建立稳定面板区域，扫描停止')
        self.anchors = copy.deepcopy(cache.anchors)
        rects = self.text_rects + [r for r, _ in self.anchors]
        rects += [r['rect'] for r in profile.get('activation', []) if 'rect' in r]
        rects += [profile[k]['rect'] for k in ('locked', 'equipped', 'discarded', 'rarity')
                  if k in profile and 'rect' in profile[k]]
        # Keep the entire panel height (artwork, level, statuses), including the
        # calibrated regions. Full-size canvas preserves all existing coordinates.
        left = max(0, min(int(r[0]) for r in rects) - 32)
        self.rect = (left, 0, width-left, height)
        self.baseline = self.signature(image[:, left:])

    def signature(self, image):
        left, top, _, _ = self.rect
        parts = []
        for index, (x, y, w, h) in enumerate(self.text_rects):
            crop = image[y-top:y-top+h, x-left:x-left+w]
            if crop.size == 0:
                raise ValueError('面板区域越界')
            if index < 2:
                from app.core.panel_cache import gold
                mask = gold(crop)
            else:
                pixels = crop.astype(np.int16)
                mask = (pixels.max(axis=2)-pixels.min(axis=2) < 35) & (pixels.min(axis=2) > 100)
            parts.append(cv2.resize(mask.astype(np.uint8)*255, (160, 32), interpolation=cv2.INTER_AREA))
        return np.concatenate(parts).astype(np.int16)

    @staticmethod
    def similar(a, b):
        return float(np.mean(np.abs(a-b))) < .5

    def changed(self, signature):
        return not self.similar(signature, self.baseline)

    def accept(self, image, signature):
        left, top, width, height = self.rect
        for (x, y, w, h), expected in self.anchors:
            actual = anchor_pixels(image[y-top:y-top+h, x-left:x-left+w], expected)
            if not anchor_matches(actual, expected):
                raise PanelLayoutMismatch('无法确认面板固定标记，扫描停止')
        canvas = np.zeros((self.window['height'], self.window['width'], 3), dtype=np.uint8)
        canvas[top:top+height, left:left+width] = image
        self.baseline = signature.copy()
        from app.core.data_models.model_io import WindowInfoOutput
        return dict(image=canvas, preview_image=image, window_info=WindowInfoOutput(**self.window))
