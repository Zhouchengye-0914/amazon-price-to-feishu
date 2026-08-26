import unittest

from archive_stats import percentile


class TestNearestRank(unittest.TestCase):
    def test_small_sample_percentiles(self):
        values = [405, 7780, 8672, 9047]
        self.assertEqual(percentile(values, .50), 7780)
        self.assertEqual(percentile(values, .95), 9047)


if __name__ == '__main__':
    unittest.main()
