import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from mhtml_compare import capture_mhtml


class FakeTab:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def run_cdp(self, method, **kwargs):
        self.calls.append((method, kwargs))
        return {'data': self.data}


class MhtmlCaptureTest(unittest.TestCase):
    def valid_data(self, asin='B000000001'):
        return ('MIME-Version: 1.0\r\nContent-Type: multipart/related; boundary=x\r\n\r\n'
                + asin + '\r\n' + ('x' * 11_000))

    def test_capture_is_atomic_and_does_not_navigate(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / 'sample.mhtml'
            tab = FakeTab(self.valid_data())
            result = capture_mhtml(tab, 'B000000001', destination)
            self.assertTrue(destination.is_file())
            self.assertGreater(result.size_bytes, 10_000)
            self.assertEqual([call[0] for call in tab.calls], ['Page.captureSnapshot'])
            self.assertFalse(destination.with_suffix('.mhtml.tmp').exists())

    def test_rejects_missing_identity_without_partial_file(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / 'sample.mhtml'
            with self.assertRaisesRegex(RuntimeError, 'ASIN'):
                capture_mhtml(FakeTab(self.valid_data('B000000002')),
                              'B000000001', destination)
            self.assertFalse(destination.exists())

    def test_rejects_non_mhtml(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / 'sample.mhtml'
            with self.assertRaisesRegex(RuntimeError, 'MIME'):
                capture_mhtml(FakeTab('B000000001' + 'x' * 11_000),
                              'B000000001', destination)


if __name__ == '__main__':
    unittest.main()
