# -*- coding: utf-8 -*-
"""main.py — 主流程编排：CLI → 同步飞书原始周报 → 抓取计算 → 六列写回

CLI（方案 19 + 当前测试方案修正）：
  --sheets PD03,PD17       只处理指定子表
  --asins B0...,B0...      只对指定 ASIN 实时抓取（默认 dry-run，在线专项测试）
  --limit 10               每表前 N 行（自动隐含 --dry-run）
  --no-headless            显示浏览器
  --force-fetch            忽略缓存重新抓取
  --fetch-only             同步数据并抓取，不写飞书六列
  --push-only              用最近快照缓存推送，不抓取
  --dry-run                读取+计算+本地输出，不改飞书
  --resume                 恢复最近有效的未完成批次（跨进程断点续跑）
  --run-id <id>            明确恢复指定批次
  --force-push             技术异常比例超阈值时仍写入（人工确认恢复推送）
  --inspect-feishu-layout  只读预检目标表布局，不写任何数据
  --migrate-feishu-columns [--sheets ...] --confirm  一次性旧列清理 + 六列表头
"""
from __future__ import annotations

import argparse
import json
import logging
import queue
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from amazon.crawler import AmazonBrowser
from cache import (
    cleanup_debug_dirs, is_cache_valid, load_latest_snapshot, load_sheet_cache,
    make_run_id, records_to_crawls, restore_from_cache, save_sheet_cache,
    save_snapshot,
)
from config import BASE_DIR, DEBUG_DIR, LOG_DIR, OUTPUT_DIR, ensure_dirs, load_config
from diagnostics import save_evidence
from exporters import export_results
from feishu import FeishuClient, col_letter
from models import CrawlResult, PageStatus, ReportRow
from pricing import compute_result, dec


# ============================ 日志 ============================
def setup_logger(cfg: dict) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    log_file = LOG_DIR / f'run_{ts}.log'
    logger = logging.getLogger('daily')
    logger.setLevel(logging.INFO)
    if logger.handlers:
        for h in list(logger.handlers):
            logger.removeHandler(h)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logs = sorted(LOG_DIR.glob('run_*.log'))
    while len(logs) > cfg['log_keep']:
        logs[0].unlink()
        logs = logs[1:]
    return logger


def p(logger, msg: str):
    print(msg, flush=True)
    logger.info(msg)


# ============================ CLI ============================
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description='PP周报·亚马逊价格校验 + 飞书六列回写')
    ap.add_argument('--sheets', default=None, help='逗号分隔(默认美国站 11 表)')
    ap.add_argument('--asins', default=None, help='逗号分隔 ASIN，只抓指定商品(自动 dry-run)')
    ap.add_argument('--limit', type=int, default=None, help='每表前 N 行(自动隐含 --dry-run)')
    ap.add_argument('--no-headless', action='store_true', help='显示浏览器调试')
    ap.add_argument('--force-fetch', action='store_true', help='忽略缓存重新抓取')
    ap.add_argument('--fetch-only', action='store_true', help='同步+抓取，不写飞书六列')
    ap.add_argument('--push-only', action='store_true', help='用最近快照缓存推送，不抓取')
    ap.add_argument('--dry-run', action='store_true', help='只读+计算+本地输出，不改飞书')
    ap.add_argument('--resume', action='store_true', help='恢复最近有效的未完成批次')
    ap.add_argument('--run-id', default=None, help='明确恢复指定批次(排错用)')
    ap.add_argument('--force-push', action='store_true', help='异常比例超阈值时仍写入飞书')
    ap.add_argument('--inspect-feishu-layout', action='store_true',
                    help='只读预检目标表布局(表头行/ASIN起始行/旧列/J:O)')
    ap.add_argument('--migrate-feishu-columns', action='store_true',
                    help='一次性清理旧列并写六列表头(可配合 --sheets 限定范围)')
    ap.add_argument('--confirm', action='store_true', help='确认执行破坏性迁移')
    args = ap.parse_args()

    # 互斥规则
    if args.push_only and args.fetch_only:
        raise SystemExit('--push-only 与 --fetch-only 互斥')
    if args.push_only and args.dry_run:
        raise SystemExit('--push-only 与 --dry-run 互斥')
    if args.push_only and (args.force_fetch or args.resume):
        raise SystemExit('--push-only 不能与 --force-fetch/--resume 同用')
    if args.inspect_feishu_layout and (args.migrate_feishu_columns or args.fetch_only or args.push_only):
        raise SystemExit('--inspect-feishu-layout 是独立只读命令，不能与其他写操作同用')
    if args.migrate_feishu_columns and (args.fetch_only or args.push_only or args.dry_run or args.limit):
        raise SystemExit('列迁移不能与抓取/推送参数同时使用(--sheets 可用于限定范围)')
    if args.limit:
        args.dry_run = True                # --limit 隐含 --dry-run
    if args.asins:
        args.dry_run = True                # --asins 在线专项测试默认 dry-run
    if args.asins and args.limit:
        raise SystemExit('--asins 与 --limit 不能同用')
    return args


