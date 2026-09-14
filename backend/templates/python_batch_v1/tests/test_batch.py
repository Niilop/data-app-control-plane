import unittest
from src.__PACKAGE__.batch import summarize


class BatchTests(unittest.TestCase):
    def test_synthetic_summary(self) -> None:
        self.assertEqual(summarize(5), {"rows": 5, "total": 10})

    def test_bounds(self) -> None:
        for count in (0, 10001):
            with self.assertRaises(ValueError):
                summarize(count)


if __name__ == "__main__":
    unittest.main()
