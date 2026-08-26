# -*- coding: utf-8 -*-
import unittest
import tempfile
from pathlib import Path
from unittest import mock

from html_archive import SingleFileArchiver


class TestArchiveValidation(unittest.TestCase):
    def test_prepare_tab_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archiver = SingleFileArchiver(root, root / 'work')
            tab = mock.MagicMock()
            with mock.patch.object(archiver, 'prepare_scripts',
                                   return_value={'hook': 'hook'}):
                archiver.prepare_tab(tab)
                archiver.prepare_tab(tab)
            tab.run_cdp.assert_called_once_with(
                'Page.addScriptToEvaluateOnNewDocument', source='hook')

    def test_accepts_embedded_resources_and_normal_links(self):
        data = (b'<!doctype html><html><body>B0ABCDEF12'
                b'<img src="data:image/png;base64,AA==">'
                b'<img src="data:image/gif;base64,AA==" data-src="https://lazy.example/a.jpg">'
                b'<a href="https://www.amazon.com/dp/B0ABCDEF12">link</a>'
                b'</body></html>' + b' ' * 100000)
        self.assertEqual(SingleFileArchiver._validate(data, 'B0ABCDEF12'), 0)

    def test_rejects_external_resource_but_not_href(self):
        data = (b'<!doctype html><html><body>B0ABCDEF12'
                b'<img src="https://images.example/a.jpg">'
                b'</body></html>' + b' ' * 100000)
        with self.assertRaisesRegex(RuntimeError, '外部资源引用'):
            SingleFileArchiver._validate(data, 'B0ABCDEF12')

        poster = (b'<!doctype html><html><body>B0ABCDEF12'
                  b'<video poster="https://images.example/poster.jpg"></video>'
                  b'</body></html>' + b' ' * 100000)
        with self.assertRaisesRegex(RuntimeError, '外部资源引用'):
            SingleFileArchiver._validate(poster, 'B0ABCDEF12')

    def test_page_not_found_can_use_status_specific_minimum(self):
        data = (b'<!doctype html><html><body>B0ZZZZZZZZ not found</body></html>'
                + b' ' * 20000)
        self.assertEqual(SingleFileArchiver._validate(
            data, 'B0ZZZZZZZZ', min_bytes=10_000), 0)
        with self.assertRaisesRegex(RuntimeError, '体积异常'):
            SingleFileArchiver._validate(data, 'B0ZZZZZZZZ')

    def test_external_match_reports_active_attribute(self):
        data = b'<html><img src="https://example.com/a.jpg"></html>'
        matches = SingleFileArchiver.external_resource_matches(data)
        self.assertEqual(len(matches), 1)
        self.assertIn('src=', matches[0])

    def test_only_allowlisted_font_and_ad_sprite_are_stripped(self):
        data = (b'<style>a{src:url(https://m.media-amazon.com/AmazonUIFont-x.woff2)}'
                b'b{background:url("https://images-na.ssl-images-amazon.com/images/G/01/da/adchoices/ac-topright-sprite.png")}'
                b'c{background:url(https://example.com/core.jpg)}</style>')
        cleaned, count = SingleFileArchiver._strip_allowlisted_noncore_css(data)
        self.assertEqual(count, 2)
        self.assertIn(b'https://example.com/core.jpg', cleaned)
        self.assertNotIn(b'AmazonUIFont', cleaned)


if __name__ == '__main__':
    unittest.main()
