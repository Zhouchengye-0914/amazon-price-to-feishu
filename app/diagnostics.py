# -*- coding: utf-8 -*-
"""diagnostics.py — 异常页证据保存（crawl_error/parse_error/captcha）"""
from __future__ import annotations

import io
import json
from pathlib import Path

from config import DEBUG_DIR
from models import CrawlResult


def save_evidence(run_id: str, sheet: str, cr: CrawlResult, tab, cfg: dict) -> Path | None:
    """保存截图 + HTML + 诊断 JSON，目录 outputs/debug/{run_id}/{sheet}/{asin}/"""
    if cr.status.value not in ('crawl_error', 'parse_error'):
        return None
    d = DEBUG_DIR / run_id / sheet / cr.asin
    d.mkdir(parents=True, exist_ok=True)
    try:
        tab.get_screenshot(path=str(d / 'screenshot.png'))
    except Exception:
        pass
    try:
        html = tab.html
        if html:
            (d / 'page.html').write_text(html, encoding='utf-8', errors='replace')
    except Exception:
        pass
    diag = {
        'asin': cr.asin, 'status': cr.status.value, 'error': cr.error,
        'url': cr.page_url, 'title': cr.page_title,
        'candidates': [{'rule': c.rule, 'raw': c.raw_text,
                        'value': str(c.value) if c.value is not None else None}
                       for c in cr.price_candidates],
        'promotion_raw': cr.promotion_raw,
        'attempt_count': cr.attempt_count,
        'saved_at': cr.timestamp,
    }
    with io.open(d / 'diagnostic.json', 'w', encoding='utf-8') as f:
        json.dump(diag, f, ensure_ascii=False, indent=2)
    return d
