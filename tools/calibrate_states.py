"""Create local state templates from saved game screenshots (no game input)."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import cv2
import numpy as np
from app.constant import LOCAL_DATA_FOLDER
from app.core.local_profile import recognize_states


def image(path):
    result = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if result is None:
        raise ValueError(f'无法读取截图: {path}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add')
    add.add_argument('screenshot', type=Path)
    add.add_argument('--field', required=True, choices=['locked', 'equipped', 'discarded', 'activation0', 'activation1', 'activation2', 'activation3'])
    add.add_argument('--state', required=True)
    add.add_argument('--rect', nargs=4, type=int, required=True, metavar=('X', 'Y', 'W', 'H'))
    verify = sub.add_parser('verify')
    verify.add_argument('cases', type=Path, help='Independent screenshot expectations JSON')
    verify.add_argument('--unlock-cost', type=int, choices=[0, 1], required=True)
    args = parser.parse_args()
    root = Path(LOCAL_DATA_FOLDER)
    path = root / 'recognition.json'
    profile = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'activation': [{}, {}, {}, {}]}
    if args.command == 'add':
        valid = ['active', 'pending', 'unknown'] if args.field.startswith('activation') else ([str(n) for n in range(2, 6)] if args.field == 'rarity' else ['true', 'false'])
        if args.state not in valid:
            raise ValueError(f'状态必须为 {valid}')
        shot = image(args.screenshot)
        size = [shot.shape[1], shot.shape[0]]
        if 'size' in profile and profile['size'] != size:
            raise ValueError('截图尺寸与已有配置不同，请使用另一份配置')
        profile['size'] = size
        x, y, w, h = args.rect
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > size[0] or y+h > size[1]:
            raise ValueError('框选超出截图')
        region = profile['activation'][int(args.field[-1])] if args.field.startswith('activation') else profile.setdefault(args.field, {})
        if 'rect' in region and region['rect'] != args.rect:
            raise ValueError('同一状态区域的正反模板必须使用相同矩形')
        filename = f'templates/{args.field}-{args.state}.png'
        (root / 'templates').mkdir(exist_ok=True)
        cv2.imencode('.png', shot[y:y+h, x:x+w])[1].tofile(str(root / filename))
        region['rect'] = args.rect
        region.setdefault('templates', {})[args.state] = filename
        profile['client_verified'] = False
    else:
        cases = json.loads(args.cases.read_text(encoding='utf-8'))
        coverage = {key: set() for key in ['locked', 'equipped', 'discarded', 'activation0', 'activation1', 'activation2', 'activation3']}
        for case in cases:
            observed = recognize_states(image(args.cases.parent / case['image']), {'relic_sub_stat': [{} for _ in range(4)]})
            for key in coverage:
                expected = case['expected'][key]
                actual = observed['relic_sub_stat'][int(key[-1])].get('activation') if key.startswith('activation') else observed.get(key)
                if actual != expected:
                    raise ValueError(f"{case['image']} 的 {key}: 期望 {expected}，得到 {actual}")
                coverage[key].add(expected)
        for key in coverage:
            required = ({'active', 'pending'} if key == 'activation3' else {'active'}) if key.startswith('activation') else {True, False}
            if not required.issubset(coverage[key]):
                raise ValueError(f'{key} 缺少正反例覆盖')
        profile['pending_unlock_cost'] = args.unlock_cost
        profile['client_verified'] = True
        profile['validation_cases'] = str(args.cases.resolve())
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    print('已保存本机识别配置；client_verified =', profile['client_verified'])


if __name__ == '__main__':
    main()
