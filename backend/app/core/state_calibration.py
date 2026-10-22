"""Local calibration samples and independently labelled validation; no game actions."""
import copy
import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from app.constant import LOCAL_DATA_FOLDER
from app.core.local_profile import recognize_states

FIELDS = ('locked', 'equipped', 'discarded')


def missing_coverage(profile):
    cases = profile.get('validation', [])
    missing = []
    for key, label in zip(FIELDS, ('锁定', '装备', '弃置')):
        values = {case['expected'].get(key) for case in cases}
        for value, prefix in (('true', '已'), ('false', '未')):
            if value not in values:
                missing.append(prefix + label)
    return missing


class StateCalibration:
    def __init__(self, root=None):
        self.root = Path(root or LOCAL_DATA_FOLDER)
        self.directory = self.root / 'calibration'
        self.directory.mkdir(parents=True, exist_ok=True)

    def profile(self):
        path = self.root / 'recognition.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def save_profile(self, profile):
        path = self.root / 'recognition.json'
        if path.exists():
            backup = self.directory / 'backups'
            backup.mkdir(exist_ok=True)
            shutil.copy2(path, backup / (uuid4().hex + '.json'))
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)

    def sample(self, sample_id):
        if len(sample_id) != 32 or any(c not in '0123456789abcdef' for c in sample_id):
            raise ValueError('无效的校准截图编号')
        path = self.directory / (sample_id + '.json')
        if not path.is_file():
            raise ValueError('校准截图不存在')
        return json.loads(path.read_text(encoding='utf-8'))

    def image(self, sample_id):
        self.sample(sample_id)
        return cv2.imdecode(np.fromfile(self.directory / (sample_id + '.png'), dtype=np.uint8), cv2.IMREAD_COLOR)

    def capture(self, relic, screenshot):
        if not isinstance(screenshot, bytes):
            ok, encoded = cv2.imencode('.png', screenshot)
            if not ok:
                raise ValueError('无法保存校准截图')
            screenshot = encoded.tobytes()
        sample_id = uuid4().hex
        image = cv2.imdecode(np.frombuffer(screenshot, dtype=np.uint8), cv2.IMREAD_COLOR)
        sample = dict(id=sample_id, size=[image.shape[1], image.shape[0]],
                      digest=hashlib.sha256(screenshot).hexdigest(), relic=relic)
        (self.directory / (sample_id + '.png')).write_bytes(screenshot)
        (self.directory / (sample_id + '.json')).write_text(json.dumps(sample, ensure_ascii=False), encoding='utf-8')
        return sample

    def add_template(self, sample_id, field, value, rect, mode):
        if field not in FIELDS or value not in ('true', 'false'):
            raise ValueError('状态字段或取值无效')
        if mode not in ('color', 'glyph'):
            raise ValueError('匹配方式无效')
        sample, image = self.sample(sample_id), self.image(sample_id)
        profile = self.profile()
        if profile.get('size', sample['size']) != sample['size']:
            raise ValueError('截图尺寸与本机配置不同，请恢复校准时的窗口尺寸')
        x, y, w, h = rect
        if min(x, y) < 0 or min(w, h) < 3 or x+w > sample['size'][0] or y+h > sample['size'][1]:
            raise ValueError('框选范围无效')
        region = profile.get(field, {})
        if region and (region['rect'] != rect or region.get('mode', 'color') != mode):
            raise ValueError('正反状态必须使用相同区域和匹配方式；请先重置此字段')
        filename = f'templates/{field}-{value}-{uuid4().hex}.png'
        (self.root / 'templates').mkdir(exist_ok=True)
        cv2.imencode('.png', image[y:y+h, x:x+w])[1].tofile(str(self.root / filename))
        region.update(rect=rect, mode=mode)
        region.setdefault('templates', {})[value] = filename
        profile[field] = region
        profile['size'] = sample['size']
        profile.setdefault('training_digests', []).append(sample['digest'])
        profile['client_verified'] = False
        profile['validation'] = []
        self.save_profile(profile)
        return profile

    def reset(self, field):
        if field not in FIELDS:
            raise ValueError('状态字段无效')
        profile = self.profile()
        profile.pop(field, None)
        profile.update(client_verified=False, validation=[])
        self.save_profile(profile)
        return profile

    def validate(self, sample_id, expected):
        sample, profile = self.sample(sample_id), self.profile()
        if sample['digest'] in profile.get('training_digests', []):
            raise ValueError('制作模板的截图不能用作独立验证，请换另一件遗器重新截图')
        if any(v['digest'] == sample['digest'] for v in profile.get('validation', [])):
            raise ValueError('这张截图已验证，请换另一件遗器')
        required = list(FIELDS)
        if set(expected) != set(required):
            raise ValueError('请填写锁定、装备、弃置的真实状态')
        for key in required:
            choices = ('true', 'false')
            if expected[key] not in choices:
                raise ValueError('请填写有效状态：' + key)
        observed = recognize_states(self.image(sample_id), copy.deepcopy(sample['relic']), profile)
        actual = {key: str(observed.get(key)).lower() for key in FIELDS}
        errors = [dict(field=k, expected=expected[k], actual=actual[k]) for k in required if expected[k] != actual[k]]
        if not errors:
            profile.setdefault('validation', []).append(dict(id=sample_id, digest=sample['digest'], expected=expected))
        else:
            profile['validation'] = []
        # Any mismatch invalidates previously completed calibration, too.
        profile['client_verified'] = False
        self.save_profile(profile)
        return dict(errors=errors, actual=actual, profile=profile)

    def finish(self):
        profile = self.profile()
        missing = missing_coverage(profile)
        if missing:
            raise ValueError('尚需独立验证：' + '、'.join(missing))
        profile.update(client_verified=True, pending_unlock_cost=1)
        self.save_profile(profile)
        return profile
