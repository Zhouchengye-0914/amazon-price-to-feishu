# -*- coding: utf-8 -*-
"""HTML 归档目录规划、容量保护、manifest 与五日清理。"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

_SAFE_FRAGMENT = re.compile(r'[^A-Za-z0-9_-]+')
_DATE_DIR = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _is_linklike(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(os.path, 'isjunction', lambda _: False)(path))


def safe_fragment(value: str, field: str) -> str:
    value = _SAFE_FRAGMENT.sub('_', str(value).strip()).strip('_')
    if not value or value in ('.', '..'):
        raise ValueError(f'{field} 无法生成安全路径片段')
    return value


class ArchiveStorage:
    def __init__(self, root: str | Path, retention_days: int = 5,
                 min_free_gb: float = 40.0, http_base_url: str = ''):
        raw = Path(root).expanduser()
        if not raw.is_absolute():
            raise ValueError('html_archive_root 必须是绝对路径')
        self.root = raw.absolute()
        self.retention_days = int(retention_days)
        self.min_free_gb = float(min_free_gb)
        self.http_base_url = str(http_base_url or '').rstrip('/')

    def ensure_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        if _is_linklike(self.root):
            raise RuntimeError('html_archive_root 不能是符号链接或目录联接')
        return self.root

    def assert_inside(self, path: str | Path) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise RuntimeError(f'路径越界: {resolved}') from exc
        return resolved

    def check_capacity(self) -> dict:
        root = self.ensure_root()
        usage = shutil.disk_usage(root)
        free_gb = usage.free / (1024 ** 3)
        result = {'root': str(root), 'free_bytes': usage.free,
                  'free_gb': round(free_gb, 3), 'minimum_gb': self.min_free_gb,
                  'ok': free_gb >= self.min_free_gb}
        if not result['ok']:
            raise RuntimeError(f'HTML归档磁盘空间不足: {free_gb:.2f}GB < {self.min_free_gb:.2f}GB')
        return result

    def run_dir(self, run_date: date, run_id: str) -> Path:
        safe_run = safe_fragment(run_id, 'run_id')
        return self.assert_inside(self.root / run_date.isoformat() / safe_run)

    def html_path(self, run_date: date, run_id: str, sheet_order: int,
                  sheet: str, item_order: int, asin: str) -> Path:
        if sheet_order < 1 or item_order < 1:
            raise ValueError('Sheet和HTML顺序必须从1开始')
        safe_sheet = safe_fragment(sheet, 'sheet')
        safe_asin = safe_fragment(asin, 'asin')
        path = (self.run_dir(run_date, run_id)
                / f'{sheet_order:03d}_{safe_sheet}'
                / f'{item_order:05d}_{safe_asin}.html')
        return self.assert_inside(path)

    def write_manifest(self, run_date: date, run_id: str, manifest: dict) -> Path:
        run_dir = self.run_dir(run_date, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = self.assert_inside(run_dir / 'manifest.json')
        tmp = self.assert_inside(run_dir / 'manifest.json.tmp')
        try:
            tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(tmp, path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return path

    def file_url(self, html_path: str | Path) -> str:
        """只为根目录内已落盘的 HTML 生成本机 file:/// URL。"""
        path = self.assert_inside(html_path)
        if not path.is_file():
            raise RuntimeError(f'HTML归档不存在: {path}')
        if path.suffix.lower() != '.html':
            raise RuntimeError(f'只允许生成 HTML 文件URL: {path}')
        if self.http_base_url:
            from urllib.parse import quote
            relative = path.relative_to(self.root)
            return self.http_base_url + '/' + '/'.join(quote(part) for part in relative.parts)
        return path.as_uri()

    def cleanup_expired(self, today: date | None = None) -> list[dict]:
        """只清理根目录直属、可解析且早于五日窗口的日期目录。"""
        root = self.ensure_root()
        current = today or datetime.now().date()
        oldest_kept = current - timedelta(days=self.retention_days - 1)
        removed = []
        for child in root.iterdir():
            if not child.is_dir() or not _DATE_DIR.fullmatch(child.name):
                continue
            try:
                folder_date = date.fromisoformat(child.name)
            except ValueError:
                continue
            if folder_date >= oldest_kept:
                continue
            if _is_linklike(child):
                raise RuntimeError(f'拒绝清理符号链接日期目录: {child}')
            target = self.assert_inside(child)
            size = sum(p.stat().st_size for p in target.rglob('*') if p.is_file())
            shutil.rmtree(target)
            removed.append({'path': str(target), 'date': folder_date.isoformat(),
                            'bytes': size})
        return removed
