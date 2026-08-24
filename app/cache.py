# -*- coding: utf-8 -*-
"""cache.py — 运行快照 + 抓取缓存（原子保存、有效性校验、断点续跑）"""
from __future__ import annotations

import hashlib
import io
import json
import os
import time
from datetime import datetime
from pathlib import Path

from config import SNAPSHOT_DIR, CACHE_ROOT
from models import CrawlResult, PageStatus, ReportRow

SCHEMA_VERSION = 2


def make_run_id() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def data_signature(rows: list[ReportRow]) -> str:
    """影响同步/计算的源字段签名。"""
    h = hashlib.sha256()
    for r in rows:
        h.update(f'{r.asin}|{r.sku}|{r.size}|{r.normal_price}|{r.h_type}|'
                 f'{r.i_value}|{r.target_price};'.encode())
    return h.hexdigest()[:16]


# ---------------- 原始周报快照 ----------------
def save_snapshot(run_id: str, source_meta: dict,
                  rows_by_sheet: dict[str, list[ReportRow]]) -> Path:
    dir_ = SNAPSHOT_DIR / run_id
    dir_.mkdir(parents=True, exist_ok=True)
    data = {
        'source_meta': source_meta,
        'captured_at': datetime.now().isoformat(timespec='seconds'),
        'sheets': {sheet: [r.as_dict() for r in rows] for sheet, rows in rows_by_sheet.items()},
    }
    path = dir_ / 'source.json'
    _atomic_write(path, data)
    return path


def load_latest_snapshot() -> tuple[str, dict] | None:
    """返回最新的 (run_id, 快照 dict)；无快照返回 None"""
    if not SNAPSHOT_DIR.exists():
        return None
    runs = sorted([p for p in SNAPSHOT_DIR.iterdir() if p.is_dir()])
    if not runs:
        return None
    run_id = runs[-1].name
    path = runs[-1] / 'source.json'
    if not path.exists():
        return None
    try:
        with io.open(path, encoding='utf-8') as f:
            return run_id, json.load(f)
    except Exception:
        return None


# ---------------- 抓取缓存 ----------------
def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)          # 原子替换，断电不会留下半个 JSON


def cache_dir(run_id: str) -> Path:
    return CACHE_ROOT / run_id


def save_sheet_cache(run_id: str, sheet: str, rows: list[ReportRow],
                     crawls: list[CrawlResult], cfg: dict) -> None:
    path = cache_dir(run_id) / f'{sheet}.json'
    data = {
        'schema_version': SCHEMA_VERSION,
        'parser_rule_version': cfg['parser_rule_version'],
        'snapshot_id': run_id,
        'sheet': sheet,
        'asin_signature': data_signature(rows),
        'price_tolerance': str(cfg['price_tolerance']),
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'records': {c.asin: c.as_dict() for c in crawls},
    }
    _atomic_write(path, data)


def load_sheet_cache(run_id: str, sheet: str) -> dict | None:
    path = cache_dir(run_id) / f'{sheet}.json'
    if not path.exists():
        return None
    try:
        with io.open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def is_cache_valid(meta: dict | None, cfg: dict, sheet: str,
                   rows: list[ReportRow]) -> bool:
    """方案 15.3：全部相符才可复用"""
    if not meta:
        return False
    if meta.get('schema_version') != SCHEMA_VERSION:
        return False
    if meta.get('parser_rule_version') != cfg['parser_rule_version']:
        return False
    if meta.get('sheet') != sheet:
        return False
    if meta.get('asin_signature') != data_signature(rows):
        return False
    if str(meta.get('price_tolerance')) != str(cfg['price_tolerance']):
        return False
    try:
        created = datetime.fromisoformat(meta['created_at'])
        age_h = (datetime.now() - created).total_seconds() / 3600
    except Exception:
        return False
    if age_h > cfg['cache_max_age_hours']:
        return False
    return True


# ---------------- 断点续跑 ----------------
def _crawl_from_dict(d: dict) -> CrawlResult | None:
    """缓存记录 dict → CrawlResult（通用还原，包括异常记录）"""
    if not d:
        return None
    cr = CrawlResult(asin=d.get('asin') or '')
    try:
        cr.status = PageStatus(d.get('status') or 'ok')
    except ValueError:
        cr.status = PageStatus.CRAWL_ERROR
    cr.error = d.get('error') or ''
    cr.display_price = _dec(d.get('display_price'))
    cr.discount_type = d.get('discount_type') or ''
    cr.discount_value = d.get('discount_value') or ''
    cr.final_price = _dec(d.get('final_price'))
    cr.match = d.get('match') or ''
    cr.timestamp = d.get('timestamp') or ''
    cr.target_price = _dec(d.get('target_price'))
    cr.price_diff = _dec(d.get('price_diff'))
    cr.price_rule = d.get('price_rule') or ''
    # 促销证据（3.4：恢复后重新计算不得改变折扣类型）
    cr.promotion_raw = d.get('promotion_raw') or ''
    cr.coupon_pct = _dec(d.get('coupon_pct'))
    cr.coupon_amount = _dec(d.get('coupon_amount'))
    cr.coupon_final = _dec(d.get('coupon_final'))
    cr.code_pct = _dec(d.get('code_pct'))
    cr.save_pct = _dec(d.get('save_pct'))
    cr.expected_type = d.get('expected_type') or ''
    cr.expected_type_mismatch = bool(d.get('expected_type_mismatch'))
    for pc in d.get('price_candidates') or []:
        from models import PriceCandidate
        cr.price_candidates.append(PriceCandidate(
            rule=pc.get('rule') or '',
            raw_text=pc.get('raw_text') or '',
            value=_dec(pc.get('value')),
            visible=bool(pc.get('visible', True)),
        ))
    cr.attempt_count = int(d.get('attempt_count') or 0)
    cr.page_url = d.get('page_url') or ''
    cr.page_title = d.get('page_title') or ''
    return cr


def restore_from_cache(meta: dict, rows: list[ReportRow]) -> dict[str, CrawlResult]:
    """把可复用的缓存记录还原为 CrawlResult（按 asin 键）。"""
    out: dict[str, CrawlResult] = {}
    records = meta.get('records') or {}
    for r in rows:
        d = records.get(r.asin)
        if not d:
            continue
        st = d.get('status')
        if st not in ('ok', 'page_not_found', 'sold_out'):
            continue
        cr = _crawl_from_dict(d)
        if cr is None:
            continue
        if not cr.expected_type:
            cr.expected_type = r.h_type
        out[r.asin] = cr
    return out


def records_to_crawls(meta: dict) -> list[CrawlResult]:
    """还原全部缓存记录（push-only 使用，保留异常记录）"""
    out: list[CrawlResult] = []
    for d in (meta.get('records') or {}).values():
        cr = _crawl_from_dict(d)
        if cr is not None:
            out.append(cr)
    return out


def _dec(s) -> object:
    from decimal import Decimal, InvalidOperation
    if s in (None, ''):
        return None
    try:
        return Decimal(str(s))
    except InvalidOperation:
        return None


def cleanup_debug_dirs(debug_root: Path, keep_days: int = 7) -> None:
    """只保留最近 N 天的异常证据目录"""
    if not debug_root.exists():
        return
    now = time.time()
    for p in debug_root.iterdir():
        if not p.is_dir():
            continue
        try:
            age = (now - p.stat().st_mtime) / 86400
        except OSError:
            continue
        if age > keep_days:
            import shutil
            shutil.rmtree(p, ignore_errors=True)
