import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import gen_jobs
from set_a_rust_bench import require_agreement, write_invoice_data


class RustBenchmarkTests(unittest.TestCase):
    def test_invoice_data_comes_from_the_existing_deterministic_h7_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "invoice.csv"
            write_invoice_data(destination)
            expected = "".join(f"{quantity},{cents}\n" for quantity, cents in gen_jobs.invoice_lines())
            self.assertEqual(destination.read_text(encoding="utf-8"), expected)

    def test_every_runtime_must_agree_before_a_benchmark_can_proceed(self):
        require_agreement({"Rust": "due 2854966.72", "Python": "due 2854966.72", "JavaScript": "due 2854966.72"})

    def test_a_runtime_divergence_blocks_benchmarking(self):
        with self.assertRaisesRegex(RuntimeError, "results differ"):
            require_agreement({"Rust": "due 2854966.73", "Python": "due 2854966.72", "JavaScript": "due 2854966.72"})


if __name__ == "__main__":
    unittest.main()
