# -*- coding: utf-8 -*-
"""test_layout.py — 六列输出布局解析（P0-2.2）"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from feishu import resolve_sheet_start_col, load_migration_layout, save_migration_layout
from config import DEFAULTS

HEADERS = DEFAULTS['feishu_output_headers']


class TestResolveStartCol(unittest.TestCase):
    def test_reuse_existing_six_cols(self):
        """表头已存在完整六列 → 复用其起始列"""
        header = ['ASIN', 'SKU', '正常售价', '本周折扣形式', '本周折扣%', '目标成交价',
                  '', '', ''] + HEADERS + ['其他']
        start = resolve_sheet_start_col(header, [], HEADERS)
        self.assertEqual(start, 10)     # HEADERS 从第 10 列开始（1-based）

    def test_find_empty_cols_after_business(self):
        """业务列之后找连续空列（PD03 型：业务到 K 列目标成交价）"""
        header = ['ASIN', 'SKU', '正常售价', '本周折扣形式', '本周折扣%', '', '广告策略',
                  '目标成交价', 'BD/LD/日常折扣', 'BD/LD参加数量']
        # 表头 10 列有内容，之后为空 → 从 11 列开始
        start = resolve_sheet_start_col(header, [], HEADERS)
        self.assertEqual(start, 11)

    def test_data_blocks_business_cols(self):
        """空表头但下方有数据 → 不算空列（PD05 型：表头 J 空但数据区可能有值）"""
        header = ['ASIN', 'SKU', '正常售价', '', '', '', '广告策略', '目标成交价', '', '备注']
        sample = [[None] * 9 + ['有数据']]      # 第 10 列有数据
        start = resolve_sheet_start_col(header, sample, HEADERS)
        self.assertEqual(start, 11)            # 跳过第 10 列（有数据），从 11 开始

    def test_different_sheets_different_start(self):
        """不同 Sheet 业务列长度不同 → 不同起始列（PD03 到 K=11，PD05 到 L=12）"""
        h_pd03 = ['ASIN', 'SKU', '正常售价', '本周折扣形式', '本周折扣%', '广告策略',
                  '目标成交价', 'BD/LD/日常折扣']
        h_pd05 = ['ASIN', 'SKU', '正常售价', '本周折扣形式', '本周折扣%', '备注',
                  '广告策略', '目标成交价', 'BD/LD/日常折扣']
        self.assertEqual(resolve_sheet_start_col(h_pd03, [], HEADERS), 9)
        self.assertEqual(resolve_sheet_start_col(h_pd05, [], HEADERS), 10)

    def test_no_space_returns_none(self):
        header = ['x'] * 400
        self.assertIsNone(resolve_sheet_start_col(header, [], HEADERS))


class TestMigrationLayoutRecord(unittest.TestCase):
    def test_roundtrip(self):
        import tempfile
        import config as config_mod
        import feishu as feishu_mod
        from pathlib import Path as P
        with tempfile.TemporaryDirectory() as td:
            orig = config_mod.OUTPUT_DIR
            config_mod.OUTPUT_DIR = P(td)
            # feishu 的 OUTPUT_DIR 引用同一模块对象 → 生效
            try:
                self.assertEqual(load_migration_layout(), {})
                save_migration_layout({'PD03': 35, 'PD05': 36})
                layout = load_migration_layout()
                self.assertEqual(layout.get('PD03'), 35)
                self.assertEqual(layout.get('PD05'), 36)
            finally:
                config_mod.OUTPUT_DIR = orig


if __name__ == '__main__':
    unittest.main()
