import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import cv2
from app.core.scan_session import persist_record, public_session
from app.core.preview_image import thumbnail_file
from app.core.title_identity import exact_identity
from app.core.model_impls.relic_matcher_model import RelicMatcherModel
from app.constant import RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE


class ScanPerformanceTests(unittest.TestCase):
    def test_records_append_without_rewriting_checkpoint_and_original_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'session.json').write_text('{}')
            image = np.zeros((800,400,3), np.uint8)
            for i in range(3):
                persist_record(path, 'session', dict(id=str(i),screenshot=f'{i}.png'), image)
            self.assertEqual((path/'session.json').read_text(), '{}')
            self.assertEqual([json.loads(line)['id'] for line in (path/'session.jsonl').read_text().splitlines()], ['0','1','2'])
            original = (path/'0.png').read_bytes()
            thumb = thumbnail_file(path/'0.png')
            self.assertEqual(cv2.imread(str(thumb)).shape[:2], (640,320))
            self.assertEqual((path/'0.png').read_bytes(), original)

    def test_public_poll_excludes_raw_ocr_but_preserves_count_and_decision(self):
        record = dict(id='0',screenshot='0.png', ambiguous=False,execution='pending',
            relic=dict(relic_title=None,raw_ocr=['large data']),assessment=dict(decision='review'))
        current = dict(id='x',status='scanning',message='',counts={},rules={'private':'large'},records=[record])
        result = public_session(current)
        self.assertEqual(len(result['records']), 1)
        self.assertNotIn('raw_ocr',result['records'][0]['relic'])
        self.assertNotIn('rules',result)
        self.assertIn('raw_ocr',current['records'][0]['relic'])

    def test_set_and_part_require_exact_unique_high_confidence_labels(self):
        matcher = RelicMatcherModel(RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE)
        matcher.load()
        labels = [('风举云飞的勇烈', .99)]
        result = exact_identity(matcher, labels, [('头部', .99)])
        self.assertEqual(result, matcher.match_relic_part('勇烈的玄枵面甲'))
        self.assertIsNone(exact_identity(matcher,[('风举云飞的勇列',.99)],[('头部',.99)]))
        self.assertIsNone(exact_identity(matcher,labels,[('头部',.94)]))
        self.assertIsNone(exact_identity(matcher,labels,[('头部',.99),('手部',.99)]))
