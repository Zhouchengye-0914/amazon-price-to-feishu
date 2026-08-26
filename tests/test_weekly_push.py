import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

import cache
import main
from models import CrawlResult, PageStatus, ReportRow


class WeeklyPushCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'outputs'
        self.cache_root = self.output / 'fetch_cache'
        self.run_id = 'run1'
        self.manifest = {
            'period_id': 'week',
            'snapshot': {'spreadsheet_token': 'snapshot'},
            'result': {'spreadsheet_token': 'result'},
        }
        snap = self.output / 'snapshots' / self.run_id / 'source.json'
        snap.parent.mkdir(parents=True)
        snap.write_text(json.dumps({'source_meta': {
            'period_id': 'week', 'snapshot_spreadsheet_token': 'snapshot',
            'result_spreadsheet_token': 'result'}}, ensure_ascii=False), encoding='utf-8')
        self.html = self.root / 'a.html'
        self.html.write_bytes(b'archive')

    def save_cache(self, sha=None):
        import hashlib
        row = ReportRow(2, 'B000000001', marketplace='US')
        cr = CrawlResult(asin=row.asin, run_id=self.run_id, status=PageStatus.OK,
                         display_price=Decimal('10'), marketplace='US',
                         currency_code='USD', archive_status='ok',
                         html_path=str(self.html), html_url=self.html.as_uri(),
                         html_sha256=sha or hashlib.sha256(b'archive').hexdigest(),
                         product_url='https://www.amazon.com/dp/B000000001')
        old = cache.CACHE_ROOT
        cache.CACHE_ROOT = self.cache_root
        self.addCleanup(setattr, cache, 'CACHE_ROOT', old)
        cache.save_sheet_cache(self.run_id, 'PD03', [row], [cr], {
            'parser_rule_version': 'v', 'price_tolerance': '0.5',
            'html_archive_enabled': True, 'html_archive_required': True})

    def test_loads_only_current_manifest_cache_and_checks_hash(self):
        self.save_cache()
        with mock.patch.object(main, 'OUTPUT_DIR', self.output):
            result = main._load_weekly_push_results(
                self.run_id, ['PD03'], self.manifest)
        self.assertEqual(result['PD03'][0].run_id, self.run_id)
        self.assertEqual(result['PD03'][0].html_url, self.html.as_uri())

    def test_hash_mismatch_blocks_only_row_but_snapshot_mismatch_blocks_batch(self):
        self.save_cache(sha='bad')
        with mock.patch.object(main, 'OUTPUT_DIR', self.output):
            result = main._load_weekly_push_results(
                self.run_id, ['PD03'], self.manifest)
            self.assertEqual(result['PD03'][0].archive_status, 'failed')
            self.assertEqual(result['PD03'][0].archive_error, 'html_sha256_mismatch')
            changed = dict(self.manifest)
            changed['snapshot'] = {'spreadsheet_token': 'other'}
            with self.assertRaisesRegex(RuntimeError, '固定快照'):
                main._load_weekly_push_results(self.run_id, ['PD03'], changed)

    def test_feishu_rich_url_equals_plain_url(self):
        url = 'file:///D:/html/a.html'
        self.assertTrue(main._cells_equal(
            [{'type': 'url', 'text': url, 'link': url}], url))
        self.assertFalse(main._cells_equal(
            [{'type': 'url', 'text': 'wrong', 'link': 'file:///wrong'}], url))

    def test_bundle_preserves_source_invalid_in_same_run(self):
        daily = self.output / 'daily_runs' / '2026-08-24'
        daily.mkdir(parents=True)
        bundle = {
            'schema_version': 2, 'run_id': self.run_id, 'period_id': 'week',
            'snapshot_spreadsheet_token': 'snapshot',
            'result_spreadsheet_token': 'result',
            'sheets': {'PD03': [{
                'asin': 'B000000009', 'run_id': self.run_id,
                'status': 'source_data_invalid', 'error': 'missing price',
                'discount_type': '-', 'match': '-', 'currency_code': 'USD',
            }]},
        }
        (daily / f'{self.run_id}_weekly_bundle.json').write_text(
            json.dumps(bundle), encoding='utf-8')
        with mock.patch.object(main, 'OUTPUT_DIR', self.output):
            result = main._load_weekly_push_results(
                self.run_id, ['PD03'], self.manifest)
        self.assertEqual(result['PD03'][0].status, PageStatus.SOURCE_INVALID)
        self.assertEqual(result['PD03'][0].run_id, self.run_id)


if __name__ == '__main__': unittest.main()
