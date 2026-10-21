"""Re-score a saved session offline without loading OCR or sending game input."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.review import evaluate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('session', type=Path)
parser.add_argument('--threshold', type=float, required=True, help='0 < threshold <= 1')
args = parser.parse_args()
if not 0 < args.threshold <= 1:
    parser.error('threshold must be in (0, 1]')
session = json.loads(args.session.read_text(encoding='utf-8'))
for record in session['records']:
    relic = record['relic']
    rules = session['rules'].get((relic.get('relic_title') or {}).get('title'), [])
    print(json.dumps({'id': record['id'], **evaluate(relic, rules, args.threshold)}, ensure_ascii=False))
