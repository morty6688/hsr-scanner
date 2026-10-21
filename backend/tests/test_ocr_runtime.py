import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.core.ocr_runtime import configure_runtime


class RuntimeTests(unittest.TestCase):
    def test_default_cpu_and_explicit_missing_gpu(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('app.core.ocr_runtime.LOCAL_DATA_FOLDER', directory), \
             patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configure_runtime(), 'cpu')
            Path(directory, 'ocr-runtime.json').write_text(json.dumps({'device':'gpu'}), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                configure_runtime()
            os.environ['HSR_OCR_DEVICE'] = 'cpu'
            self.assertEqual(configure_runtime(), 'cpu')

    def test_invalid_mode_rejected(self):
        with patch.dict(os.environ, {'HSR_OCR_DEVICE':'invalid'}):
            with self.assertRaises(ValueError):
                configure_runtime()
