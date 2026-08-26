# -*- coding: utf-8 -*-
"""同一 Chromium tab 的 SingleFile 自包含 HTML 捕获与落盘校验。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ArchiveResult:
    path: str
    sha256: str
    size_bytes: int
    duration_ms: int
    asin: str
    source_html_sha256: str
    page_status: str = ''
    external_resource_refs: int = 0
    validation: str = 'ok'
    stripped_noncore_css_resources: int = 0


class SingleFileArchiver:
    """把官方 SingleFile 脚本注入已加载商品 tab，不重复导航。"""

    def __init__(self, project_root: Path, work_dir: Path):
        self.project_root = project_root.resolve()
        self.work_dir = work_dir.resolve()
        self.script_dir = self.work_dir / 'scripts'
        self.download_dir = self.work_dir / 'downloads'
        self._scripts: dict[str, str] | None = None
        self._prepared_tabs: set[int] = set()

    def prepare_scripts(self) -> dict[str, str]:
        if self._scripts:
            return self._scripts
        helper = self.project_root / 'tools' / 'singlefile' / 'export-scripts.mjs'
        package_dir = helper.parent
        if not (package_dir / 'node_modules' / 'single-file-cli').exists():
            raise RuntimeError('SingleFile 运行依赖未安装：请在 tools/singlefile 执行 npm install')
        cp = subprocess.run(['node', str(helper), str(self.script_dir)], cwd=str(package_dir),
                            check=True, capture_output=True, text=True, timeout=30)
        paths = json.loads(cp.stdout)
        self._scripts = {key: Path(value).read_text(encoding='utf-8')
                         for key, value in paths.items()}
        return self._scripts

    def prepare_tab(self, tab) -> None:
        """商品导航前安装 hook；调用本身不会导航。"""
        key = id(tab)
        if key in self._prepared_tabs:
            return
        tab.run_cdp('Page.addScriptToEvaluateOnNewDocument',
                    source=self.prepare_scripts()['hook'])
        self._prepared_tabs.add(key)

    def capture(self, tab, asin: str, destination: Path, timeout: float = 120,
                page_status: str = 'ok') -> ArchiveResult:
        """在当前文档内封装并触发 Blob 下载，只回传小状态对象。"""
        started = time.monotonic()
        scripts = self.prepare_scripts()
        source_html = tab.html or ''
        source_hash = hashlib.sha256(source_html.encode('utf-8')).hexdigest()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        filename = f'{asin}.singlefile.tmp.html'
        pending = self.download_dir / filename
        pending.unlink(missing_ok=True)
        tab.set.download_path(self.download_dir)

        tab.run_cdp('Runtime.evaluate', expression=scripts['main'], awaitPromise=True,
                    returnByValue=False, _timeout=30)
        options = {
            'blockScripts': True, 'compressHTML': False,
            'blockVideos': True, 'blockAudios': True,
            'removeVideoSrc': True, 'removeAudioSrc': True,
            'removeHiddenElements': False, 'removeUnusedStyles': False,
            'removeUnusedFonts': False, 'removeFrames': False,
            'saveRawPage': False, 'zipScript': scripts['zip'],
        }
        expression = f"""
            (async () => {{
              document.querySelectorAll('[poster]').forEach(node => node.removeAttribute('poster'));
              const data = await window.singlefile.getPageData({json.dumps(options)});
              const blob = new Blob([data.content], {{type: 'text/html;charset=utf-8'}});
              const a = document.createElement('a');
              a.href = URL.createObjectURL(blob);
              a.download = {json.dumps(filename)};
              document.documentElement.appendChild(a);
              a.click();
              a.remove();
              setTimeout(() => URL.revokeObjectURL(a.href), 30000);
              return {{ok: true, bytes: blob.size}};
            }})()
        """
        result = tab.run_cdp('Runtime.evaluate', expression=expression, awaitPromise=True,
                             returnByValue=True, _timeout=timeout)
        small = result.get('result', {}).get('value') or {}
        if not small.get('ok'):
            raise RuntimeError(f'SingleFile 页面处理失败: {result}')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            partial = list(self.download_dir.glob(filename + '*.crdownload'))
            if pending.exists() and not partial:
                break
            time.sleep(0.25)
        if not pending.exists():
            raise RuntimeError('SingleFile 未生成下载文件')
        data = pending.read_bytes()
        data, stripped = self._strip_allowlisted_noncore_css(data)
        min_bytes = 10_000 if page_status == 'page_not_found' else 100_000
        external_refs = self._validate(data, asin, min_bytes=min_bytes)
        tmp = destination.with_suffix(destination.suffix + '.tmp')
        tmp.write_bytes(data)
        os.replace(tmp, destination)
        # Chromium/杀毒软件在 Windows 上可能短暂持有下载文件；目标已完成原子落盘时，
        # 临时下载清理不能把有效归档误判为失败，统一在浏览器退出后重试。
        try:
            pending.unlink(missing_ok=True)
        except PermissionError:
            pass
        return ArchiveResult(path=str(destination), sha256=hashlib.sha256(data).hexdigest(),
                             size_bytes=len(data),
                             duration_ms=int((time.monotonic() - started) * 1000),
                             asin=asin, source_html_sha256=source_hash,
                             page_status=page_status, external_resource_refs=external_refs,
                             stripped_noncore_css_resources=stripped)

    @staticmethod
    def _strip_allowlisted_noncore_css(data: bytes) -> tuple[bytes, int]:
        """只移除无法内嵌的 Amazon 字体和广告角标；未知外链仍由校验器阻断。"""
        text = data.decode('utf-8', errors='ignore')
        pattern = re.compile(
            r'url\(\s*(["\']?)(https?://[^)"\']+'
            r'(?:AmazonUIFont[^)"\']*\.woff2|AmazonEmberModernDisplay[^)"\']*\.woff2|'
            r'da/adchoices/ac-topright-sprite\.png))\1\s*\)',
            flags=re.IGNORECASE,
        )
        cleaned, count = pattern.subn('url("")', text)
        return cleaned.encode('utf-8'), count

    @staticmethod
    def external_resource_matches(data: bytes) -> list[str]:
        text = data.decode('utf-8', errors='ignore')
        patterns = (
            r'(?:<|\s)(?:src|poster)\s*=\s*["\']\s*https?://[^"\']+',
            r'(?:<|\s)srcset\s*=\s*["\'][^"\']*https?://[^"\']+',
            r'<link\b[^>]*\brel\s*=\s*["\'][^"\']*stylesheet[^>]*\bhref\s*=\s*["\']\s*https?://[^"\']+',
            r'url\(\s*["\']?https?://[^)]+',
        )
        return [match.group(0)[:500] for pattern in patterns
                for match in re.finditer(pattern, text, flags=re.IGNORECASE)]

    @staticmethod
    def _validate(data: bytes, asin: str, min_bytes: int = 100_000) -> int:
        if len(data) < min_bytes:
            raise RuntimeError(f'自包含 HTML 体积异常: {len(data)} bytes')
        head = data[:4096].lower()
        if b'<html' not in head and b'<!doctype html' not in head:
            raise RuntimeError('归档缺少 HTML 文档结构')
        if asin.encode('ascii') not in data:
            raise RuntimeError('归档中未找到目标 ASIN')
        # 普通页面超链接可以保留；会被浏览器自动请求的资源属性/CSS URL 必须内嵌。
        count = len(SingleFileArchiver.external_resource_matches(data))
        if count:
            raise RuntimeError(f'归档仍包含 {count} 个外部资源引用')
        return count

    def cleanup_downloads(self, attempts: int = 5) -> int:
        """浏览器退出后清理本工具自己的临时下载，不触及归档目录。"""
        try:
            self.download_dir.resolve().relative_to(self.work_dir)
        except ValueError as exc:
            raise RuntimeError('临时下载目录越界，拒绝清理') from exc
        removed = 0
        for attempt in range(attempts):
            remaining = list(self.download_dir.glob('*.singlefile.tmp.html'))
            if not remaining:
                break
            for path in remaining:
                try:
                    path.unlink()
                    removed += 1
                except PermissionError:
                    pass
            if list(self.download_dir.glob('*.singlefile.tmp.html')) and attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
        return removed


def write_manifest(result: ArchiveResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)
