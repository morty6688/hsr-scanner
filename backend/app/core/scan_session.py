"""Persisted two-pass review. Only this module can issue a discard click."""
import asyncio
import hashlib
import json
import threading
from pathlib import Path
from uuid import uuid4

from app.constant import LOCAL_DATA_FOLDER
from app.core.review import evaluate, fingerprint


class ScanSession:
    def __init__(self, adapter, rules, directory=None):
        self.adapter = adapter
        self.rules_provider = rules
        self.directory = Path(directory or LOCAL_DATA_FOLDER) / 'sessions'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.current = None
        self.task = None
        self.stop = threading.Event()
        self.adapter.cancelled = self.stop.is_set

    def rules(self):
        return self.rules_provider()

    def revision(self):
        environment = self.adapter.revision() if hasattr(self.adapter, 'revision') else ''
        return hashlib.sha256(json.dumps([self.rules(), environment], sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def save(self):
        if self.current:
            target = self.directory / (self.current['id'] + '.json')
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(self.current, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(target)

    def busy(self):
        return self.task is not None and not self.task.done()

    def request_stop(self):
        self.stop.set()

    async def observe(self):
        if self.stop.is_set():
            raise InterruptedError('已停止')
        self.adapter.check_focus()
        result = await asyncio.wait_for(self.adapter.observe(), timeout=30)
        if self.stop.is_set():
            raise InterruptedError('已停止')
        return result

    def assess(self, relic):
        title = (relic.get('relic_title') or {}).get('title')
        return evaluate(relic, self.current['rules'].get(title, []), self.current['threshold'])

    def start_scan(self):
        if self.busy():
            raise ValueError('已有扫描或标记任务')
        self.stop.clear()
        if hasattr(self.adapter, 'reset_navigation'):
            self.adapter.reset_navigation()
        self.current = dict(id=str(uuid4()), status='scanning', records=[], threshold=None,
            rules=self.rules(), revision=self.revision(), message='', counts={})
        self.save()
        self.task = asyncio.create_task(self.scan())
        return self.current

    async def scan(self):
        try:
            # Allows returning focus from the desktop app to the game.
            await asyncio.sleep(3)
            seen = set()
            for index in range(3000):
                relic, screenshot = await self.observe()
                if self.revision() != self.current['revision']:
                    raise InterruptedError('模板或识别配置变化，扫描已停止，请重新扫描')
                key = fingerprint(relic)
                if key in seen:
                    for record in self.current['records']:
                        if record['fingerprint'] == key:
                            record['ambiguous'] = True
                    self.current['message'] = '遇到重复内容或导航未移动，扫描停止；重复项禁止自动标记。请核对是否已到列表末尾，或存在属性完全相同的遗器。'
                    break
                seen.add(key)
                name = f"{self.current['id']}-{index}.png"
                (self.directory / name).write_bytes(screenshot)
                self.current['records'].append(dict(id=str(index), fingerprint=key, relic=relic,
                    screenshot=name, assessment=self.assess(relic), ambiguous=False, execution='pending'))
                self.save()
                if self.stop.is_set():
                    raise InterruptedError('已停止')
                self.adapter.check_focus()
                self.adapter.next()
                await asyncio.sleep(.5)
            else:
                self.current['message'] = '达到 3000 件上限，扫描停止。'
        except Exception as error:
            self.current['message'] = str(error)
        finally:
            self.current['status'] = 'preview'
            self.save()

    def reprice(self, threshold):
        if self.busy() or not self.current:
            raise ValueError('请先完成扫描')
        if not 0 < threshold <= 1:
            raise ValueError('阈值须大于 0 且不超过 100%')
        self.current['threshold'] = threshold
        self.current['rules'] = self.rules()
        self.current['revision'] = self.revision()
        for record in self.current['records']:
            record['assessment'] = self.assess(record['relic'])
        self.save()
        return self.current

    def start_execute(self, session_id, selected):
        if self.busy() or not self.current or self.current['id'] != session_id:
            raise ValueError('会话已变化或任务仍在运行')
        if self.current['status'] != 'preview' or self.revision() != self.current['revision']:
            raise ValueError('模板或会话已变化，请重新预览')
        selected = set(selected)
        eligible = {r['id'] for r in self.current['records'] if not r['ambiguous'] and r['assessment']['decision'] == 'discard' and r['execution'] == 'pending'}
        if not selected or not selected.issubset(eligible):
            raise ValueError('清单包含不可执行项')
        self.stop.clear()
        if hasattr(self.adapter, 'reset_navigation'):
            self.adapter.reset_navigation()
        self.current['status'] = 'executing'
        self.current['counts'] = dict(success=0, skipped=0, failed=0, unexecuted=len(selected))
        self.save()
        self.task = asyncio.create_task(self.execute(selected))
        return self.current

    async def execute(self, selected):
        counts = self.current['counts']
        try:
            await asyncio.sleep(3)
            last = max(int(i) for i in selected)
            for record in self.current['records'][:last+1]:
                if self.revision() != self.current['revision']:
                    raise InterruptedError('模板已变化，已停止')
                relic, _ = await self.observe()
                if self.revision() != self.current['revision']:
                    raise InterruptedError('模板或识别配置变化，已停止')
                if fingerprint(relic) != record['fingerprint']:
                    raise InterruptedError('遗器或排序发生变化。请回到扫描起点并重新扫描。')
                if record['id'] in selected:
                    assessment = self.assess(relic)
                    if assessment['decision'] != 'discard':
                        record['execution'] = 'skipped'
                        counts['skipped'] += 1
                        counts['unexecuted'] -= 1
                    else:
                        # No await between final stop/focus checks and click.
                        if self.stop.is_set():
                            raise InterruptedError('已停止')
                        self.adapter.check_focus()
                        self.adapter.mark()
                        record['execution'] = 'unverified'
                        counts['unexecuted'] -= 1
                        self.save()
                        await asyncio.sleep(.4)
                        after, _ = await self.observe()
                        if fingerprint(after) != record['fingerprint'] or after.get('discarded') is not True:
                            record['execution'] = 'failed'
                            counts['failed'] += 1
                            raise InterruptedError('标记后核验失败，已停止且不会重试点击')
                        record['execution'] = 'success'
                        counts['success'] += 1
                    self.save()
                if int(record['id']) < last:
                    if self.stop.is_set():
                        raise InterruptedError('已停止')
                    self.adapter.check_focus()
                    self.adapter.next()
                    await asyncio.sleep(.5)
            self.current['message'] = '本次标记完成'
        except Exception as error:
            for record in self.current['records']:
                if record['execution'] == 'unverified':
                    record['execution'] = 'failed'
                    counts['failed'] += 1
            self.current['message'] = str(error)
        finally:
            self.current['status'] = 'finished'
            self.save()
