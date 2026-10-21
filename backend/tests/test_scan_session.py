import copy
import tempfile
import unittest
from unittest.mock import patch

from app.core.scan_session import ScanSession
from app.core.review import fingerprint
from test_review import sample, RULE


class Adapter:
    def __init__(self, relic):
        self.relic = relic
        self.clicks = 0
        self.focus = True
        self.click_works = True
        self.scan_mode = None

    def set_scan_mode(self, enabled):
        self.scan_mode = enabled

    def check_focus(self):
        if not self.focus:
            raise InterruptedError('失焦')

    async def observe(self):
        return copy.deepcopy(self.relic), b'fake png'

    def mark(self):
        self.clicks += 1
        if self.click_works:
            self.relic['discarded'] = True

    def next(self):
        pass


async def no_sleep(_):
    pass


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        r = sample(); r['relic_main_stat']['level'] = 15
        self.adapter = Adapter(r)
        self.runner = ScanSession(self.adapter, lambda: {'test': [RULE]}, self.directory.name)
        self.sleep = patch('app.core.scan_session.asyncio.sleep', no_sleep)
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        self.directory.cleanup()

    def prepare(self):
        runner = self.runner
        runner.current = dict(id='test-session', status='preview', threshold=.5, rules=runner.rules(),
                              revision=runner.revision(), message='', counts={})
        r = copy.deepcopy(self.adapter.relic)
        runner.current['records'] = [dict(id='0', relic=r, fingerprint=fingerprint(r), ambiguous=False,
                                         assessment=runner.assess(r), execution='pending')]

    async def test_duplicate_scan_stops_and_protects(self):
        self.runner.start_scan()
        await self.runner.task
        self.assertEqual(self.adapter.clicks, 0)
        self.assertTrue(self.runner.current['records'][0]['ambiguous'])
        self.assertEqual(self.runner.current['status'], 'preview')
        self.assertTrue(self.adapter.scan_mode)

    async def test_successful_verified_mark(self):
        self.prepare(); self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 1)
        self.assertEqual(self.runner.current['counts']['success'], 1)
        self.assertFalse(self.adapter.scan_mode)

    async def test_stopped_does_not_click(self):
        self.prepare(); self.runner.start_execute('test-session', ['0']); self.runner.request_stop()
        await self.runner.task
        self.assertEqual(self.adapter.clicks, 0)

    async def test_focus_loss_does_not_click(self):
        self.prepare(); self.adapter.focus = False
        self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 0)

    async def test_changed_relic_does_not_click(self):
        self.prepare(); self.adapter.relic['relic_main_stat']['level'] = 12
        self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 0)

    async def test_already_marked_never_toggle(self):
        self.prepare(); self.adapter.relic['discarded'] = True
        self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 0)
        self.assertEqual(self.runner.current['counts']['skipped'], 1)

    async def test_failed_click_no_retry(self):
        self.prepare(); self.adapter.click_works = False
        self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 1)
        self.assertEqual(self.runner.current['counts']['failed'], 1)

    async def test_stale_session_and_non_candidate_rejected(self):
        self.prepare()
        for session_id, selected in [('stale', ['0']), ('test-session', ['1'])]:
            with self.assertRaises(ValueError):
                self.runner.start_execute(session_id, selected)
        self.assertEqual(self.adapter.clicks, 0)

    async def test_rules_change_rejected(self):
        self.prepare(); self.runner.rules_provider = lambda: {}
        with self.assertRaises(ValueError):
            self.runner.start_execute('test-session', ['0'])

    async def test_stop_during_recognition(self):
        self.prepare()
        original = self.adapter.observe
        async def stop_during_read():
            self.runner.request_stop()
            return await original()
        self.adapter.observe = stop_during_read
        self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 0)

    async def test_stop_after_click_records_uncertain_attempt(self):
        self.prepare()
        original = self.adapter.mark
        def click_then_stop():
            original()
            self.runner.request_stop()
        self.adapter.mark = click_then_stop
        self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 1)
        self.assertEqual(self.runner.current['counts'], dict(success=0, skipped=0, failed=1, unexecuted=0))

    async def test_rules_changed_during_recognition(self):
        self.prepare()
        original = self.adapter.observe
        async def change_during_read():
            self.runner.rules_provider = lambda: {}
            return await original()
        self.adapter.observe = change_during_read
        self.runner.start_execute('test-session', ['0']); await self.runner.task
        self.assertEqual(self.adapter.clicks, 0)


if __name__ == '__main__':
    unittest.main()
