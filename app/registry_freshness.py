"""Durable guard against silently reusing one weekly registry row forever."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from runtime_state import atomic_json


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def assert_registry_fresh(store, selection, now: datetime, max_age_days: float) -> dict:
    """Persist first sighting of a registry identity and reject it after max age."""
    if now.tzinfo is None:
        raise RuntimeError('登记表新鲜度检查要求带时区时间')
    path = store.root / 'registry_freshness.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'periods': {}}
    periods = data.setdefault('periods', {})
    key = str(selection.period_id)
    entry = periods.get(key)
    if entry and entry.get('source_url') != selection.source_url:
        raise RuntimeError('同一登记序号的周报链接发生变化，禁止重置新鲜度')
    if not entry:
        manifest = store.load(key) or {}
        first = manifest.get('created_at') or now.isoformat()
        try:
            _aware(first)
        except (TypeError, ValueError):
            first = now.isoformat()
        entry = {'period_id': key, 'source_url': selection.source_url,
                 'first_seen_at': first, 'row_number': getattr(selection, 'row_number', 0)}
        periods[key] = entry
    age = (now.astimezone(timezone.utc) - _aware(entry['first_seen_at']).astimezone(timezone.utc)).total_seconds()
    if age < 0:
        raise RuntimeError('登记表首次发现时间在未来，禁止运行')
    entry['last_seen_at'] = now.isoformat()
    atomic_json(path, data)
    if age > float(max_age_days) * 86400:
        raise RuntimeError(
            f'登记表当前链接已连续使用 {age / 86400:.1f} 天，超过 {max_age_days:g} 天；'
            '请新增本周链接和更大序号后再运行')
    return entry
