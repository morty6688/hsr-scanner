import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from app.core.batch_ocr import batch_read, text_rows


def panel(rows, golden=False):
    image = np.zeros((rows*40+10, 200, 3), dtype=np.uint8)
    color = [20, 150, 240] if golden else [245]*3
    for row in range(rows):
        image[row*40+10:row*40+30, 10:80] = color
        image[row*40+10:row*40+30, 160:185] = color
    return image


class BatchTests(unittest.TestCase):
    def test_missing_row_rejected(self):
        with self.assertRaises(ValueError):
            text_rows(panel(3), expected=4)

    def test_clipped_row_rejected(self):
        image = panel(1)[15:]
        with self.assertRaises(ValueError):
            text_rows(image, expected=1)

    def test_all_eleven_lines_use_one_recognizer_call(self):
        rec = Mock(return_value=([('test', .99)]*11, 0))
        groups, _ = batch_read(SimpleNamespace(model=SimpleNamespace(text_recognizer=rec)), panel(1, True), panel(1, True), panel(4))
        rec.assert_called_once()
        self.assertEqual(len(rec.call_args.args[0]), 11)
        self.assertEqual([len(group[0]) for group in groups], [1,1,1,4,4])

    def test_low_confidence_rejected(self):
        rec = Mock(return_value=([('test', .80)]*11, 0))
        with self.assertRaises(ValueError):
            batch_read(SimpleNamespace(model=SimpleNamespace(text_recognizer=rec)), panel(1, True), panel(1, True), panel(4))

    def test_misaligned_values_rejected_before_recognition(self):
        rec = Mock()
        subs = panel(4)
        subs[:,140:] = np.roll(subs[:,140:], 15, axis=0)
        with self.assertRaises(ValueError):
            batch_read(SimpleNamespace(model=SimpleNamespace(text_recognizer=rec)), panel(1, True), panel(1, True), subs)
        rec.assert_not_called()
