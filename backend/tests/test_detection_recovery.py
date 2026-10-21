import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from app.core.model_impls.yolo_model import YOLOModel


def result(rows):
    return [SimpleNamespace(boxes=SimpleNamespace(
        xywhn=np.array([r[0] for r in rows]), cls=[r[1] for r in rows], conf=[r[2] for r in rows]))]


class DetectionRecoveryTests(unittest.TestCase):
    def run_detection(self, enabled, confidence=.831, stripe=False):
        model = YOLOModel('unused')
        model.model = Mock()
        model.model.names = {0: 'relic-title', 1: 'relic-main-stat', 2: 'relic-sub-stat', 3: 'discard-icon'}
        model.model.predict.side_effect = [result([
            ([.7,.1,.2,.05],0,.91), ([.7,.4,.2,.05],1,.796), ([.7,.5,.2,.1],2,.87)]), result([
            ([.7,.4,.2,.05],1,confidence), ([.7,.2,.2,.05],0,.99), ([.9,.3,.02,.02],3,.99)])]
        image = np.zeros((200,400,3), dtype=np.uint8)
        if stripe:
            image[75:85,225:228] = [30,160,230]
        regions = model.predict(dict(image=image,
            window_info=SimpleNamespace(width=400,height=200), allow_multiscale=enabled))
        return model, regions

    def test_missing_main_recovered_without_replacing_title_or_click_target(self):
        model, regions = self.run_detection(True)
        self.assertEqual(model.model.predict.call_count, 2)
        self.assertEqual(regions['relic-main-stat']['confidence'], .831)
        self.assertEqual(regions['relic-title']['confidence'], .91)
        self.assertNotIn('discard-icon', regions)

    def test_recovery_does_not_lower_confidence_threshold(self):
        _, regions = self.run_detection(True, .79)
        self.assertNotIn('relic-main-stat', regions)

    def test_execution_does_not_enable_preview_recovery(self):
        model, regions = self.run_detection(False)
        self.assertEqual(model.model.predict.call_count, 1)
        self.assertNotIn('relic-main-stat', regions)

    def test_weak_preview_keeps_actual_confidence_and_requires_gold_anchor(self):
        _, regions = self.run_detection(True, .79, stripe=True)
        self.assertEqual(regions['relic-main-stat']['confidence'], .796)
        _, regions = self.run_detection(True, .79, stripe=False)
        self.assertNotIn('relic-main-stat', regions)

    def test_execution_rejects_weak_box_even_with_gold_anchor(self):
        _, regions = self.run_detection(False, .79, stripe=True)
        self.assertNotIn('relic-main-stat', regions)
