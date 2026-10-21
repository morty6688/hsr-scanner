import unittest
import numpy as np
from app.core.substat_activation import activation, clean_name, merge_rows


def line(text, x=0, confidence=.99):
    return [[[x, 0], [x+9, 0], [x+9, 9], [x, 9]], (text, confidence)]


class ActivationTests(unittest.TestCase):
    def test_white_is_active(self):
        self.assertEqual(activation(np.full((10, 10, 3), 245, dtype=np.uint8), line('速度'), 0, 4), 'active')

    def test_grey_requires_explicit_fourth_unlock(self):
        image = np.full((10, 10, 3), 120, dtype=np.uint8)
        self.assertEqual(activation(image, line('效果命中（+3可激活）'), 3, 4), 'pending')
        self.assertEqual(activation(image, line('效果命中'), 3, 4), 'unknown')
        self.assertEqual(activation(image, line('效果命中（+3可激活）'), 0, 4), 'unknown')
        self.assertEqual(activation(image, line('效果命中（+3可激活）', confidence=.8), 3, 4), 'unknown')

    def test_merge_suffix_and_strip_exact_hint(self):
        result = merge_rows([[line('效果命中'), line('（+3可激活）', x=10)]])
        self.assertEqual(len(result[0]), 1)
        self.assertEqual(clean_name(result[0][0][1][0]), '效果命中')
        self.assertEqual(clean_name('效果命中（+6可激活）'), '效果命中（+6可激活）')
