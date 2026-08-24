# -*- coding: utf-8 -*-
"""config.py — 配置加载与校验（默认值 → config.json → 环境变量）"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUT_DIR = PROJECT_ROOT / 'outputs'
CACHE_ROOT = OUTPUT_DIR / 'fetch_cache'
SNAPSHOT_DIR = OUTPUT_DIR / 'snapshots'
CSV_DIR = OUTPUT_DIR / 'csv'
LOG_DIR = OUTPUT_DIR / 'logs'
DEBUG_DIR = OUTPUT_DIR / 'debug'

# 默认配置（代码兜底）
DEFAULTS = {
    # 抓取
    'workers': 2,                     # 固定 worker，初始 2，稳定后调 4
    'delay_min': 1.0,
    'delay_max': 4.0,
    'page_timeout': 30,               # 整个页面加载超时(秒)
    'price_wait_timeout': 12,         # 等待价格元素出现(秒)
    'per_asin_timeout': 90,           # 单个 ASIN 总超时(秒)
    'retry': 2,                       # 技术失败重试次数
    'save_every': 10,                 # 每 N 条原子保存一次缓存
    'us_zip': '90210',
    'proxy': '',                      # 显式浏览器代理；留空使用固定 VPN，不自动读取系统代理
    # 计算
    'price_tolerance': '0.50',        # 一致性容差(USD, Decimal 字符串)
    'ambiguous_price_ratio': '0.05',  # 多候选冲突阈值
    # 缓存
    'cache_max_age_hours': 12,        # 缓存有效期
    'parser_rule_version': '2026-08-21-v1',
    # 飞书
    'feishu_source_wiki': 'https://wit0jhu6kvu.feishu.cn/wiki/O1t1wJVlHiEbd1kLdj6cIr0KnIg',
    'feishu_target_wiki': 'https://wit0jhu6kvu.feishu.cn/wiki/JbiQwDZXeiJan0k8ydRczfWNnFc',
    'feishu_app_id': 'cli_aa097133e3355ccd',
    'feishu_app_secret': '',          # 环境变量 FS_APP_SECRET 或 config.json
    'feishu_output_start_col': 8,     # 紧凑目标表 H 列(1-based)
    'feishu_header_row': 2,           # 目标表表头固定第 2 行
    'feishu_output_headers': [
        '展示价格', '折扣类型', '折扣值', '最终价格', '一致性检查', '时间戳',
    ],
    # 目标子表（默认美国站 11 表）
    'sheets': ['PD03', 'PD17', 'PD05', 'PD25', 'XD03', 'XD17', 'PD52', 'PD39', 'PD33',
               'PDF075', 'PD63'],
    # 原始周报表列位置(1-based)
    'source_cols': {
        'asin': 1, 'sku': 2, 'size': 4, 'normal_price': 5,
        'h_type': 8, 'i_value': 9, 'target_price': 11,
    },
    # 汇总与告警
    'max_error_ratio_for_push': 0.10, # 技术异常占比超阈值不推送
    'max_target_fallback_ratio_for_push': 0.10,  # 目标价缺失(missing)占比超阈值不推送；上传 xlsx 本地兜底属常态不阻止
    'log_keep': 30,
    # 六列输出布局（P0-2.2）：日常优先读 outputs/migration_record.json，这里仅兜底
    'feishu_output_layout': {
        'default_start_col': None,
        'sheet_start_cols': {},
    },
}

# 数值字段类型检查
_NUM_FIELDS = {
    'workers': (int, 1, 16),
    'delay_min': (float, 0, 60),
    'delay_max': (float, 0, 120),
    'page_timeout': (float, 5, 180),
    'price_wait_timeout': (float, 1, 60),
    'per_asin_timeout': (float, 10, 600),
    'retry': (int, 0, 5),
    'save_every': (int, 1, 1000),
    'price_tolerance': (str, '0', '10'),
    'ambiguous_price_ratio': (str, '0', '1'),
    'cache_max_age_hours': (float, 0.5, 720),
    'max_error_ratio_for_push': (float, 0, 1),
    'max_target_fallback_ratio_for_push': (float, 0, 1),
    'log_keep': (int, 1, 365),
}


def load_config(config_path: Path | None = None) -> dict:
    """默认值 → config.json 覆盖 → 环境变量覆盖 Secret。启动即校验，错误直接抛。"""
    cfg = dict(DEFAULTS)
    path = Path(config_path) if config_path else PROJECT_ROOT / 'config' / 'config.json'
    if path.exists():
        try:
            with open(path, encoding='utf-8') as f:
                user = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise RuntimeError(f'config.json 解析失败: {e}')
        if not isinstance(user, dict):
            raise RuntimeError('config.json 必须是 JSON 对象')
        cfg.update({k: v for k, v in user.items() if v is not None})

    # 环境变量覆盖 Secret
    env_secret = os.environ.get('FS_APP_SECRET', '').strip()
    if env_secret:
        cfg['feishu_app_secret'] = env_secret
    elif not cfg.get('feishu_app_secret'):
        envf = BASE_DIR / '.env'
        if envf.exists():
            try:
                for line in envf.read_text(encoding='utf-8').splitlines():
                    if line.startswith('FS_APP_SECRET='):
                        cfg['feishu_app_secret'] = line.split('=', 1)[1].strip()
                        break
            except OSError:
                pass

    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    """校验数值类型与范围，错误时启动阶段报错。"""
    for key, (typ, lo, hi) in _NUM_FIELDS.items():
        v = cfg.get(key)
        if v is None or v == '':
            raise RuntimeError(f'配置项 {key} 不能为空')
        try:
            if typ is int:
                n = int(v)
            else:
                n = float(v)
        except (ValueError, TypeError):
            raise RuntimeError(f'配置项 {key} 必须是数字，当前值: {v!r}')
        if typ is int:
            if not (int(lo) <= n <= int(hi)):
                raise RuntimeError(f'配置项 {key} 超出范围 [{lo}, {hi}]，当前值: {n}')
        else:
            lo_f, hi_f = float(lo), float(hi)
            if not (lo_f <= n <= hi_f):
                raise RuntimeError(f'配置项 {key} 超出范围 [{lo}, {hi}]，当前值: {n}')

    # Decimal 字符串必须可解析
    from decimal import Decimal, InvalidOperation
    for key in ('price_tolerance', 'ambiguous_price_ratio'):
        try:
            Decimal(str(cfg[key]))
        except InvalidOperation:
            raise RuntimeError(f'配置项 {key} 不是合法的小数: {cfg[key]!r}')

    if cfg['delay_max'] < cfg['delay_min']:
        raise RuntimeError('delay_max 不能小于 delay_min')
    if cfg['per_asin_timeout'] < cfg['page_timeout']:
        raise RuntimeError('per_asin_timeout 不能小于 page_timeout')
    if not cfg['feishu_app_id']:
        raise RuntimeError('feishu_app_id 不能为空')
    if cfg['feishu_output_start_col'] < 1:
        raise RuntimeError('feishu_output_start_col 必须 >= 1')
    if len(cfg['feishu_output_headers']) != 6:
        raise RuntimeError('feishu_output_headers 必须正好 6 列')


def ensure_dirs() -> None:
    for d in (OUTPUT_DIR, CACHE_ROOT, SNAPSHOT_DIR, CSV_DIR, LOG_DIR, DEBUG_DIR):
        d.mkdir(parents=True, exist_ok=True)
