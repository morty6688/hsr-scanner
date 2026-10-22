import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import cv2
from app.core.scan_session import persist_record, public_session
from app.core.preview_image import thumbnail_file
from app.core.title_identity import exact_identity, cross_checked_identity
from app.core.model_impls.relic_matcher_model import RelicMatcherModel
from app.constant import RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE


class ScanPerformanceTests(unittest.TestCase):
    def test_part_reread_preserves_threshold_and_rejects_conflicting_labels(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from app.core.title_identity import read_part_labels
        model = SimpleNamespace(predict=Mock(return_value=[[[[[1,1],[20,1],[20,20],[1,20]], ('躯干', .92)]]]),
            model=SimpleNamespace(text_recognizer=Mock(return_value=([('躯干', .99), ('躯干', .98)], 0))))
        labels = read_part_labels(model, np.full((30,30,3), 240, np.uint8))
        self.assertIn(('躯干', .99), labels)
        matcher = RelicMatcherModel(RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE)
        matcher.load()
        self.assertIsNotNone(cross_checked_identity(matcher, [('宝命长存的者', .99)], labels, '者的承露羽衣'))
        model.model.text_recognizer.return_value = ([('躯干', .99), ('头部', .99)], 0)
        labels = read_part_labels(model, np.full((30,30,3), 240, np.uint8))
        self.assertIsNone(cross_checked_identity(matcher, [('宝命长存的者', .99)], labels, '者的承露羽衣'))
        model.model.text_recognizer.return_value = ([('躯干', .94), ('躯干', .94)], 0)
        labels = read_part_labels(model, np.full((30,30,3), 240, np.uint8))
        self.assertIsNone(cross_checked_identity(matcher, [('宝命长存的者', .99)], labels, '者的承露羽衣'))
        model.predict.return_value[0][0][1] = ('躯干', .99)
        model.model.text_recognizer.reset_mock()
        read_part_labels(model, np.full((30,30,3), 240, np.uint8))
        model.model.text_recognizer.assert_not_called()

    def test_same_omission_requires_title_set_part_and_unique_candidate(self):
        matcher = RelicMatcherModel(RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE)
        matcher.load()
        for part in ('头部', '手部', '躯干', '脚部'):
            # Use the actual local title for each part, avoiding hand-maintained aliases.
            from app.core.title_identity import PARTS
            details = next(d for d in matcher.relic_sets.values() if d['name'] == '宝命长存的莳者')
            title = details['parts_cn'][PARTS[part]]
            result = cross_checked_identity(matcher, [('宝命长存的者', .99)], [(part, .99)], title.replace('莳', ''))
            self.assertEqual(result, matcher.match_relic_part(title))
        labels, parts = [('宝命长存的者', .99)], [('头部', .99)]
        self.assertIsNone(cross_checked_identity(matcher, labels, parts, '莳者的复明义眼'))
        self.assertIsNone(cross_checked_identity(matcher, labels, parts, '者的复明义目'))
        self.assertIsNone(cross_checked_identity(matcher, [('宝命长存的者', .9)], parts, '者的复明义眼'))
        self.assertIsNone(cross_checked_identity(matcher, labels, [('手部', .99)], '者的复明义眼'))
        self.assertIsNone(cross_checked_identity(matcher, labels, [('头部', .99), ('手部', .99)], '者的复明义眼'))
        self.assertIsNone(cross_checked_identity(matcher, [('宝命长存莳者', .99)], parts, '者的复明义眼'))
        self.assertIsNone(cross_checked_identity(matcher, [('宝命长存者', .99)], parts, '者复明义眼'))
        import copy
        duplicate = copy.deepcopy(details)
        duplicate['parts'] = {k: 'ambiguous' for k in duplicate['parts']}
        matcher.relic_sets['duplicate'] = duplicate
        self.assertIsNone(cross_checked_identity(matcher, labels, parts, '者的复明义眼'))

    def test_all_known_unsupported_title_characters_resolve_by_exact_set_and_part(self):
        from app.core.title_identity import PARTS
        matcher = RelicMatcherModel(RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE)
        matcher.load()
        unsupported = set('鞲枵坼辔桹')
        covered = set()
        for details in matcher.relic_sets.values():
            for part, title in details.get('parts_cn', {}).items():
                rare = set(title) & unsupported
                if not rare:
                    continue
                covered |= rare
                label = next(name for name, key in PARTS.items() if key == part)
                result = cross_checked_identity(matcher, [(details['name'], .99)], [(label, .99)], None)
                self.assertEqual(result, matcher.match_relic_part(title))
        self.assertEqual(covered, unsupported)

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
