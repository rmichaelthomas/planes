import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmarks" / "published"))
import gen_jobs


class InvoiceFixtureTests(unittest.TestCase):
    def test_browser_fixture_matches_the_h7_generator(self):
        fixture = REPO / "rust" / "planes-spike" / "data" / "h7_invoice.csv"
        expected = "".join(f"{quantity},{cents}\n" for quantity, cents in gen_jobs.invoice_lines())
        self.assertEqual(fixture.read_text(encoding="utf-8"), expected)


if __name__ == "__main__":
    unittest.main()
