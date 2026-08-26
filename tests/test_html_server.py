import tempfile
import unittest
from pathlib import Path
from unittest import mock

import html_server


class HtmlServerTest(unittest.TestCase):
    def test_archive_http_url_requires_reachable_service(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / '2026-08-25' / 'run 1' / 'a.html'
            target.parent.mkdir(parents=True)
            target.write_text('x', encoding='utf-8')
            cfg = {'html_archive_root': str(root)}
            url = html_server.archive_http_url(target, cfg, {
                'reachable': True, 'base_url': 'http://10.0.0.2:8765/tok'})
            self.assertEqual(url, 'http://10.0.0.2:8765/tok/2026-08-25/run%201/a.html')
            with self.assertRaisesRegex(RuntimeError, '不可用'):
                html_server.archive_http_url(target, cfg, {'reachable': False})

    def test_status_rejects_state_for_other_root(self):
        cfg = {'html_archive_root': str(Path('D:/expected').resolve()),
               'html_server_enabled': True}
        with mock.patch.object(html_server, 'load_state', return_value={
                'root': str(Path('D:/other').resolve())}):
            status = html_server.server_status(cfg)
        self.assertFalse(status['reachable'])
        self.assertEqual(status['reason'], 'state_root_mismatch_or_missing')


if __name__ == '__main__':
    unittest.main()
