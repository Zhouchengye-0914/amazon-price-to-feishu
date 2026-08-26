# -*- coding: utf-8 -*-
"""HTML 归档局域网只读服务、状态探测与 URL 生成。"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import secrets
import socket
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR, load_config

STATE_PATH = OUTPUT_DIR / 'html_server.json'


def _lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(('8.8.8.8', 80))
        return sock.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())
    finally:
        sock.close()


def _atomic_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, STATE_PATH)


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def server_status(cfg: dict, timeout: float = 1.5) -> dict:
    state = load_state()
    expected_root = str(Path(cfg['html_archive_root']).resolve())
    result = {**state, 'enabled': bool(cfg.get('html_server_enabled', True)),
              'reachable': False}
    if not result['enabled']:
        result['reason'] = 'disabled'
        return result
    if state.get('root') != expected_root:
        result['reason'] = 'state_root_mismatch_or_missing'
        return result
    health = state.get('health_url') or ''
    try:
        with urllib.request.urlopen(health, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
        result['reachable'] = response.status == 200 and payload.get('status') == 'ok'
        result['reason'] = 'ok' if result['reachable'] else 'bad_health_response'
    except Exception as exc:
        result['reason'] = f'{type(exc).__name__}: {str(exc)[:100]}'
    return result


def archive_http_url(path: str | Path, cfg: dict, status: dict | None = None) -> str:
    root = Path(cfg['html_archive_root']).resolve()
    target = Path(path).resolve()
    relative = target.relative_to(root)
    state = status or server_status(cfg)
    if not state.get('reachable') or not state.get('base_url'):
        raise RuntimeError(f'HTML局域网服务不可用: {state.get("reason", "unknown")}')
    quoted = '/'.join(urllib.parse.quote(part) for part in relative.parts)
    return state['base_url'].rstrip('/') + '/' + quoted


class ArchiveHandler(http.server.SimpleHTTPRequestHandler):
    root = Path('.')
    token = ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.root), **kwargs)

    def _deny(self, message='403 Forbidden'):
        body = message.encode('utf-8')
        self.send_response(403)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, method: str):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        prefix = '/' + self.token
        if path == prefix + '/_health':
            body = json.dumps({'status': 'ok'}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if method == 'GET':
                self.wfile.write(body)
            return
        if path == prefix:
            self.send_response(302)
            self.send_header('Location', prefix + '/')
            self.end_headers()
            return
        if not path.startswith(prefix + '/'):
            return self._deny('403 Forbidden: missing or invalid token')
        relative = path[len(prefix):]
        if any(part.startswith('.') for part in relative.split('/')):
            return self._deny('403 Forbidden: hidden path')
        self.path = urllib.parse.quote(relative, safe='/%')
        return super().do_GET() if method == 'GET' else super().do_HEAD()

    def do_GET(self):
        return self._dispatch('GET')

    def do_HEAD(self):
        return self._dispatch('HEAD')


def serve(cfg: dict) -> None:
    root = Path(cfg['html_archive_root']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    old = load_state()
    token = str(old.get('token') or secrets.token_urlsafe(18))
    port = int(cfg.get('html_server_port', 8765))
    bind = str(cfg.get('html_server_bind', '0.0.0.0'))
    lan_ip = _lan_ip()
    ArchiveHandler.root = root
    ArchiveHandler.token = token
    server = http.server.ThreadingHTTPServer((bind, port), ArchiveHandler)
    base_url = f'http://{lan_ip}:{port}/{token}'
    state = {'status': 'running', 'pid': os.getpid(), 'root': str(root),
             'bind': bind, 'port': port, 'token': token, 'lan_ip': lan_ip,
             'base_url': base_url, 'health_url': base_url + '/_health',
             'started_at': datetime.now().isoformat()}
    _atomic_state(state)
    print(json.dumps({k: v for k, v in state.items() if k != 'token'},
                     ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    cfg = load_config()
    if args.status:
        print(json.dumps(server_status(cfg), ensure_ascii=False, indent=2))
        return
    serve(cfg)


if __name__ == '__main__':
    main()
