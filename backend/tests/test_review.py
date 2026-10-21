import copy
import unittest
from app.core.review import evaluate, score_rule, fingerprint


def sample():
    return dict(relic_title={'title': 'test', 'part': 'head'}, relic_main_stat={'name': '生命', 'level': 0},
        relic_sub_stat=[dict(name=n, score=[1.0], activation='active') for n in ['攻击', '防御', '效果命中', '效果抵抗']],
        rarity=5, locked=False, equipped=False, discarded=False, recognition_verified=True)


RULE = dict(valuable_mains=['生命'], valuable_subs=[dict(name='攻击', rating_scale=1)], fit_characters=['test'])


class ReviewTests(unittest.TestCase):
    def test_low_detection_confidence_blocks_discard_even_with_verified_profile(self):
        r = sample(); r['relic_main_stat']['level'] = 15
        r['detection_review_required'] = True
        self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'review')

    def test_no_template_is_not_discard(self):
        self.assertEqual(evaluate(sample(), [], .5)['decision'], 'review')

    def test_no_implicit_old_threshold(self):
        self.assertEqual(evaluate(sample(), [RULE])['decision'], 'review')

    def test_unknown_state_blocks_discard(self):
        r = sample(); r['locked'] = None
        self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'review')

    def test_four_visible_not_four_active(self):
        r = sample(); r['relic_sub_stat'][0]['activation'] = 'unknown'
        self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'review')
        self.assertEqual(score_rule(r, RULE)['score'], 0)

    def test_known_fourth_not_random(self):
        r = sample(); r['relic_sub_stat'][0]['activation'] = 'pending'; r['pending_unlock_cost'] = 1
        s = score_rule(r, RULE)
        self.assertEqual(s['score'], 0)
        self.assertAlmostEqual(s['potential'], 5 / 6)
        r['pending_unlock_cost'] = 0
        self.assertEqual(score_rule(r, RULE)['potential'], 1)

    def test_unknown_unlock_cost_blocks(self):
        r = sample(); r['relic_sub_stat'][0]['activation'] = 'pending'
        self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'review')

    def test_remaining_potential_keeps(self):
        self.assertEqual(evaluate(sample(), [RULE], .5)['decision'], 'keep')

    def test_max_level_low_score_candidate(self):
        r = sample(); r['relic_main_stat']['level'] = 15
        self.assertEqual(evaluate(r, [RULE], .5)['decision'], 'discard')

    def test_protected_never_discard(self):
        for key in ('locked', 'equipped'):
            r = sample(); r[key] = True
            self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'keep')

    def test_already_marked(self):
        r = sample(); r['discarded'] = True
        self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'review')

    def test_duplicate_and_main_overlap(self):
        for name in ('生命', '防御'):
            r = sample(); r['relic_sub_stat'][0]['name'] = name
            self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'review')

    def test_fingerprint_ignores_order_and_mark(self):
        r = sample(); other = copy.deepcopy(r)
        other['relic_sub_stat'].reverse(); other['discarded'] = True
        self.assertEqual(fingerprint(r), fingerprint(other))

    def test_impossible_main_for_slot(self):
        r = sample(); r['relic_title']['part'] = 'hand'
        self.assertEqual(evaluate(r, [RULE], 1)['decision'], 'review')


if __name__ == '__main__':
    unittest.main()
