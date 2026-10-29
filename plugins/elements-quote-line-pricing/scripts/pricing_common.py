"""Shared file, table and identifier helpers for quote line pricing scripts."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re

DATA = Path(__file__).resolve().parent.parent / 'skills/explain-quote-line-pricing/data'


def table(name):
    with (DATA / (name + '.csv')).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sfid(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?', value):
        raise ValueError('Expected a 15 or 18 character Salesforce record Id')
    short = value[:15]
    suffix = ''.join('ABCDEFGHIJKLMNOPQRSTUVWXYZ012345'[
        sum(1 << index for index, char in enumerate(short[start:start + 5]) if char.isupper())
    ] for start in (0, 5, 10))
    return short + suffix


def valid_id(value):
    try:
        return sfid(value)
    except ValueError:
        return None


def literal(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"
