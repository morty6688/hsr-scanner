import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import numpy as np

from app.core.desktop_adapter import DesktopAdapter
from app.core.scan_capture import PanelLayoutMismatch
from app.core.model_impls.screenshot_model import ScreenshotModel
from app.core.data_models.model_io import WindowInfoOutput
from test_review import sample


class DesktopCacheTests(unittest.IsolatedAsyncioTestCase):
    async def run_observation(self, incomplete=False, scan=True, frozen=False, missing_refresh=False, persistent=False, unknown_title=False):
        adapter = DesktopAdapter()
        adapter.set_scan_mode(scan)
        adapter.check_focus = Mock()
        regions = {name: dict(confidence=.9, box=dict(x_center=10, y_center=10, width=10, height=10))
            for name in ('relic-title', 'relic-main-stat', 'relic-sub-stat')}
        adapter.panel_cache = Mock()
        adapter.panel_cache.reuse.return_value = regions
        relic = sample()
        if unknown_title:
            relic['relic_title'] = None
        valid = SimpleNamespace(**relic, model_dump=lambda: relic.copy())
        partial = dict(relic, relic_title=None, relic_main_stat=None, relic_sub_stat=None)
        invalid = SimpleNamespace(**partial, model_dump=lambda: partial.copy())
        shot = dict(image=np.zeros((32, 32, 3), dtype=np.uint8),
            window_info=WindowInfoOutput(width=32, height=32, left=0, top=0))
        def result(data):
            return SimpleNamespace(success=True, data=data)
        stages = {
            'screenshot_stage': SimpleNamespace(process=AsyncMock(return_value=result(shot))),
            'detection_stage': SimpleNamespace(process=AsyncMock(return_value=result(
                {k:v for k,v in regions.items() if k != 'relic-main-stat'} if missing_refresh else regions))),
            'ocr_stage': SimpleNamespace(process=AsyncMock(side_effect=[result(invalid), result(invalid if persistent else valid)] if incomplete else [result(valid)])),
        }
        with patch('app.core.desktop_adapter.StageManager') as manager, \
             patch('app.core.desktop_adapter.get_pipeline_config', return_value={}), \
             patch('app.core.desktop_adapter.recognize_states', side_effect=lambda image, data: data):
            manager.return_value.get_stage.side_effect = stages.__getitem__
            data, _ = await adapter._observe(shot=shot if frozen else None)
        return adapter, stages, data

    async def test_valid_cache_skips_detector_and_cannot_click(self):
        adapter, stages, data = await self.run_observation()
        stages['detection_stage'].process.assert_not_awaited()
        self.assertEqual(data['detection_source'], 'cache')
        with self.assertRaises(ValueError):
            adapter.mark()

    async def test_unknown_title_does_not_repeat_detection_or_ocr(self):
        _, stages, data = await self.run_observation(unknown_title=True, frozen=True)
        stages['detection_stage'].process.assert_not_awaited()
        stages['ocr_stage'].process.assert_awaited_once()
        self.assertIsNone(data['relic_title'])
        self.assertNotIn('cache_fallback_ms', data['timings_ms'])

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

    async def test_frozen_frame_fallback_never_recaptures_next_item(self):
        adapter, stages, data = await self.run_observation(incomplete=True, frozen=True)
        stages['screenshot_stage'].process.assert_not_awaited()
        stages['detection_stage'].process.assert_awaited_once()
        self.assertEqual(data['detection_source'], 'fresh')

    async def test_ocr_retry_missing_detector_uses_revalidated_cache(self):
        adapter, stages, data = await self.run_observation(incomplete=True, frozen=True, missing_refresh=True)
        adapter.panel_cache.clear.assert_not_called()
        self.assertEqual(adapter.panel_cache.reuse.call_count, 2)
        self.assertTrue(adapter.panel_cache.reuse.call_args.kwargs['allow_expired'])
        self.assertTrue(data['detection_refresh_fallback'])
        self.assertEqual(data['detection_source'], 'cache')
        self.assertIsNotNone(data['relic_main_stat'])

    async def test_persistent_partial_ocr_returns_preview_without_infinite_retry(self):
        adapter, stages, data = await self.run_observation(incomplete=True, frozen=True, missing_refresh=True, persistent=True)
        self.assertEqual(stages['ocr_stage'].process.await_count, 2)
        self.assertIsNone(data['relic_main_stat'])
        adapter.panel_cache.clear.assert_not_called()

    async def test_capture_stop_before_navigation(self):
        adapter = DesktopAdapter()
        adapter.check_focus = Mock()
        adapter.cancelled = lambda: True
        adapter.next = Mock()
        with self.assertRaises(InterruptedError):
            await adapter.capture_next(Mock())
        adapter.next.assert_not_called()

    async def test_capture_timeout_does_not_repeat_navigation(self):
        adapter = DesktopAdapter()
        adapter.check_focus = Mock()
        adapter.next = Mock()
        window = WindowInfoOutput(left=0, top=0, width=20, height=20)
        capture = SimpleNamespace(window=window.model_dump())
        with patch('app.core.desktop_adapter.ModelManager') as manager, \
             patch('app.core.desktop_adapter.perf_counter', side_effect=[0, 4]):
            manager.return_value.get_model.return_value.predict.return_value = window
            with self.assertRaisesRegex(InterruptedError, '未变化或未稳定'):
                await adapter.capture_next(capture)
        adapter.next.assert_called_once_with(fast=True)

    async def test_transient_anchor_mismatch_retries_same_item(self):
        adapter = DesktopAdapter(); adapter.check_focus = Mock(); adapter.next = Mock()
        window = WindowInfoOutput(left=0, top=0, width=20, height=20)
        capture = SimpleNamespace(window=window.model_dump(), rect=(0,0,20,20),
            signature=Mock(return_value=1), changed=Mock(return_value=True),
            similar=Mock(return_value=True),
            accept=Mock(side_effect=[PanelLayoutMismatch('transient'), dict(image='ok')]))
        clock = iter(n*.03 for n in range(100))
        with patch('app.core.desktop_adapter.ModelManager') as manager, \
             patch('app.core.desktop_adapter.perf_counter', side_effect=lambda: next(clock)):
            manager.return_value.get_model.side_effect = lambda kind: SimpleNamespace(
                predict=lambda _: np.zeros((20,20,3), dtype=np.uint8) if kind is ScreenshotModel else window)
            shot = await adapter.capture_next(capture)
        self.assertEqual(shot['image'], 'ok')
        self.assertEqual(capture.accept.call_count, 2)
        adapter.next.assert_called_once_with(fast=True)

    async def test_capture_window_move_before_navigation(self):
        adapter = DesktopAdapter()
        adapter.check_focus = Mock()
        adapter.next = Mock()
        window = WindowInfoOutput(left=1, top=0, width=20, height=20)
        capture = SimpleNamespace(window=dict(left=0, top=0, width=20, height=20))
        with patch('app.core.desktop_adapter.ModelManager') as manager:
            manager.return_value.get_model.return_value.predict.return_value = window
            with self.assertRaises(InterruptedError):
                await adapter.capture_next(capture)
        adapter.next.assert_not_called()

    async def test_capture_focus_loss_after_navigation_no_second_key(self):
        adapter = DesktopAdapter()
        adapter.check_focus = Mock(side_effect=[None, InterruptedError('失焦')])
        adapter.next = Mock()
        window = WindowInfoOutput(left=0, top=0, width=20, height=20)
        capture = SimpleNamespace(window=window.model_dump())
        with patch('app.core.desktop_adapter.ModelManager') as manager:
            manager.return_value.get_model.return_value.predict.return_value = window
            with self.assertRaisesRegex(InterruptedError, '失焦'):
                await adapter.capture_next(capture)
        adapter.next.assert_called_once_with(fast=True)
