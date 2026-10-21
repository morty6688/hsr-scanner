"""Explicit one-time asset preparation. Never imported or run by the application."""
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'backend/app/assets'


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    commit = json.loads(fetch('https://api.github.com/repos/Mar-7th/StarRailRes/commits/master'))['sha']
    base = f'https://raw.githubusercontent.com/Mar-7th/StarRailRes/{commit}/'
    def index(lang, name):
        return json.loads(fetch(base + f'index_min/{lang}/{name}.json'))
    sets = {lang: index(lang, 'relic_sets') for lang in ('cn', 'en')}
    relics = {lang: index(lang, 'relics') for lang in ('cn', 'en')}
    chars = {lang: index(lang, 'characters') for lang in ('cn', 'en')}
    paths = index('cn', 'paths')
    existing = json.loads((ROOT / 'relic/relic_sets.json').read_text(encoding='utf-8'))
    parts = dict(HEAD='head', HAND='hand', BODY='body', FOOT='feet', NECK='sphere', OBJECT='rope')
    new_sets = {}
    for sid, data in sets['en'].items():
        members = [r for r in relics['en'].values() if r['set_id'] == sid and r['rarity'] == 5]
        if not members:
            continue
        old = existing.get(data['name'], {})
        new_sets[data['name']] = dict(id=sid, name=sets['cn'][sid]['name'], icon=old.get('icon', ''),
            isInner=members[0]['type'] in ('NECK', 'OBJECT'),
            parts={parts[r['type']]: r['name'] for r in members},
            parts_cn={parts[r['type']]: relics['cn'][r['id']]['name'] for r in members},
            part_ids={parts[r['type']]: r['id'] for r in members})
    old_chars = json.loads((ROOT / 'character/character_meta.json').read_text(encoding='utf-8'))
    new_chars = {}
    for cid, data in chars['en'].items():
        key = data['name'] if data['name'] != '{NICKNAME}' else f'Trailblazer ({cid})'
        # Some forms share a display name; preserve their stable identity.
        if key in new_chars:
            key += f' ({cid})'
        old = old_chars.get(key, {})
        new_chars[key] = dict(id=cid, name=chars['cn'][cid]['name'].replace('{NICKNAME}', '开拓者') +
            (f' ({cid})' if '{NICKNAME}' == data['name'] else ''), icon=old.get('icon', ''),
            paths=paths[data['path']]['name'])
    write_json(ROOT / 'relic/relic_sets.json', new_sets)
    # Legacy template names remain selectable; new data takes precedence.
    write_json(ROOT / 'character/character_meta.json', {**old_chars, **new_chars})
    hashes = {}
    for kind in ('det', 'rec'):
        url = f'https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_{kind}_infer.tar'
        raw = fetch(url)
        hashes[url] = hashlib.sha256(raw).hexdigest()
        dest = ROOT / 'paddle/ch' / kind
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for member in archive.getmembers():
                if member.isfile() and Path(member.name).name in ('inference.pdmodel', 'inference.pdiparams', 'inference.pdiparams.info'):
                    (dest / Path(member.name).name).write_bytes(archive.extractfile(member).read())
    write_json(ROOT / 'local_manifest.json', dict(schema_version=1, source=base, source_commit=commit,
        game_version=None, client_verified=False, note='社区数据快照，尚未与本机客户端逐项核验；不代表已支持最新版本',
        set_count=len(new_sets), character_count=len(new_chars), models=hashes))
    print(f'Prepared {len(new_sets)} sets, {len(new_chars)} characters and Chinese OCR models.')


if __name__ == '__main__':
    main()
