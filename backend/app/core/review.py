"""Offline scoring and review policy. No screen, network or mouse dependencies."""
import hashlib
import json
import math

ALGORITHM_VERSION = 'local-v2-known-fourth'


def fingerprint(relic):
    value = {k: relic.get(k) for k in ('relic_title', 'relic_main_stat', 'relic_sub_stat', 'rarity')}
    value['relic_sub_stat'] = sorted(value.get('relic_sub_stat') or [], key=lambda s: s['name'])
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def score_rule(relic, rule):
    """Normalized rolls, with known pending rolls, never random fourth-stat guessing.

    Unknown activation consumes no assumed unlock: the upper bound stays conservative.
    A known pending stat requires an explicitly recognized unlock cost (0 or 1).
    """
    main = relic['relic_main_stat']
    subs = relic['relic_sub_stat']
    weights = {s['name']: s['rating_scale'] for s in rule['valuable_subs']}
    weights.pop(main['name'], None)
    if any(not math.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError('模板权重必须是有限非负数')
    best = max(weights.values(), default=0)
    denominator = sum(sorted(weights.values(), reverse=True)[:4]) + 5 * best
    if denominator <= 0:
        raise ValueError('模板没有有效权重')
    remaining = 5 - main['level'] // 3
    active = sum(weights.get(s['name'], 0) * min(s['score']) for s in subs if s.get('activation') == 'active')
    upper_base = sum(weights.get(s['name'], 0) * max(s['score']) for s in subs)
    pending = [s for s in subs if s.get('activation') == 'pending']
    cost = relic.get('pending_unlock_cost')
    if pending and cost in (0, 1):
        remaining -= cost
    if remaining < 0:
        raise ValueError('待解锁词条与强化等级冲突')
    # Three actually recognized stats remain uncertain; bound the missing one optimistically.
    if len(subs) < 4:
        upper_base += max((w for n, w in weights.items() if n not in {s['name'] for s in subs}), default=0)
    return dict(score=min(active / denominator, 1), potential=min((upper_base + remaining * best) / denominator, 1),
                current_confirmed=all(s.get('activation') in ('active', 'pending') for s in subs),
                characters=rule.get('fit_characters', []), type='actual' if main['level'] == 15 else 'potential')


def evaluate(relic, rules, threshold=None):
    result = dict(decision='review', reasons=[], scores=[], algorithm_version=ALGORITHM_VERSION)
    if relic.get('state_conflict'):
        result['reasons'] = ['锁定与弃置状态识别冲突，请人工确认']
        return result
    if relic.get('detection_review_required'):
        result['reasons'] = ['属性区域定位置信度偏低，仅供预览，请人工确认']
        return result
    main, subs = relic.get('relic_main_stat'), relic.get('relic_sub_stat')
    if not relic.get('relic_title') or not main or not subs:
        result['reasons'] = ['识别信息不完整'] + relic.get('recognition_errors', [])
        return result
    names = [s['name'] for s in subs]
    part = relic['relic_title'].get('part')
    common = ['生命百分比', '攻击百分比', '防御百分比']
    allowed = {
        'head': ['生命'], 'hand': ['攻击'],
        'body': common + ['暴击率', '暴击伤害', '治疗量加成', '效果命中'],
        'feet': common + ['速度'],
        'rope': common + ['击破特攻', '能量回复效率'],
        'sphere': common + [element + '属性伤害提高' for element in ['物理', '火', '冰', '雷', '风', '量子', '虚数']],
    }
    if main['name'] not in allowed.get(part, []):
        result['reasons'] = ['主属性与遗器部位不符或部位未知']
        return result
    if (not isinstance(main.get('level'), int) or not 0 <= main['level'] <= 15 or
        not 3 <= len(subs) <= 4 or len(set(names)) != len(names) or main['name'] in names or
        any(not s.get('score') or any(not math.isfinite(v) or v <= 0 for v in s['score']) for s in subs)):
        result['reasons'] = ['词条或等级校验失败']
        return result
    matching = [r for r in rules if main['name'] in r['valuable_mains']]
    try:
        result['scores'] = sorted([score_rule(relic, r) for r in matching], key=lambda s: s['potential'], reverse=True)
    except (ValueError, TypeError, KeyError) as error:
        result['reasons'] = [str(error)]
        return result
    if relic.get('locked') is True or relic.get('equipped') is True:
        result.update(decision='keep', reasons=['已锁定或已装备'])
        return result
    if ('速度' in names or main['name'] in ('速度', '能量回复效率', '治疗量加成') or
            {'暴击率', '暴击伤害'}.issubset(names)):
        result.update(decision='keep', reasons=['通用保留规则：速度、稀有主属性或双暴散件'])
        return result
    reasons = []
    if not matching:
        reasons.append('没有覆盖此遗器的有效模板')
    if relic.get('rarity') != 5:
        reasons.append('未确认五星遗器')
    if any(relic.get(k) is None for k in ('locked', 'equipped', 'discarded')):
        reasons.append('锁定、装备或弃置状态未知')
    if relic.get('discarded') is True:
        reasons.append('已经标记弃置，不重复点击')
    if len(subs) != 4 or any(s.get('activation') not in ('active', 'pending') for s in subs):
        reasons.append('词条生效状态尚未确认，不能仅按显示数量推断')
    if any(s.get('activation') == 'pending' for s in subs) and relic.get('pending_unlock_cost') not in (0, 1):
        reasons.append('待解锁词条是否消耗强化次数未知')
    if sum(s.get('activation') == 'pending' for s in subs) > 1 or (main['level'] >= 3 and any(s.get('activation') == 'pending' for s in subs)):
        reasons.append('待解锁词条数量或强化等级与本算法不符')
    if relic.get('recognition_verified') is not True:
        reasons.append('识别配置尚未通过本机验证')
    if threshold is None or not math.isfinite(threshold) or not 0 < threshold <= 1:
        reasons.append('请预览评分并设置本次清理阈值')
    if reasons:
        result['reasons'] = reasons
        return result
    if max(s['potential'] for s in result['scores']) >= threshold:
        result.update(decision='keep', reasons=['当前分或潜力上界达到保留阈值'])
    else:
        result.update(decision='discard', reasons=['所有适用模板的潜力上界均低于本次阈值'])
    return result
