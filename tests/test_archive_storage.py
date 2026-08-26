# -*- coding: utf-8 -*-
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from archive_storage import ArchiveStorage, safe_fragment


class TestArchiveStorage(unittest.TestCase):
    def test_path_naming_and_traversal_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArchiveStorage(Path(td), min_free_gb=0)
            path = store.html_path(date(2026, 8, 24), 'run/01', 1, 'PD 03', 2,
                                   '../B0ABCDEF12')
            self.assertEqual(path.name, '00002_B0ABCDEF12.html')
            self.assertEqual(path.parent.name, '001_PD_03')
            self.assertIn('run_01', path.parts)
            store.assert_inside(path)
            with self.assertRaises(RuntimeError):
                store.assert_inside(Path(td).parent / 'outside.html')

    def test_six_days_two_runs_only_removes_expired_day(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = ArchiveStorage(root, retention_days=5, min_free_gb=0)
            today = date(2026, 8, 24)
            for ago in range(6):
                for run in ('run_am', 'run_pm'):
                    folder = root / (today - timedelta(days=ago)).isoformat() / run
                    folder.mkdir(parents=True)
                    (folder / 'x.html').write_text('x')
            (root / 'notes').mkdir()
            removed = store.cleanup_expired(today)
            self.assertEqual(len(removed), 1)
            self.assertFalse((root / '2026-08-19').exists())
            self.assertTrue((root / '2026-08-20').exists())
            self.assertTrue((root / 'notes').exists())

    def test_capacity_failure(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArchiveStorage(td, min_free_gb=40)
            usage = mock.Mock(free=10 * 1024 ** 3)
            with mock.patch('archive_storage.shutil.disk_usage', return_value=usage):
                with self.assertRaisesRegex(RuntimeError, '空间不足'):
                    store.check_capacity()

    def test_manifest_atomic_failure_removes_tmp(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArchiveStorage(td, min_free_gb=0)
            with mock.patch('archive_storage.os.replace', side_effect=OSError('fail')):
                with self.assertRaises(OSError):
                    store.write_manifest(date(2026, 8, 24), 'run_01', {'run_id': 'run_01'})
            self.assertFalse((Path(td) / '2026-08-24' / 'run_01' / 'manifest.json.tmp').exists())

    def test_empty_fragment_rejected(self):
        with self.assertRaises(ValueError):
            safe_fragment('..', 'asin')

    def test_linklike_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArchiveStorage(td, min_free_gb=0)
            with mock.patch('archive_storage._is_linklike', return_value=True):
                with self.assertRaisesRegex(RuntimeError, '符号链接或目录联接'):
                    store.ensure_root()

    def test_file_url_encodes_unicode_spaces_and_special_chars(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArchiveStorage(td, min_free_gb=0)
            path = Path(td) / '2026-08-24' / 'run 01' / '001_中文' / '00001_B0#TEST.html'
            path.parent.mkdir(parents=True)
            path.write_text('<html></html>', encoding='utf-8')
            url = store.file_url(path)
            self.assertTrue(url.startswith('file:///'))
            self.assertIn('%20', url)
            self.assertIn('%23', url)
            self.assertIn('%E4%B8%AD%E6%96%87', url)

    def test_http_url_uses_lan_base_and_relative_archive_path(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArchiveStorage(td, http_base_url='http://192.168.1.8:8765/token')
            path = Path(td) / '2026-08-25' / 'run 1' / 'a.html'
            path.parent.mkdir(parents=True)
            path.write_text('<html></html>', encoding='utf-8')
            self.assertEqual(
                store.file_url(path),
                'http://192.168.1.8:8765/token/2026-08-25/run%201/a.html')

    def test_file_url_rejects_missing_non_html_and_outside(self):
        with tempfile.TemporaryDirectory() as td:
            store = ArchiveStorage(td, min_free_gb=0)
            with self.assertRaisesRegex(RuntimeError, '不存在'):
                store.file_url(Path(td) / 'missing.html')
            txt = Path(td) / 'x.txt'
            txt.write_text('x')
            with self.assertRaisesRegex(RuntimeError, '只允许'):
                store.file_url(txt)
            with self.assertRaisesRegex(RuntimeError, '越界'):
                store.file_url(Path(td).parent / 'outside.html')


if __name__ == '__main__':
    unittest.main()
