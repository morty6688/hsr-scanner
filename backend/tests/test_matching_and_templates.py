import base64
import json
import lzma
import tempfile
import unittest
from pathlib import Path

import msgpack
from app.constant import RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE
from app.core.model_impls.relic_matcher_model import RelicMatcherModel, numeric_match, stat_key
from app.core.custom_exception import RelicMatchNotFoundException
from app.core.database import db
from app.core.orm_models.rating_template_orm import RatingTemplateORM
from app.core.orm_models.rating_rule_orm import RatingRuleORM
from app.core.utils.template_en_decode import TemplateEnDecoder
from app.core.network_models.responses.rating_template_response import GetRatingTemplateResponse
from app.core.network_models.responses.rating_rule_response import GetRatingRuleResponse


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.matcher = RelicMatcherModel(RELIC_SETS_FILE, RELIC_MAIN_STATS_FILE, RELIC_SUB_STATS_FILE)
        self.matcher.load()

    def test_chinese_and_english_have_same_identity(self):
        sets = json.loads(Path(RELIC_SETS_FILE).read_text(encoding='utf-8'))
        for entry in sets.values():
            for part in entry['parts']:
                self.assertEqual(self.matcher.match_relic_part(entry['parts'][part]),
                                 self.matcher.match_relic_part(entry['parts_cn'][part]))

    def test_unknown_name_not_guessed(self):
        with self.assertRaises(RelicMatchNotFoundException):
            self.matcher.match_relic_part('完全未知的新套装')

    def test_numeric_does_not_correct_digits_or_percent(self):
        self.assertIsNone(numeric_match('704', {'705': 15}))
        self.assertIsNone(numeric_match('5.8', {'5.8%': 1}))
        self.assertEqual(numeric_match('5.80％', {'5.8%': 1})[0], '5.8%')

    def test_chinese_flat_percentage_distinction(self):
        self.assertEqual(stat_key('生命值'), 'HP')
        self.assertEqual(stat_key('生命值Percentage'), 'HPPercentage')

    def test_current_client_main_stat_labels_and_units(self):
        self.assertEqual(self.matcher.match_relic_main_stat('能量恢复效率', '19.4%').level, 15)
        self.assertEqual(self.matcher.match_relic_main_stat('暴击伤害', '64.8%').level, 15)
        with self.assertRaises(RelicMatchNotFoundException):
            self.matcher.match_relic_main_stat('暴击伤害', '64.8')


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous = db.database
        if not db.is_closed():
            db.close()
        db.init(str(Path(self.directory.name) / 'test.db'))
        db.connect()
        db.create_tables([RatingTemplateORM, RatingRuleORM])
        self.codec = TemplateEnDecoder()

    def tearDown(self):
        db.close()
        db.init(self.previous)
        self.directory.cleanup()

    def test_legacy_decode_uses_frozen_order(self):
        value = dict(n='old', d='', a='', r=[dict(a=[0], b={'head': [0]}, c=[[0, 1]], d=[0])])
        encoded = base64.urlsafe_b64encode(lzma.compress(msgpack.packb(value))).decode()
        self.codec.decode_and_save(encoded)
        rule = RatingRuleORM.select().get()
        self.assertEqual(rule.fit_characters, ['Fu Xuan'])
        self.assertEqual(rule.set_names[0], self.codec.legacy_mappings['relic_set']['backward'][0])

    def test_new_roundtrip_ignores_current_dictionary_order(self):
        template = GetRatingTemplateResponse(id=1, name='local', description='', author='', in_use=False)
        rule = GetRatingRuleResponse(id=1, template_id=1,
            set_names=[next(iter(self.codec.mappings['relic_set']['forward']))],
            valuable_mains={'head': ['HP']}, valuable_subs=[dict(name='SPD', rating_scale=1)], fit_characters=['Fu Xuan'])
        encoded = self.codec.encode(template, [rule])
        self.codec.mappings = {}
        self.codec.decode_and_save(encoded)
        saved = RatingRuleORM.select().get()
        self.assertEqual(saved.fit_characters, ['Fu Xuan'])
        self.assertEqual(saved.valuable_subs, [{'name': 'SPD', 'rating_scale': 1}])

    def test_invalid_import_rolls_back_template(self):
        value = dict(n='bad', d='', a='', r=[dict(a=[999999], b={}, c=[], d=[])])
        encoded = base64.urlsafe_b64encode(lzma.compress(msgpack.packb(value))).decode()
        with self.assertRaises(KeyError):
            self.codec.decode_and_save(encoded)
        self.assertEqual(RatingTemplateORM.select().count(), 0)
