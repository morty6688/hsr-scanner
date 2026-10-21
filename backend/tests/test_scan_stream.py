import asyncio
import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import cv2

from app.core.scan_stream import scan_stream
from app.core.scan_capture import ScanCapture
from app.core.data_models.model_io import WindowInfoOutput
from app.core.scan_session import persist_scan
import test_panel_cache


class CaptureTests(unittest.TestCase):
    def setUp(self):
        fixture = test_panel_cache.CacheTests(); fixture.setUp()
        self.fixture = fixture
        context = SimpleNamespace(data=dict(screenshot_stage=dict(image=fixture.image,
            window_info=WindowInfoOutput(**fixture.window)), detection_stage=fixture.regions))
        self.capture = ScanCapture(context, fixture.cache, {})

    def test_roi_preserves_coordinates_and_detects_text_change(self):
        x, y, w, h = self.capture.rect
        self.assertLess(w, self.fixture.window['width'])
        image = self.fixture.image[:, x:].copy()
        self.assertFalse(self.capture.changed(self.capture.signature(image)))
        image[160:180, 230-x:300-x] = 255
        signature = self.capture.signature(image)
        self.assertTrue(self.capture.changed(signature))
        shot = self.capture.accept(image, signature)
        np.testing.assert_array_equal(shot['image'][:, x:], image)
        self.assertFalse(self.capture.changed(signature))

    def test_page_change_rejected(self):
        x, _, _, _ = self.capture.rect
        image = np.zeros_like(self.fixture.image[:, x:])
        with self.assertRaises(InterruptedError):
            self.capture.accept(image, self.capture.signature(image))

    def test_colored_background_change_is_not_text_change(self):
        x, _, _, _ = self.capture.rect
        image = self.fixture.image[:, x:].copy()
        blank = np.all(image == 0, axis=2)
        image[blank] = [95, 60, 20]
        self.assertFalse(self.capture.changed(self.capture.signature(image)))

    def test_background_persistence_writes_lossless_image_and_session(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            snapshot = dict(id='replay', records=[dict(screenshot='item.png')])
            persist_scan(directory, snapshot, 'item.png', self.fixture.image)
            np.testing.assert_array_equal(cv2.imread(str(directory / 'item.png')), self.fixture.image)
            self.assertEqual(json.loads((directory / 'replay.json').read_text()), snapshot)
            self.assertFalse((directory / 'replay.tmp').exists())


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_frame_lookahead_overlaps_ocr_and_stops_on_close(self):
        captures = []
        advanced = asyncio.Event()
        async def capture(_):
            captures.append(len(captures)+1)
            if len(captures) == 2:
                advanced.set()
            return captures[-1]
        async def read(frame):
            await asyncio.wait_for(advanced.wait(), 1)
            return frame, b'png'
        adapter = SimpleNamespace(prepare_capture=lambda: object(), capture_next=capture,
            observe_frame=read, cancelled=lambda: False, check_focus=Mock())
        async def initial(): return 0, b'png'
        stream = scan_stream(adapter, initial)
        self.assertEqual((await stream.__anext__())[0], 0)
        self.assertEqual((await stream.__anext__())[0], 1)
        self.assertEqual(captures, [1, 2])
        await stream.aclose()
        await asyncio.sleep(0)
        self.assertEqual(captures, [1, 2])

    async def test_ocr_failure_drains_prefetch(self):
        cancelled = asyncio.Event()
        calls = 0
        async def capture(_):
            nonlocal calls
            calls += 1
            if calls == 1: return 1
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def read(frame):
            await asyncio.sleep(0)
            raise ValueError('bad OCR')
        adapter = SimpleNamespace(prepare_capture=lambda: object(), capture_next=capture,
            observe_frame=read, cancelled=lambda: False, check_focus=Mock())
        async def initial(): return 0, b'png'
        stream = scan_stream(adapter, initial)
        await stream.__anext__()
        with self.assertRaisesRegex(ValueError, 'bad OCR'):
            await stream.__anext__()
        self.assertTrue(cancelled.is_set())
        self.assertEqual(calls, 2)

    async def test_stop_during_ocr_does_not_deliver_frame(self):
        stopped = False
        async def read(frame):
            nonlocal stopped
            stopped = True
            return frame, b'png'
        async def capture(_): return 1
        adapter = SimpleNamespace(prepare_capture=lambda: object(), capture_next=capture,
            observe_frame=read, cancelled=lambda: stopped, check_focus=Mock())
        async def initial(): return 0, b'png'
        stream = scan_stream(adapter, initial)
        await stream.__anext__()
        with self.assertRaises(InterruptedError): await stream.__anext__()

