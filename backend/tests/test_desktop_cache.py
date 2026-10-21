import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import numpy as np

from app.core.desktop_adapter import DesktopAdapter
from app.core.data_models.model_io import WindowInfoOutput
from test_review import sample


class DesktopCacheTests(unittest.IsolatedAsyncioTestCase):
    async def run_observation(self, incomplete=False, scan=True):
        adapter = DesktopAdapter()
        adapter.set_scan_mode(scan)
        adapter.check_focus = Mock()
        regions = {name: dict(confidence=.9, box=dict(x_center=10, y_center=10, width=10, height=10))
            for name in ('relic-title', 'relic-main-stat', 'relic-sub-stat')}
        adapter.panel_cache = Mock()
        adapter.panel_cache.reuse.return_value = regions
        relic = sample()
        valid = SimpleNamespace(**relic, model_dump=lambda: relic.copy())
        invalid = SimpleNamespace(relic_title=None, relic_main_stat=None, relic_sub_stat=None)
        shot = dict(image=np.zeros((32, 32, 3), dtype=np.uint8),
            window_info=WindowInfoOutput(width=32, height=32, left=0, top=0))
        def result(data):
            return SimpleNamespace(success=True, data=data)
        stages = {
            'screenshot_stage': SimpleNamespace(process=AsyncMock(return_value=result(shot))),
            'detection_stage': SimpleNamespace(process=AsyncMock(return_value=result(regions))),
            'ocr_stage': SimpleNamespace(process=AsyncMock(side_effect=[result(invalid), result(valid)] if incomplete else [result(valid)])),
        }
        with patch('app.core.desktop_adapter.StageManager') as manager, \
             patch('app.core.desktop_adapter.get_pipeline_config', return_value={}), \
             patch('app.core.desktop_adapter.recognize_states', side_effect=lambda image, data: data):
            manager.return_value.get_stage.side_effect = stages.__getitem__
            data, _ = await adapter._observe()
        return adapter, stages, data

    async def test_valid_cache_skips_detector_and_cannot_click(self):
        adapter, stages, data = await self.run_observation()
        stages['detection_stage'].process.assert_not_awaited()
        self.assertEqual(data['detection_source'], 'cache')
        with self.assertRaises(ValueError):
            adapter.mark()

    async def test_incomplete_cached_ocr_reobserves_fresh(self):
        adapter, stages, data = await self.run_observation(incomplete=True)
        stages['detection_stage'].process.assert_awaited_once()
        self.assertEqual(stages['screenshot_stage'].process.await_count, 2)
        self.assertEqual(data['detection_source'], 'fresh')
        self.assertIn('cache_fallback_ms', data['timings_ms'])

    async def test_execution_observation_never_uses_cache(self):
        adapter, stages, data = await self.run_observation(scan=False)
        adapter.panel_cache.reuse.assert_not_called()
        stages['detection_stage'].process.assert_awaited_once()
        self.assertEqual(data['detection_source'], 'fresh')
