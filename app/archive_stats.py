# -*- coding: utf-8 -*-
"""汇总 R1.9 PoC manifest 的归档耗时和体积。"""
from __future__ import annotations

import json
import math
from pathlib import Path

from config import OUTPUT_DIR


def percentile(values: list[int], pct: float) -> float:
    """最近秩百分位；小样本不制造插值精度。"""
    ordered = sorted(values)
    return float(ordered[max(0, math.ceil(len(ordered) * pct) - 1)])


def main() -> None:
    root = OUTPUT_DIR / 'poc_resources'
    report = {'method': 'nearest_rank', 'groups': {}}
    for marketplace in ('us', 'ca'):
        records = []
        for path in root.glob(f'r1_9_{marketplace}_*.manifest.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            data['manifest'] = str(path)
            records.append(data)
        durations = [int(r['duration_ms']) for r in records]
        sizes = [int(r['size_bytes']) for r in records]
        report['groups'][marketplace.upper()] = {
            'sample_count': len(records),
            'statuses': {status: sum(1 for r in records
                                     if (r.get('page_status') or 'legacy_ok') == status)
                         for status in sorted({r.get('page_status') or 'legacy_ok'
                                               for r in records})},
            'duration_ms': {'p50': percentile(durations, .50),
                            'p95': percentile(durations, .95)} if durations else {},
            'size_bytes': {'p50': percentile(sizes, .50),
                           'p95': percentile(sizes, .95)} if sizes else {},
        }
    out = root / 'r1_9_archive_stats.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
