import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app.core.local_profile import recognize_states, grey_glyph_error, equipped_text_matches, equipment_background_error
from app.core.state_calibration import StateCalibration


class StateCalibrationTests(unittest.TestCase):
    def test_equipment_background_ignores_lore_but_rejects_blank_or_dark_bar(self):
        template = np.full((90, 600, 3), (150, 110, 70), np.uint8)
        changed = template.copy()
        cv2.putText(template, 'OLD LORE', (10, 30), 0, .8, (230, 230, 230), 2)
        cv2.putText(changed, 'DIFFERENT TEXT', (200, 65), 0, .8, (230, 230, 230), 2)
        self.assertLess(equipment_background_error(template, changed), .025)
        equipped = changed.copy()
        equipped[30:60] = (75, 50, 25)
        self.assertGreater(equipment_background_error(template, equipped), .05)
        self.assertEqual(equipment_background_error(template, np.zeros_like(template)), 1)

    def test_mutually_exclusive_icons_and_grey_require_positive_counterpart(self):
        from app.core.review import evaluate
        profile = dict(size=[120, 60], client_verified=True)
        icons = {}
        for value, char in [('false', 'U'), ('true', 'X')]:
            icon = np.zeros((60, 60, 3), np.uint8)
            cv2.putText(icon, char, (15, 45), 0, 1, (255, 255, 255), 3)
            icons[value] = icon
            cv2.imwrite(str(self.root / (value + '.png')), icon)
        for key, x in [('locked', 0), ('discarded', 60)]:
            profile[key] = dict(rect=[x, 0, 60, 60], mode='glyph', templates={v: v+'.png' for v in icons})
        grey = (icons['false'].astype(float) * (110/255)).astype(np.uint8)
        for left, right, expected in [
            (icons['true'], grey, (True, False)),
            (grey, icons['true'], (False, True)),
            (icons['false'], icons['false'], (False, False)),
            (grey, icons['false'], (None, False)),
            (icons['true'], np.zeros_like(grey), (True, None)),
        ]:
            result = recognize_states(np.concatenate([left, right], axis=1), dict(confidence=1), profile)
            self.assertEqual((result['locked'], result['discarded']), expected)
            self.assertFalse(result['state_conflict'])
        conflict = recognize_states(np.concatenate([icons['true']]*2, axis=1), dict(confidence=1), profile)
        self.assertTrue(conflict['state_conflict'])
        self.assertIsNone(conflict['locked'])
        self.assertIsNone(conflict['discarded'])
        self.assertFalse(conflict['recognition_verified'])
        self.assertEqual(evaluate(conflict, [])['decision'], 'review')

    def test_grey_glyph_requires_shape_not_just_grey_pixels(self):
        reference = np.zeros((60, 60), np.uint8)
        cv2.putText(reference, 'U', (15, 45), 0, 1, 1, 3)
        grey = np.repeat((reference*110)[:, :, None], 3, axis=2)
        self.assertLess(grey_glyph_error(reference.astype(bool), grey), .12)
        self.assertEqual(grey_glyph_error(reference.astype(bool), np.zeros_like(grey)), 1)
        self.assertGreater(grey_glyph_error(reference.astype(bool), np.full_like(grey, 110)), .12)

    def test_equipment_label_ignores_avatar_but_requires_matching_text(self):
        template = np.zeros((100, 400, 3), np.uint8)
        cv2.putText(template, 'EQUIPPED', (150, 65), 0, .8, (80, 190, 230), 2)
        actual = template.copy()
        actual[10:90, 10:100] = (240, 240, 240)
        self.assertTrue(equipped_text_matches(template, actual))
        self.assertFalse(equipped_text_matches(template, np.zeros_like(actual)))
        other = np.zeros_like(actual)
        cv2.putText(other, 'NOT HERE', (150, 65), 0, .8, (80, 190, 230), 2)
        self.assertFalse(equipped_text_matches(template, other))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.calibration = StateCalibration(self.root)
        self.root_patch = patch('app.core.local_profile.LOCAL_DATA_FOLDER', str(self.root))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.temp.cleanup)
        self.relic = dict(confidence=1, relic_sub_stat=[dict(activation='active') for _ in range(4)])

    def sample(self, white=False, marker=0):
        image = np.zeros((80, 100, 3), np.uint8)
        image[10:20, 10:20] = 255 if white else 80
        image[0, 0] = marker
        return self.calibration.capture(copy.deepcopy(self.relic), cv2.imencode('.png', image)[1].tobytes())

    def test_unknown_without_profile_or_wrong_size(self):
        result = recognize_states(np.zeros((10, 10, 3), np.uint8), dict(locked=False, recognition_verified=True), {})
        self.assertIsNone(result['locked'])
        self.assertFalse(result['recognition_verified'])
        self.assertEqual(result['rarity'], 5)
        self.assertEqual(result['rarity_source'], 'user_assumed')

    def test_capture_accepts_scan_array_without_changing_coordinates(self):
        shot = np.zeros((80, 100, 3), np.uint8)
        shot[15, 90] = [20, 40, 60]
        sample = self.calibration.capture(self.relic, shot)
        self.assertEqual(sample['size'], [100, 80])
        np.testing.assert_array_equal(self.calibration.image(sample['id']), shot)

    def test_pairs_required_and_missing_file_fails_closed(self):
        a, b = self.sample(), self.sample(True)
        profile = self.calibration.add_template(a['id'], 'locked', 'false', [10, 10, 10, 10], 'color')
        self.assertIsNone(recognize_states(self.calibration.image(a['id']), {}, profile)['locked'])
        profile = self.calibration.add_template(b['id'], 'locked', 'true', [10, 10, 10, 10], 'color')
        self.assertIs(recognize_states(self.calibration.image(a['id']), {}, profile)['locked'], False)
        self.assertIs(recognize_states(self.calibration.image(b['id']), {}, profile)['locked'], True)
        (self.root / profile['locked']['templates']['true']).unlink()
        self.assertIsNone(recognize_states(self.calibration.image(a['id']), {}, profile)['locked'])

    def test_backup_and_invalidation(self):
        self.calibration.save_profile(dict(client_verified=True, validation=[{}]))
        a = self.sample()
        profile = self.calibration.add_template(a['id'], 'locked', 'false', [10, 10, 10, 10], 'color')
        self.assertFalse(profile['client_verified'])
        self.assertEqual(profile['validation'], [])
        self.assertEqual(len(list((self.calibration.directory/'backups').glob('*.json'))), 1)
        with self.assertRaises(ValueError):
            self.calibration.add_template(a['id'], 'locked', 'true', [11, 10, 10, 10], 'color')

    def test_training_cannot_validate_and_no_incomplete_approval(self):
        a = self.sample()
        self.calibration.add_template(a['id'], 'locked', 'false', [10, 10, 10, 10], 'color')
        with self.assertRaises(ValueError):
            self.calibration.validate(a['id'], {})
        with self.assertRaises(ValueError):
            self.calibration.finish()

    def test_glyph_rejects_ambiguous_and_retains_ocr_activation(self):
        a = self.sample(True)
        self.calibration.add_template(a['id'], 'locked', 'false', [10, 10, 10, 10], 'glyph')
        profile = self.calibration.add_template(a['id'], 'locked', 'true', [10, 10, 10, 10], 'glyph')
        profile['activation'] = [{}, {}, {}, {}]
        result = recognize_states(self.calibration.image(a['id']), copy.deepcopy(self.relic), profile)
        self.assertIsNone(result['locked'])
        self.assertEqual(result['relic_sub_stat'][0]['activation'], 'active')

    def test_validation_requires_coverage_and_unique_samples(self):
        expected = dict(locked='false', equipped='false', discarded='false')
        observed = dict(locked=False, equipped=False, discarded=False, rarity=5, **self.relic)
        with patch('app.core.state_calibration.recognize_states', return_value=observed):
            a = self.sample(marker=1)
            self.assertFalse(self.calibration.validate(a['id'], expected)['errors'])
            with self.assertRaises(ValueError):
                self.calibration.validate(a['id'], expected)
        with self.assertRaises(ValueError):
            self.calibration.finish()  # state coverage, not a fixed sample count
        observed.update(locked=True, equipped=True, discarded=True, rarity=4)
        observed['relic_sub_stat'][3]['activation'] = 'pending'
        expected.update(locked='true', equipped='true', discarded='true')
        with patch('app.core.state_calibration.recognize_states', return_value=observed):
            self.calibration.validate(self.sample(marker=13)['id'], expected)
        self.assertTrue(self.calibration.finish()['client_verified'])
        with patch('app.core.state_calibration.recognize_states', return_value={}):
            result = self.calibration.validate(self.sample(marker=14)['id'], expected)
        self.assertTrue(result['errors'])
        self.assertFalse(result['profile']['client_verified'])
        with self.assertRaises(ValueError):
            self.calibration.finish()

    def test_untrusted_sample_paths_rejected(self):
        with self.assertRaises(ValueError):
            self.calibration.sample('../recognition')


if __name__ == '__main__':
    unittest.main()
