import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark_console", ROOT / "benchmarks/validate_console.py")
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)
CORPUS = json.loads((ROOT / "benchmarks/calibration-corpus.json").read_text())


def smoke_records():
    # Independent schema fixture: intentionally unrelated to instruction counts.
    return [{"case_id": case, "region": "kernel", "hart": hart,
             "start_cycle": 100, "end_cycle": 200, "instret_delta": 32,
             "checksum": next(c for c in CORPUS['cases'] if c['case_id']==case)['expected_checksums_by_hart'][hart],
             "expected_checksum": next(c for c in CORPUS['cases'] if c['case_id']==case)['expected_checksums_by_hart'][hart], "pass": True}
            for case in ("baseline.empty", "scalar.dep.256", "scalar.dep.1024", "scalar.branch.256")
            for hart in range(3)]


def log(records=None, done=None):
    records = smoke_records() if records is None else records
    done = [{"failed": 0}] if done is None else done
    return "\n".join(["IRIS_REGION " + json.dumps(row) for row in records]
                     + ["IRIS_BATCH_DONE " + json.dumps(row) for row in done]) + "\n"


class BenchmarkConsoleTests(unittest.TestCase):
    def check_rejected(self, text):
        with self.assertRaises(ValueError):
            console.validate(text, CORPUS, 3, True)

    def test_complete_smoke_has_twelve_rows_without_timing_certification(self):
        result = console.validate(log(), CORPUS, 3, True)
        self.assertEqual(result["regions"], 12)
        self.assertTrue(result["functional_checks_passed"])
        self.assertFalse(result["timing_accuracy_certified"])

    def test_missing_hart_or_case_is_rejected(self):
        self.check_rejected(log(smoke_records()[:-1]))

    def test_duplicate_region_is_rejected(self):
        self.check_rejected(log(smoke_records() + [smoke_records()[0]]))

    def test_unknown_case_is_rejected(self):
        records = smoke_records()
        records[0]["case_id"] = "unknown"
        self.check_rejected(log(records))

    def test_failed_checksum_is_rejected_even_with_guest_pass(self):
        records = smoke_records()
        records[0]["checksum"] = 8
        self.check_rejected(log(records))

    def test_guest_cannot_change_its_own_expected_result(self):
        records = smoke_records()
        records[0]["checksum"] = records[0]["expected_checksum"] = 999
        self.check_rejected(log(records))

    def test_guest_failure_is_rejected_even_with_matching_checksum(self):
        records = smoke_records()
        records[0]["pass"] = False
        self.check_rejected(log(records))

    def test_invalid_cycle_interval_is_rejected(self):
        records = smoke_records()
        records[0]["end_cycle"] = 99
        self.check_rejected(log(records))

    def test_counter_boolean_is_not_an_integer_measurement(self):
        records = smoke_records()
        records[0]["instret_delta"] = True
        self.check_rejected(log(records))

    def test_counter_and_checksum_must_fit_unsigned_64_bits(self):
        for field in ("start_cycle", "end_cycle", "instret_delta", "checksum", "expected_checksum"):
            for value in (-1, 1 << 64):
                with self.subTest(field=field, value=value):
                    records = smoke_records()
                    records[0][field] = value
                    self.check_rejected(log(records))

    def test_direct_api_rejects_invalid_hart_count(self):
        for harts in (False, True, 0, 4, "3", 2.0):
            with self.subTest(harts=harts):
                with self.assertRaises(ValueError):
                    console.validate(log(), CORPUS, harts, True)

    def test_hart_boolean_is_not_a_valid_hart_identity(self):
        records = smoke_records()
        records[1]["hart"] = True
        self.check_rejected(log(records))

    def test_completion_must_be_present_once_and_successful(self):
        for completion in ([], [{"failed": 1}], [{"failed": False}], [{"failed": 0}, {"failed": 0}]):
            with self.subTest(completion=completion):
                self.check_rejected(log(done=completion))

    def test_fatal_diagnostic_rejects_otherwise_successful_log(self):
        self.check_rejected(log() + 'IRIS_FATAL {"hart":2}\n')

    def test_smoke_log_does_not_certify_complete_batch(self):
        with self.assertRaises(ValueError):
            console.validate(log(), CORPUS, 3, False)


if __name__ == "__main__":
    unittest.main()
