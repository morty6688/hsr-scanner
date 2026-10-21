"""Compare full-frame and panel-only OCR on saved screenshots; no game input."""
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import cv2
from fastapi.testclient import TestClient
from main import app
from app.core.desktop_adapter import DesktopAdapter
from app.core.data_models.model_io import WindowInfoOutput


async def replay(paths):
    full = DesktopAdapter(); panel = DesktopAdapter()
    for adapter in (full, panel):
        adapter.check_focus = lambda: None
        adapter.set_scan_mode(True)
    rows = []
    capture = None
    for index, path in enumerate(paths):
        image = cv2.imread(path)
        if image is None:
            raise ValueError(path)
        shot = dict(image=image, window_info=WindowInfoOutput(
            width=image.shape[1], height=image.shape[0], left=0, top=0))
        original, _ = await full._observe_worker(shot)
        if capture is None:
            result, _ = await panel._observe_worker(shot)
            capture = panel.prepare_capture()
            if capture is None:
                raise ValueError('No panel anchors in first image')
        else:
            x, y, w, h = capture.rect
            crop = image[y:y+h, x:x+w].copy()
            frozen = capture.accept(crop, capture.signature(crop))
            result, _ = await panel.observe_frame(frozen)
        keys = ('relic_title', 'relic_main_stat', 'relic_sub_stat', 'rarity',
                'locked', 'equipped', 'discarded', 'recognition_verified')
        equal = all(original.get(k) == result.get(k) for k in keys)
        x, y, w, h = capture.rect
        timings = {}
        for name, pixels, args in [('full_png_ms', image, []),
                                  ('panel_png_ms', image[y:y+h, x:x+w], [cv2.IMWRITE_PNG_COMPRESSION, 1])]:
            start = perf_counter()
            ok, encoded = cv2.imencode('.png', pixels, args)
            assert ok
            timings[name] = round((perf_counter()-start)*1000, 2)
        rows.append(dict(file=path, equal=equal, panel_rect=capture.rect,
                         full=original['timings_ms'], panel=result['timings_ms'], **timings))
        print(json.dumps(rows[-1]), flush=True)
        if not equal:
            raise AssertionError('Panel/full recognition differs: ' + path)
    Path('local-data/panel-benchmark.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    return rows


if __name__ == '__main__':
    with TestClient(app):
        rows = asyncio.run(replay(sys.argv[1:]))
    print('CONTENT_EQUAL', all(r['equal'] for r in rows))
