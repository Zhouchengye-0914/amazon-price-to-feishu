# -*- coding: utf-8 -*-
"""单浏览器多 tab 池测试（不启动真实浏览器）。"""
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amazon.crawler import AmazonBrowser


class TestTabPool(unittest.TestCase):
    def _browser(self):
        b = AmazonBrowser.__new__(AmazonBrowser)
        b.page = mock.MagicMock()
        b._lock = threading.Lock()
        b._free = []
        b._live = set()
        return b

    def test_created_tab_is_not_free_until_release(self):
        b = self._browser()
        tab = mock.MagicMock()
        b.page.new_tab.return_value = tab

        acquired = b.acquire()
        self.assertIs(acquired, tab)
        self.assertEqual(b._free, [])

        b.release(acquired)
        self.assertEqual(b._free, [tab])

    def test_rebuilt_tab_is_not_exposed_to_other_worker(self):
        b = self._browser()
        old = mock.MagicMock()
        new = mock.MagicMock()
        b._live.add(id(old))
        b.page.new_tab.return_value = new

        rebuilt = b.rebuild(old)
        self.assertIs(rebuilt, new)
        self.assertNotIn(old, b._free)
        self.assertNotIn(new, b._free)
        self.assertNotIn(id(old), b._live)
        self.assertIn(id(new), b._live)

        b.release(rebuilt)
        self.assertEqual(b._free, [new])

    def test_two_workers_never_acquire_same_tab(self):
        b = self._browser()
        t1, t2 = mock.MagicMock(), mock.MagicMock()
        b._free = [t1, t2]
        b._live = {id(t1), id(t2)}

        a = b.acquire()
        c = b.acquire()
        self.assertIsNot(a, c)
        self.assertEqual(b._free, [])


if __name__ == '__main__':
    unittest.main()
