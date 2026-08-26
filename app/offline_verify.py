# -*- coding: utf-8 -*-
"""在 Chromium 离线模式中打开归档 HTML，并输出机器可读验收报告。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from DrissionPage import ChromiumOptions, ChromiumPage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('html', type=Path)
    ap.add_argument('--asin', required=True)
    ap.add_argument('--price', default='')
    ap.add_argument('--status', default='ok', choices=('ok', 'sold_out', 'page_not_found'))
    args = ap.parse_args()
    path = args.html.resolve()
    if not path.is_file():
        raise SystemExit(f'文件不存在: {path}')
    co = ChromiumOptions().headless(True)
    page = ChromiumPage(co)
    try:
        page.run_cdp('Network.enable')
        page.run_cdp('Network.emulateNetworkConditions', offline=True, latency=0,
                     downloadThroughput=0, uploadThroughput=0)
        page.get(path.as_uri())
        page.wait.doc_loaded(timeout=30)
        title = page.title or ''
        body = page.ele('tag:body').text if page.ele('tag:body') else ''
        resources = page.run_js(
            "return performance.getEntriesByType('resource').map(x => x.name)") or []
        network_resources = [u for u in resources if str(u).startswith(('http://', 'https://'))]
        image_count = int(page.run_js(
            "return [...document.images].filter(x => x.complete && x.naturalWidth > 0).length") or 0)
        report = {
            'path': str(path), 'offline': True, 'title': title,
            'asin_visible': args.asin in (body + title),
            'asin_present_in_archive': args.asin.encode('ascii') in path.read_bytes(),
            'price_visible': not args.price or args.price in body,
            'loaded_image_count': image_count,
            'network_resource_count': len(network_resources),
            'network_resources': network_resources[:20],
        }
        visual_ok = image_count > 0 if args.status == 'ok' else True
        identity_ok = report['asin_visible']
        if args.status == 'page_not_found':
            identity_ok = (report['asin_present_in_archive']
                           and 'not found' in title.lower())
        report['page_status'] = args.status
        report['passed'] = (identity_ok and report['price_visible']
                            and visual_ok and not network_resources)
        out = path.with_suffix('.offline.json')
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report['passed']:
            raise SystemExit(1)
    finally:
        page.quit()


if __name__ == '__main__':
    main()
