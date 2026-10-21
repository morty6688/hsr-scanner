import ctypes
import asyncio
import hashlib
import json
from time import perf_counter
from uuid import uuid4
from pathlib import Path
import cv2
import numpy as np
import pyautogui

from app.constant import LOCAL_DATA_FOLDER, ASSETS_FOLDER

from app.core.data_models.pipeline_context import PipelineContext
from app.core.local_profile import recognize_states
from app.core.local_profile import read_profile
from app.core.managers.model_manager import ModelManager
from app.core.managers.stage_manager import StageManager
from app.core.model_impls.window_info_model import WindowInfoModel
from app.core.model_impls.screenshot_model import ScreenshotModel
from app.core.utils.database import get_pipeline_config
from app.core.observation_retry import DetectionIncomplete, retry_observation
from app.constant import AUTO_DETECT_RELIC_BOX
from app.core.grid_navigation import GridNavigation
from app.core.panel_cache import PanelCache
from app.core.data_models.stage_result import StageResult
from app.core.data_models.model_io import WindowInfoOutput
from app.core.scan_capture import ScanCapture, run_native, PanelLayoutMismatch


class DesktopAdapter:
    def __init__(self):
        self.last = None
        self.cancelled = lambda: False
        self.navigation = GridNavigation()
        self.panel_cache = PanelCache()
        self.scan_mode = False

    def set_scan_mode(self, enabled):
        self.scan_mode = enabled
        self.panel_cache.clear()

    def reset_navigation(self):
        self.navigation.reset()
        self.last = None
        self.panel_cache.clear()

    def revision(self):
        digest = hashlib.sha256()
        paths = [Path(LOCAL_DATA_FOLDER) / 'recognition.json', Path(ASSETS_FOLDER) / 'local_manifest.json']
        paths += sorted((Path(LOCAL_DATA_FOLDER) / 'templates').glob('*.png'))
        paths += sorted((Path(ASSETS_FOLDER) / 'relic').glob('*.json'))
        for path in paths:
            digest.update(str(path).encode())
            digest.update(path.read_bytes() if path.is_file() else b'missing')
        return digest.hexdigest()

    def check_focus(self):
        window = ModelManager().get_model(WindowInfoModel)
        window.predict(None)
        if ctypes.windll.user32.GetForegroundWindow() != window.hwnd:
            raise InterruptedError('游戏窗口未在前台，操作已暂停')

    async def observe(self):
        return await retry_observation(self._observe_worker, self.check_focus, self.cancelled)

    async def _observe_worker(self, shot=None):
        # OCR must not block HTTP stop requests on the server event loop.
        worker = asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(self._observe(shot=shot))))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Native OCR cannot be cancelled halfway. Keep the session busy until it
            # exits so a second scan never races the same model or last observation.
            await worker
            raise

    async def _observe(self, force_detection=False, shot=None):
        input_shot = shot
        started = perf_counter()
        timings = {}
        reused = False
        self.check_focus()
        context = PipelineContext(pipeline_id='review', meta_data=get_pipeline_config('SingleRelicAnalysisPipeline'))
        manager = StageManager()
        for stage in ('screenshot_stage', 'detection_stage', 'ocr_stage'):
            if self.cancelled():
                raise InterruptedError('已停止')
            self.check_focus()
            step_started = perf_counter()
            cached = None
            if stage == 'detection_stage':
                context.data['screenshot_stage']['allow_multiscale'] = self.scan_mode
            if stage == 'detection_stage' and self.scan_mode and not force_detection and context.meta_data.get(AUTO_DETECT_RELIC_BOX, True):
                shot = context.data['screenshot_stage']
                cached = self.panel_cache.reuse(shot['image'], shot['window_info'].model_dump())
            if stage == 'screenshot_stage' and input_shot is not None:
                result = StageResult(success=True, data=input_shot)
            elif cached is not None:
                result = StageResult(success=True, data=cached)
                reused = True
            else:
                result = await manager.get_stage(stage).process(context)
            if (stage == 'detection_stage' and self.scan_mode
                    and context.meta_data.get(AUTO_DETECT_RELIC_BOX, True) and cached is None
                    and (not result.success or any(not (result.data or {}).get(name)
                         for name in ('relic-title', 'relic-main-stat', 'relic-sub-stat')))):
                shot = context.data['screenshot_stage']
                recovered = self.panel_cache.reuse(shot['image'], shot['window_info'].model_dump(), allow_expired=True)
                if recovered is not None:
                    result = StageResult(success=True, data=recovered)
                    reused = True
                    context.data['refresh_fallback'] = True
            timings[stage + '_ms'] = round((perf_counter() - step_started) * 1000, 2)
            if self.cancelled():
                raise InterruptedError('已停止')
            if stage == 'ocr_stage' and reused and not force_detection and (not result.success or any(
                    getattr(result.data, key, None) is None for key in ('relic_title', 'relic_main_stat', 'relic_sub_stat'))):
                # OCR uncertainty is not evidence that geometry moved. Keep the
                # cache so a failed refresh can revalidate anchors on this frame.
                fallback_ms = (perf_counter() - started) * 1000
                relic, screenshot = await self._observe(force_detection=True, shot=input_shot)
                relic['timings_ms']['cache_fallback_ms'] = round(fallback_ms, 2)
                relic['timings_ms']['total_ms'] += round(fallback_ms, 2)
                return relic, screenshot
            if not result.success:
                raise ValueError(result.error or '识别失败')
            context.data[stage] = result.data
            if stage == 'detection_stage' and context.meta_data.get(AUTO_DETECT_RELIC_BOX, True):
                missing = [name for name in ('relic-title', 'relic-main-stat', 'relic-sub-stat') if not result.data.get(name)]
                if missing:
                    folder = Path(LOCAL_DATA_FOLDER) / 'diagnostics'
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / ('detection-' + uuid4().hex)
                    ok, encoded = cv2.imencode('.png', context.data['screenshot_stage']['image'])
                    if ok:
                        target.with_suffix('.png').write_bytes(encoded.tobytes())
                    target.with_suffix('.json').write_text(json.dumps({
                        'missing': missing,
                        'force_detection': force_detection,
                        'scan_mode': self.scan_mode,
                        'cache_available': bool(self.panel_cache.regions),
                        'regions': {k: v['box'] for k, v in result.data.items()},
                    }, ensure_ascii=False, indent=2), encoding='utf-8')
                    raise DetectionIncomplete('遗器区域定位不完整（' + '、'.join(missing) +
                        '）。原地重试后仍失败则停止；诊断已保存至 ' + str(target.with_suffix('.json')))
        shot = context.data['screenshot_stage']
        context.data['detection_source'] = 'cache' if reused else 'fresh'
        relic = recognize_states(shot['image'], context.data['ocr_stage'].model_dump())
        if self.scan_mode and not reused and context.meta_data.get(AUTO_DETECT_RELIC_BOX, True) and all(
                relic.get(key) for key in ('relic_title', 'relic_main_stat', 'relic_sub_stat')):
            self.panel_cache.remember(shot['image'], shot['window_info'].model_dump(), context.data['detection_stage'])
        relic['detection_source'] = context.data['detection_source']
        relic['detection_refresh_fallback'] = context.data.get('refresh_fallback', False)
        relic['detection_confidence'] = {name: region.get('confidence')
            for name, region in context.data['detection_stage'].items()}
        if any(region.get('confidence', 1) < .8 for region in context.data['detection_stage'].values()):
            relic['recognition_verified'] = False
            relic['detection_review_required'] = True
        self.check_focus()
        self.last = context
        if self.scan_mode:
            # Encoding belongs to the bounded persistence worker, not OCR.
            screenshot = shot.get('preview_image', shot['image'])
        else:
            ok, encoded = cv2.imencode('.png', shot['image'])
            if not ok:
                raise ValueError('无法保存截图')
            screenshot = encoded.tobytes()
        timings['total_ms'] = round((perf_counter() - started) * 1000, 2)
        relic['timings_ms'] = timings
        return relic, screenshot

    def prepare_capture(self):
        if not self.scan_mode or self.last is None or not self.panel_cache.anchors:
            return None
        return ScanCapture(self.last, self.panel_cache, read_profile())

    async def capture_next(self, capture):
        self.check_focus()
        if self.cancelled():
            raise InterruptedError('已停止')
        current = ModelManager().get_model(WindowInfoModel).predict(None)
        if current.model_dump() != capture.window:
            raise InterruptedError('窗口位置或尺寸变化，扫描停止')
        self.next(fast=True)
        started = perf_counter()
        stable_since = None
        previous = None
        layout_failure = None
        image = None
        samples = []
        while perf_counter() - started < 3:
            if self.cancelled():
                raise InterruptedError('已停止')
            self.check_focus()
            current = ModelManager().get_model(WindowInfoModel).predict(None)
            if current.model_dump() != capture.window:
                raise InterruptedError('窗口位置或尺寸变化，扫描停止')
            x, y, w, h = capture.rect
            region = WindowInfoOutput(left=current.left+x, top=current.top+y, width=w, height=h)
            image = await run_native(lambda: ModelManager().get_model(ScreenshotModel).predict(region))
            signature = capture.signature(image)
            samples.append(dict(elapsed_ms=round((perf_counter()-started)*1000, 2),
                baseline_delta=float(np.mean(np.abs(signature-getattr(capture, 'baseline', signature)))),
                previous_delta=None if previous is None else float(np.mean(np.abs(signature-previous)))))
            if capture.changed(signature):
                if previous is not None and capture.similar(signature, previous):
                    stable_since = stable_since or perf_counter()
                    if perf_counter() - stable_since >= .05:
                        self.check_focus()
                        if self.cancelled():
                            raise InterruptedError('已停止')
                        try:
                            shot = capture.accept(image, signature)
                        except PanelLayoutMismatch as error:
                            layout_failure = error
                        else:
                            shot['capture_ms'] = round((perf_counter()-started)*1000, 2)
                            shot['capture_polls'] = len(samples)
                            return shot
                else:
                    stable_since = None
            else:
                stable_since = None
            previous = signature
            await asyncio.sleep(.01)
        if layout_failure is not None:
            folder = Path(LOCAL_DATA_FOLDER) / 'diagnostics'
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / ('panel-layout-' + uuid4().hex)
            def save_layout_failure():
                ok, encoded = cv2.imencode('.png', image)
                if ok:
                    target.with_suffix('.png').write_bytes(encoded.tobytes())
                target.with_suffix('.json').write_text(json.dumps(dict(
                    window=capture.window, rect=capture.rect,
                    anchors=[dict(rect=r, mask=m.tolist()) for r, m in capture.anchors]), indent=2), encoding='utf-8')
            await run_native(save_layout_failure)
            raise InterruptedError('面板固定标记连续校验失败，已停止；诊断已保存至 ' + str(target.with_suffix('.json')))
        diagnostic = ''
        if image is not None:
            folder = Path(LOCAL_DATA_FOLDER) / 'diagnostics'
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / ('switch-timeout-' + uuid4().hex)
            def save_switch_failure():
                ok, encoded = cv2.imencode('.png', image)
                if ok:
                    target.with_suffix('.png').write_bytes(encoded.tobytes())
                target.with_suffix('.json').write_text(json.dumps(dict(
                    window=capture.window, rect=capture.rect, samples=samples), indent=2), encoding='utf-8')
            await run_native(save_switch_failure)
            diagnostic = '；诊断已保存至 ' + str(target.with_suffix('.json'))
        raise InterruptedError('换件后文字未变化或未稳定，扫描停止；可能为相同内容、导航未移动或列表末尾' + diagnostic)

    async def observe_frame(self, shot):
        # Retrying must use this immutable frame: the UI may already be one item ahead.
        result = await retry_observation(lambda: self._observe_worker(shot), self.check_focus, self.cancelled)
        result[0]['timings_ms']['capture_wait_ms'] = shot.get('capture_ms', 0)
        result[0]['timings_ms']['capture_polls'] = shot.get('capture_polls', 0)
        return result

    def next(self, fast=False):
        self.check_focus()
        if self.cancelled():
            raise InterruptedError('已停止')
        # The pipeline explicitly waits for a changed, stable panel. Avoid
        # PyAutoGUI's additional fixed pause only on that guarded path.
        pyautogui.press(self.navigation.next_key(), _pause=not fast)

    def mark(self):
        self.check_focus()
        if self.last is None:
            raise ValueError('尚未核验遗器')
        if self.scan_mode or self.last.data.get('detection_source') != 'fresh':
            raise ValueError('标记前必须重新定位，禁止使用扫描缓存点击')
        icon = self.last.data['detection_stage'].get('discard-icon')
        if not icon:
            raise ValueError('未识别到弃置图标，禁止点击')
        original = self.last.data['screenshot_stage']['window_info']
        current = ModelManager().get_model(WindowInfoModel).predict(None)
        if current != original:
            raise InterruptedError('窗口位置或尺寸变化')
        x, y = icon['box']['x_center'], icon['box']['y_center']
        if not (0 < x < current.width and 0 < y < current.height):
            raise ValueError('图标超出客户区')
        profile = read_profile()
        rx, ry, rw, rh = profile.get('discarded', {}).get('rect', [0, 0, 0, 0])
        if not (rx <= x < rx+rw and ry <= y < ry+rh):
            raise ValueError('弃置点击位置与已校准的弃置状态区域不一致')
        # Reject any panel change after OCR, including user navigation while it ran.
        fresh = ModelManager().get_model(ScreenshotModel).predict(current)
        original_image = self.last.data['screenshot_stage']['image']
        rects = [r['rect'] for r in profile.get('activation', []) if 'rect' in r]
        rects += [profile[k]['rect'] for k in ('locked', 'equipped', 'discarded', 'rarity') if k in profile]
        for name in ('relic-title', 'relic-main-stat', 'relic-sub-stat'):
            region = self.last.data['detection_stage'].get(name)
            if not region:
                raise ValueError('点击前无法核验完整遗器面板')
            box = region['box']
            rects.append([int(box['x_center']-box['width']/2), int(box['y_center']-box['height']/2), box['width'], box['height']])
        for px, py, pw, ph in rects:
            if min(px, py) < 0 or min(pw, ph) <= 0 or px+pw > current.width or py+ph > current.height:
                raise ValueError('校验区域越界')
            if not np.array_equal(fresh[py:py+ph, px:px+pw], original_image[py:py+ph, px:px+pw]):
                raise InterruptedError('识别后面板发生变化，取消点击')
        self.check_focus()
        if self.cancelled():
            raise InterruptedError('已停止')
        pyautogui.click(current.left + x, current.top + y)
