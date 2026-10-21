"""Offline A/B replay of the real observation pipeline. Never sends game input."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import cv2
from fastapi.testclient import TestClient
from main import app
from app.core.desktop_adapter import DesktopAdapter
from app.core.data_models.model_io import WindowInfoOutput
from app.core.data_models.stage_result import StageResult
from app.core.pipeline_stage_impls.screenshot_stage import ScreenshotStage


async def replay(paths):
    results = []
    # Warm both models before timing, so first-use initialization is not
    # incorrectly attributed to a cache speed-up.
    for cache_enabled in (None, False, True):
        adapter = DesktopAdapter()
        adapter.check_focus = lambda: None
        adapter.set_scan_mode(bool(cache_enabled))
        for path in (paths[:1] if cache_enabled is None else paths):
            image = cv2.imread(path)
            if image is None:
                raise ValueError(path)
            shot = dict(image=image, window_info=WindowInfoOutput(width=image.shape[1], height=image.shape[0], left=0, top=0))
            async def screenshot_stage(*args):
                return StageResult(success=True, data=shot)
            with patch.object(ScreenshotStage, 'process', screenshot_stage):
                relic, _ = await adapter.observe()
            if cache_enabled is None:
                continue
            results.append(dict(file=path, cache_enabled=cache_enabled, source=relic['detection_source'],
                ocr_path=relic.get('ocr_path', 'legacy'),
                timings=relic['timings_ms'], relic={key: relic.get(key) for key in ('relic_title', 'relic_main_stat', 'relic_sub_stat')}))
    return results


with TestClient(app):
    results = asyncio.run(replay(sys.argv[1:]))
    Path('local-data/cache-benchmark.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for enabled in (False, True):
        rows = [r for r in results if r['cache_enabled'] == enabled]
        print(json.dumps(dict(cache_enabled=enabled, frames=len(rows), reused=sum(r['source'] == 'cache' for r in rows),
            fallback=sum('cache_fallback_ms' in r['timings'] for r in rows),
            total_ms=sum(r['timings']['total_ms'] for r in rows),
            detection_ms=sum(r['timings']['detection_stage_ms'] for r in rows))))
    n = len(results) // 2
    print('CONTENT_EQUAL', all(results[i]['relic'] == results[n+i]['relic'] for i in range(n)))