# ============================ 数据还原 ============================
def row_from_dict(d: dict) -> ReportRow:
    return ReportRow(
        row_num=int(d.get('row_num') or 0),
        asin=d.get('asin') or '',
        sku=d.get('sku') or '',
        size=d.get('size') or '',
        normal_price=dec(d.get('normal_price')),
        h_type=d.get('h_type') or '',
        i_value=dec(d.get('i_value')),
        target_price=dec(d.get('target_price')),
    )


def assemble_crawls(rows: list[ReportRow], results_map: dict[str, CrawlResult],
                    cfg: dict, logger) -> list[CrawlResult]:
    """按行顺序组装，补计算字段；缺失任务标 crawl_error"""
    crawls = []
    for r in rows:
        cr = results_map.get(r.asin)
        if cr is None:
            cr = CrawlResult(asin=r.asin, status=PageStatus.CRAWL_ERROR, error='任务未完成')
        if not cr.expected_type:
            cr.expected_type = r.h_type
        compute_result(r, cr, cfg['price_tolerance'])
        crawls.append(cr)
    return crawls


# ============================ 抓取 ============================
def run_fetch(run_id: str, sheet: str, rows: list[ReportRow], cfg: dict,
              headless: bool, force_fetch: bool, logger) -> list[CrawlResult]:
    reuse: dict[str, CrawlResult] = {}
    if not force_fetch:
        meta = load_sheet_cache(run_id, sheet)
        if is_cache_valid(meta, cfg, sheet, rows):
            reuse = restore_from_cache(meta, rows)
    todo = [r for r in rows if r.asin not in reuse]
    p(logger, f'[抓取] {sheet} 共{len(rows)}行 | 缓存复用 {len(reuse)} | 需抓 {len(todo)} | workers={cfg["workers"]}')

    results_map: dict[str, CrawlResult] = dict(reuse)
    if todo:
        q: queue.Queue = queue.Queue()
        for r in todo:
            q.put(r)
        done_count = [0]
        lock = threading.Lock()
        save_state = [0]
        total = len(todo)

        def _save_partial():
            # 锁内只复制结果快照，锁外写盘与重算（3.1 防死锁）
            with lock:
                snapshot = dict(results_map)
            crawls = assemble_crawls(rows, snapshot, cfg, logger)
            save_sheet_cache(run_id, sheet, rows, crawls, cfg)
            logger.info(f'[缓存] {sheet} 增量保存 {len(snapshot)} 条')

        workers = min(max(1, int(cfg['workers'])), len(todo))
        # 单浏览器 + 多 tab：一个 ChromiumPage，每个线程持有一个独立 tab（并发模型）
        browser = AmazonBrowser(headless=headless, us_zip=cfg['us_zip'],
                                proxy=cfg.get('proxy') or None,
                                tabs=workers)
        try:
            if not browser.setup():
                raise RuntimeError('浏览器初始化失败(请确认美国 VPN 节点)')

            def _worker_loop():
                while True:
                    try:
                        row = q.get_nowait()
                    except queue.Empty:
                        break
                    tab = browser.acquire()
                    try:
                        cr, tab = browser.fetch_with_retry(tab, row, cfg)
                        if cr.status in (PageStatus.CRAWL_ERROR, PageStatus.PARSE_ERROR):
                            save_evidence(run_id, sheet, cr, tab, cfg)
                    except Exception as e:
                        cr = CrawlResult(asin=row.asin)
                        cr.status = PageStatus.CRAWL_ERROR
                        cr.error = f'{type(e).__name__}: {str(e)[:80]}'
                        from datetime import datetime
                        cr.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    finally:
                        browser.release(tab)
                    should_save = False
                    with lock:
                        results_map[row.asin] = cr
                        done_count[0] += 1
                        n = done_count[0]
                        if n % cfg['save_every'] == 0 and n // cfg['save_every'] > save_state[0]:
                            save_state[0] = n // cfg['save_every']
                            should_save = True
                    if n % 10 == 0:
                        print(f'  [{n}/{total}] {row.asin} {cr.status.value:<14} {cr.duration_ms}ms', flush=True)
                    if should_save:
                        _save_partial()

            threads = [threading.Thread(target=_worker_loop, daemon=True)
                       for _ in range(workers)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            browser.quit()

    crawls = assemble_crawls(rows, results_map, cfg, logger)
    save_sheet_cache(run_id, sheet, rows, crawls, cfg)
    return crawls


# ============================ 汇总 ============================
def summarize(results_by_sheet: dict[str, list[CrawlResult]], cfg: dict, logger) -> float:
    """返回技术异常比例（crawl_error + parse_error）/ 抓取行总数。
    source_data_invalid 单列，不参与一致性与技术异常分母（4.x）。"""
    st = Counter()
    mt = Counter()
    dt = Counter()
    total = 0
    for crawls in results_by_sheet.values():
        for cr in crawls:
            st[cr.status.value] += 1
            mt[cr.match.split('(')[0] if cr.match else '-'] += 1
            dt[cr.discount_type or '-'] += 1
            if cr.status != PageStatus.SOURCE_INVALID:
                total += 1
    p(logger, f'=== 状态: ' + ' '.join(f'{k}={v}' for k, v in st.most_common()))
    p(logger, f'=== 一致性: ' + ' '.join(f'{k}={v}' for k, v in mt.most_common()))
    p(logger, f'=== 类型: ' + ' '.join(f'{k}={v}' for k, v in dt.most_common()))
    if total:
        err = st.get('crawl_error', 0) + st.get('parse_error', 0)
        ratio = err / total
        if ratio > cfg['max_error_ratio_for_push']:
            p(logger, f'[告警] 技术异常占比 {ratio:.1%} 超过阈值 '
                      f'{cfg["max_error_ratio_for_push"]:.0%}，不应将结果直接视为售罄推送')
        return ratio
    return 0.0


# ============================ 批次恢复（3.3） ============================
def resolve_run_id(cfg: dict, rows_by_sheet: dict[str, list[ReportRow]],
                   args, logger) -> str:
    if args.run_id:
        p(logger, f'[恢复] 使用指定批次 {args.run_id}')
        return args.run_id
    if args.resume:
        snap = load_latest_snapshot()
        if snap:
            rid, _ = snap
            for sheet, rows in rows_by_sheet.items():
                meta = load_sheet_cache(rid, sheet)
                if meta and is_cache_valid(meta, cfg, sheet, rows):
                    p(logger, f'[恢复] 找到有效未完成批次 {rid}（{sheet} 缓存有效）')
                    return rid
        p(logger, '[恢复] 没有可恢复的有效批次，创建新批次')
    return make_run_id()


# ============================ 飞书流程 ============================
def full_flow(fc: FeishuClient, cfg: dict, sheets: list[str], args, logger) -> None:
    t_start = time.time()
    # 1. 解析源/目标表
    source_obj, source_type = fc.resolve_wiki_obj(cfg['feishu_source_wiki'])
    target_ss = fc.resolve_wiki(cfg['feishu_target_wiki'])
    p(logger, f'[飞书] 源表 {source_obj} (类型 {source_type}) / 目标表 {target_ss}')

    # 2. 读原始周报（同一份快照）→ 无效行分离
    if source_type == 'file':
        # 原始表是上传的 xlsx 文件 → 下载解析（公式读缓存值，缺则本地兜底）
        rows_by_sheet, meta, invalid = fc.read_source_file(source_obj, sheets, cfg)
    else:
        rows_by_sheet, meta, invalid = fc.read_source_sheets(source_obj, sheets, cfg)
    if not rows_by_sheet:
        raise RuntimeError('原始周报没有读到任何有效数据，请检查源 wiki 与子表名')
    if invalid:
        p(logger, f'[数据完整性] {len(invalid)} 行源数据无效（目标价/正常售价为空），不进入抓取:')
        for iv in invalid:
            p(logger, f"   [{iv['sheet']}] 行{iv['row_num']} {iv['asin']}: {iv['reason']}")
    p(logger, f'[飞书] 读取原始表: ' + ' '.join(f'{s}={len(r)}' for s, r in rows_by_sheet.items()))

    # 2.5 按 --asins 过滤（在线专项测试）
    if args.asins:
        asins = {a.strip() for a in args.asins.split(',') if a.strip()}
        for s in list(rows_by_sheet.keys()):
            rows_by_sheet[s] = [r for r in rows_by_sheet[s] if r.asin in asins]
            if not rows_by_sheet[s]:
                del rows_by_sheet[s]
        p(logger, f'[asins] 只测试 {len(asins)} 个 ASIN: ' + ', '.join(sorted(asins)))

    # 2.6 source_data_invalid：生成六列异常记录（防目标表残留旧成功数据，不静默忽略）
    invalid_crawls: dict[str, list[CrawlResult]] = {}
    for iv in invalid:
        cr = CrawlResult(asin=iv['asin'], status=PageStatus.SOURCE_INVALID,
                         error=f"源数据无效: {iv['reason']}")
        cr.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cr.match = '-'
        cr.discount_type = '-'
        invalid_crawls.setdefault(iv['sheet'], []).append(cr)

    # 3. 批次恢复：resume/run-id 才复用旧 run_id，否则新建
    run_id = resolve_run_id(cfg, rows_by_sheet, args, logger)
    p(logger, f'===== 运行批次 {run_id} =====')

    # 4. 保存本地快照
    save_snapshot(run_id, meta, rows_by_sheet)
    p(logger, f'[快照] 已保存 outputs/snapshots/{run_id}/source.json')

    write_to_feishu = not args.dry_run and not args.fetch_only
    target_sheets = {}

    # 5. 基础数据同步到目标表（公式转数值）
    if write_to_feishu:
        target_sheets = fc.list_sheets(target_ss)
        synced = 0
        for sheet, rows in rows_by_sheet.items():
            sid = target_sheets.get(sheet)
            if not sid:
                p(logger, f'  [{sheet}] 目标表无此 sheet，跳过同步')
                continue
            # 每次覆盖前保存目标表 A:V 快照；A:G 使用完整源数据（含无效行）。
            backup = fc.backup_target_sheet(target_ss, sheet, sid, run_id)
            invalid_rows = [iv['report_row'] for iv in invalid
                            if iv.get('sheet') == sheet and iv.get('report_row') is not None]
            base_rows = sorted(rows + invalid_rows, key=lambda r: r.row_num)
            n, appended, removed = fc.sync_base_data(target_ss, sheet, sid, base_rows, cfg)
            synced += n
            p(logger, f'  [{sheet}] A:G 刷新 {appended} 行；H:M 已清空；备份 {backup.name}')
            if removed:
                p(logger, f'  [{sheet}] 提示: 源表已删除 {removed} 个 ASIN（目标表旧行保留未动）')
        p(logger, f'[飞书] 基础数据同步完成，共写入 {synced} 单元格')

    # 6. 抓取 + 计算 + CSV
    results_by_sheet: dict[str, list[CrawlResult]] = {}
    for sheet, rows in rows_by_sheet.items():
        if args.limit:
            rows = rows[:args.limit]
        if not rows:
            continue
        crawls = run_fetch(run_id, sheet, rows, cfg,
                           headless=not args.no_headless,   # 3.2 方向修正
                           force_fetch=args.force_fetch, logger=logger)
        results_by_sheet[sheet] = crawls
        csv_path = export_results(sheet, rows, crawls, run_id)
        p(logger, f'[{sheet}] 完成 {len(crawls)} 行 → {csv_path.name}')

    # 7. 汇总 → 异常比例 + 兜底比例前置判断，达标才写飞书
    error_ratio = summarize(results_by_sheet, cfg, logger)
    should_push = write_to_feishu
    if write_to_feishu and error_ratio > cfg['max_error_ratio_for_push'] and not args.force_push:
        p(logger, f'[推送] 技术异常比例 {error_ratio:.1%} 超过阈值 '
                  f'{cfg["max_error_ratio_for_push"]:.0%}，本次不写入飞书六列（本地 CSV/缓存已保留）。'
                  f'人工确认结果后可用 --force-push 或 --push-only 恢复推送。')
        should_push = False
    # 5.x：目标成交价来源监控 + 缺失比例保护
    # 源表是上传 xlsx 时公式列无缓存值 → 本地兜底是常态路径（已离线验证正确），
    # 只有"本地也算不出来(missing)"才是真正的数据风险，超阈值才阻止推送。
    fb_total = sum(1 for rs in rows_by_sheet.values() for r in rs
                   if getattr(r, 'target_price_source', '') == 'local_fallback')
    miss_total = sum(1 for rs in rows_by_sheet.values() for r in rs
                     if getattr(r, 'target_price_source', '') == 'missing')
    valid_total = sum(len(rs) for rs in rows_by_sheet.values())
    if valid_total and fb_total:
        p(logger, f'[推送] 目标成交价本地兜底 {fb_total}/{valid_total} '
                  f'({fb_total / valid_total:.0%})，缺失 {miss_total} 行'
                  f'（上传 xlsx 公式无缓存值属正常，缺失才是风险）')
    if valid_total and miss_total / valid_total > cfg['max_target_fallback_ratio_for_push'] \
            and write_to_feishu and not args.force_push:
        p(logger, f'[推送] 目标成交价缺失占比 {miss_total / valid_total:.1%} 超过阈值 '
                  f'{cfg["max_target_fallback_ratio_for_push"]:.0%}，停止推送（本地兜底也算不出目标价）。')
        should_push = False

    if should_push:
        if not target_sheets:
            target_sheets = fc.list_sheets(target_ss)
        pushed = 0
        for sheet, crawls in results_by_sheet.items():
            sid = target_sheets.get(sheet)
            if not sid:
                continue
            start_col = 8  # 统一紧凑结构：H:M
            asin_map = fc.build_asin_map(target_ss, sid)
            all_crawls = crawls + invalid_crawls.get(sheet, [])   # 无效行写 '-' 防旧数据残留
            n = fc.write_six_columns(target_ss, sheet, sid, asin_map, all_crawls, cfg,
                                     start_col=start_col)
            pushed += n
            p(logger, f'  [{sheet}] 六列写入 {n} 行（起始列 {col_letter(start_col)}）')
        p(logger, f'[飞书] 六列回写完成，共 {pushed} 行')
    else:
        p(logger, f'[推送] 本次跳过飞书六列写入（dry_run={args.dry_run} fetch_only={args.fetch_only}）')

    elapsed = time.time() - t_start
    # 每日运行留档：日志之外再保存机器可读汇总。
    daily_dir = OUTPUT_DIR / 'daily_runs' / datetime.now().strftime('%Y-%m-%d')
    daily_dir.mkdir(parents=True, exist_ok=True)
    with open(daily_dir / f'{run_id}_summary.json', 'w', encoding='utf-8') as f:
        json.dump({
            'run_id': run_id,
            'finished_at': datetime.now().isoformat(timespec='seconds'),
            'sheets': {s: len(v) for s, v in results_by_sheet.items()},
            'invalid_rows': len(invalid),
            'error_ratio': error_ratio,
            'pushed': bool(should_push),
            'elapsed_seconds': round(elapsed, 1),
        }, f, ensure_ascii=False, indent=1)
    p(logger, f'===== 运行结束（耗时 {elapsed:.0f}s）=====')


def push_only_flow(fc: FeishuClient, cfg: dict, sheets: list[str], logger, args) -> None:
    if args.run_id:
        snapshot_path = OUTPUT_DIR / 'snapshots' / args.run_id / 'source.json'
        if not snapshot_path.exists():
            raise RuntimeError(f'指定快照不存在: {args.run_id}')
        with open(snapshot_path, encoding='utf-8') as f:
            snap = (args.run_id, json.load(f))
    else:
        snap = load_latest_snapshot()
    if not snap:
        raise RuntimeError('没有找到历史快照，请先运行一次完整流程')
    run_id, snapshot = snap
    p(logger, f'[push-only] 使用快照 {run_id}')
    target_ss = fc.resolve_wiki(cfg['feishu_target_wiki'])
    target_sheets = fc.list_sheets(target_ss)

    # push-only 也必须先刷新当前原始数据 A:G，再追加缓存结果 H:M。
    source_obj, source_type = fc.resolve_wiki_obj(cfg['feishu_source_wiki'])
    if source_type == 'file':
        current_rows, _, current_invalid = fc.read_source_file(source_obj, sheets, cfg)
    else:
        current_rows, _, current_invalid = fc.read_source_sheets(source_obj, sheets, cfg)
    for sheet in sheets:
        sid = target_sheets.get(sheet)
        if not sid or sheet not in current_rows:
            continue
        invalid_rows = [iv['report_row'] for iv in current_invalid
                        if iv.get('sheet') == sheet and iv.get('report_row') is not None]
        base_rows = sorted(current_rows[sheet] + invalid_rows, key=lambda r: r.row_num)
        backup = fc.backup_target_sheet(target_ss, sheet, sid, run_id)
        fc.sync_base_data(target_ss, sheet, sid, base_rows, cfg)
        p(logger, f'  [{sheet}] A:G 已刷新 {len(base_rows)} 行；H:M 已清空；备份 {backup.name}')
    pushed = 0
    results_by_sheet: dict[str, list[CrawlResult]] = {}
    for sheet in sheets:
        if sheet not in snapshot.get('sheets', {}):
            continue
        rows = [row_from_dict(d) for d in snapshot['sheets'][sheet]]
        meta = load_sheet_cache(run_id, sheet)
        if not meta:
            p(logger, f'[{sheet}] 无抓取缓存，跳过')
            continue
        crawls = records_to_crawls(meta)
        order = {r.asin: r for r in rows}
        ordered = [next((c for c in crawls if c.asin == a), None) for a in order]
        ordered = [c for c in ordered if c is not None]
        if not ordered:
            continue
        results_by_sheet[sheet] = ordered
        sid = target_sheets.get(sheet)
        if not sid:
            continue
        start_col = 8
        asin_map = fc.build_asin_map(target_ss, sid)
        n = fc.write_six_columns(target_ss, sheet, sid, asin_map, ordered, cfg,
                                 start_col=start_col)
        pushed += n
        p(logger, f'  [{sheet}] 六列写入 {n} 行（起始列 {col_letter(start_col)}）')
    summarize(results_by_sheet, cfg, logger)
    p(logger, f'[push-only] 共写入 {pushed} 行')


def inspect_flow(fc: FeishuClient, cfg: dict, sheets: list[str], logger) -> None:
    p(logger, '===== 飞书布局只读预检（不写任何数据）=====')
    target_ss = fc.resolve_wiki(cfg['feishu_target_wiki'])
    res = fc.inspect_layout(target_ss, sheets, cfg)
    for sheet, info in res.items():
        p(logger, f'--- {sheet} ---')
        p(logger, f'  表头行={info.get("header_row")} | 首个 ASIN: {info.get("first_asin")}')
        p(logger, f'  目标成交价: {info.get("target_price_col")} | 最后业务列: {info.get("last_business_col")}')
        p(logger, f'  旧追加列: {info.get("legacy_cols")} | 已有六列: {info.get("existing_six_cols")}')
        p(logger, f'  建议输出范围: {info.get("suggested_output")} | 覆盖风险: {info.get("overlap_risk")}')
        if info.get('j_o_nonempty'):
            p(logger, f'  J:O 现有非空: {info.get("j_o_nonempty")[:8]}')
        if info.get('error'):
            p(logger, f'  {info["error"]}')
    p(logger, '===== 预检完成：人工确认每个 Sheet 的输出范围后，再执行单 Sheet 迁移 =====')


def migrate_flow(fc: FeishuClient, cfg: dict, sheets: list[str], args, logger) -> None:
    p(logger, '===== 一次性列迁移开始 =====')
    target_ss = fc.resolve_wiki(cfg['feishu_target_wiki'])
    res = fc.migrate_columns(target_ss, cfg, sheets, confirm=args.confirm)
    p(logger, f'迁移结果: {json.dumps(res, ensure_ascii=False)}')
    p(logger, '列迁移完成：旧追加列已清理，六列表头已写入。之后每日任务只覆盖六列。')


# ============================ 入口 ============================
def main():
    args = parse_args()
    cfg = load_config()
    ensure_dirs()
    cleanup_debug_dirs(DEBUG_DIR, keep_days=7)
    logger = setup_logger(cfg)
    sheets = [s.strip() for s in args.sheets.split(',')] if args.sheets else list(cfg['sheets'])

    fc = FeishuClient(cfg)
    try:
        if args.inspect_feishu_layout:
            inspect_flow(fc, cfg, sheets, logger)
        elif args.migrate_feishu_columns:
            migrate_flow(fc, cfg, sheets, args, logger)
        elif args.push_only:
            push_only_flow(fc, cfg, sheets, logger, args)
        else:
            full_flow(fc, cfg, sheets, args, logger)
    finally:
        fc.close()


if __name__ == '__main__':
    main()
