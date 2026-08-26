# -*- coding: utf-8 -*-
"""CSV 币种字段与折扣单位测试。"""
import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from exporters import export_results
from models import CrawlResult, ReportRow


class TestCurrencyCsv(unittest.TestCase):
    def test_amount_uses_market_currency_and_percent_stays_percent(self):
        rows = [
            ReportRow(2, 'B0AAA11111', marketplace='US'),
            ReportRow(3, 'B0BBB22222', marketplace='CA'),
        ]
        results = [
            CrawlResult('B0AAA11111', discount_value='25%', marketplace='US',
                        currency_code='USD', product_url='https://www.amazon.com/dp/B0AAA11111'),
            CrawlResult('B0BBB22222', discount_value='-10.00', marketplace='CA',
                        currency_code='CAD', product_url='https://www.amazon.ca/dp/B0BBB22222'),
        ]
        with tempfile.TemporaryDirectory() as td, \
                mock.patch('exporters.CSV_DIR', Path(td)):
            path = export_results('TEST', rows, results, 'run1')
            with path.open(encoding='utf-8-sig', newline='') as f:
                records = list(csv.DictReader(f))
        self.assertEqual(records[0]['discount_unit'], '%')
        self.assertEqual(records[1]['discount_unit'], 'CAD')
        self.assertEqual(records[1]['currency_code'], 'CAD')
        self.assertEqual(records[1]['product_url'],
                         'https://www.amazon.ca/dp/B0BBB22222')


if __name__ == '__main__':
    unittest.main()
