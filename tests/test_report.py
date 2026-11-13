import copy
import unittest

from iris_model.report import profile, union_cycles, validate


class ReportTest(unittest.TestCase):
    def graph(self):
        return {"schema_version": 1, "status": "experimental_uncalibrated", "harts": 3, "cycles": 12,
                "events": [dict(id=0, hart=0, name="compute", resource="vme", region="gemm", pc=16,
                                start=0, end=10, submitted=0, lane=0, bytes=0, macs=100, deps=[]),
                           dict(id=1, hart=1, name="load", resource="memory", region="gemm", pc=32,
                                start=0, end=5, submitted=0, lane=0, bytes=64, macs=0, deps=[]),
                           dict(id=2, hart=0, name="readout", resource="vme", region="gemm", pc=20,
                                start=10, end=12, submitted=0, lane=0, bytes=0, macs=0, deps=[0])]}

    def test_overlaps_and_functions(self):
        self.assertEqual(union_cycles([(0, 10), (2, 5), (8, 20), (25, 30)]), 25)
        summary, trace = profile(self.graph(), 1e8, "synthetic test fixture", [(16, 24, "gemm")])
        self.assertEqual(summary["resources"]["vme"]["busy_fraction"], 1)
        self.assertEqual(trace["traceEvents"][0]["args"]["function"], "gemm")
        self.assertIsNone(trace["traceEvents"][1]["args"]["function"])
        self.assertEqual(sum(e["ph"] in ("s", "f") for e in trace["traceEvents"]), 2)
        self.assertIsNone(summary["regions"][0]["stall_breakdown"])
        attributed=next(r for r in summary["functions"] if r["function"]=="gemm")
        self.assertEqual((attributed["symbol_address"],attributed["active_cycles"],attributed["model_operations"]),(16,12,2))
        self.assertTrue(any(r["function"] is None for r in summary["functions"]))

    def test_invalid_graph(self):
        graph = self.graph()
        graph["events"][2]["start"] = 9
        with self.assertRaises(ValueError): profile(graph, 1e8, "test")
        with self.assertRaises(ValueError): profile(self.graph(), 0, "test")

    def test_partial_trace_preserves_occupancy_without_crediting_unfinished_work(self):
        graph = self.graph()
        graph.update(partial=True, pending_operations=2)
        graph["events"][2]["completed"] = False
        summary, trace = profile(graph, 1e8, "test")
        self.assertTrue(summary["partial"])
        self.assertEqual(summary["pending_operations"], 2)
        vme = summary["regions"][0]["units"]["vme"]
        self.assertEqual(vme["busy_cycles"], 12)
        self.assertIsNone(vme["macs"])
        self.assertIsNone(vme["bytes"])
        self.assertFalse(trace["traceEvents"][2]["args"]["completed"])
        graph["partial"] = False
        with self.assertRaises(ValueError): profile(graph, 1e8, "test")

    def test_uninstrumented_is_unavailable_and_clock_must_match(self):
        graph = self.graph()
        graph.update(base_clock_hz=1e8, traffic_accounting="not_instrumented", arithmetic_accounting="not_instrumented")
        summary, _ = profile(graph, 1e8, "test")
        self.assertIsNone(summary["regions"][0]["units"]["vme"]["macs"])
        with self.assertRaisesRegex(ValueError, "instrumented"):
            profile(graph, 1e8, "test", roofline_memory_resource="memory")
        with self.assertRaisesRegex(ValueError, "base clock"):
            profile(graph, 1e9, "test")

    def test_pipelined_occupancy_uses_union_not_latency_sum(self):
        graph = self.graph()
        graph['resources'] = {'vme': 1, 'memory': 1}
        graph['events'][2].update(start=2, end=12, deps=[])
        summary, _ = profile(graph, 1e8, 'test')
        self.assertEqual(summary['resources']['vme']['busy_cycles'], 12)
        self.assertEqual(summary['resources']['vme']['busy_fraction'], 1)
        self.assertEqual(summary['resources']['vme']['occupancy_basis'],
                         'union_of_in_flight_operation_spans')
        self.assertEqual(summary['regions'][0]['units']['vme']['busy_fraction'], 1)
        graph['events'][2]['lane'] = 1
        with self.assertRaisesRegex(ValueError, 'issue lane'):
            profile(graph, 1e8, 'test')

    def test_invalid_global_dimensions_and_dependency_types(self):
        for field, value in [('harts', False), ('harts', 0), ('cycles', -1), ('cycles', True)]:
            graph = self.graph()
            graph[field] = value
            with self.assertRaises(ValueError):
                profile(graph, 1e8, 'test')
        graph = self.graph()
        graph['events'][2]['deps'] = [False]
        with self.assertRaisesRegex(ValueError, 'dependency'):
            profile(graph, 1e8, 'test')

    def test_roofline_needs_single_sourced_traffic_level(self):
        graph = self.graph()
        graph["events"][1]["hart"] = 0
        peaks = {"vme": {"macs_per_cycle": 20, "source": "synthetic fixture"},
                 "memory": {"bytes_per_cycle": 8, "source": "synthetic fixture"}}
        summary, _ = profile(graph, 1e8, "test", peaks=peaks, roofline_memory_resource="memory")
        roofline = summary["regions"][0]["roofline"]
        self.assertEqual(roofline["arithmetic_intensity_ops_per_byte"], 200 / 64)
        self.assertEqual(roofline["ceiling_ops_per_cycle"], 25)
        with self.assertRaises(ValueError):
            profile(graph, 1e8, "test", peaks={"vme": {"macs_per_cycle": 20}})

    def measurements(self):
        return {"hardware_sha256": "a" * 64, "simulator_sha256": "b" * 64,
                "calibration": {"sha256": "c" * 64, "hardware_sha256": "a" * 64,
                                "simulator_sha256": "b" * 64, "fitting_case_ids": ["fit"]},
                "measurements": [{"case_id": "holdout", "region": "e2e", "harts": 2,
                                  "elf_sha256": "d" * 64, "hardware_sha256": "a" * 64,
                                  "simulator_sha256": "b" * 64,
                                  "reference_cycles": 10000, "modeled_cycles": 9800,
                                  "reference_kind": "firesim_target_cycles"}]}

    def test_signed_error(self):
        data = self.measurements()
        report = validate(data)
        self.assertEqual(report["rows"][0]["signed_error_percent"], -2)
        self.assertEqual(report["status"], "passed_supplied_measurements")
        self.assertFalse(report["certified"])
        data["measurements"][0]["modeled_cycles"] = 10201
        self.assertEqual(validate(data)["status"], "failed")

    def test_no_leakage_or_stale_calibration(self):
        for change in ("fit", "stale", "missing", "host_time"):
            data = copy.deepcopy(self.measurements())
            if change == "fit": data["measurements"][0]["case_id"] = "fit"
            if change == "stale": data["calibration"]["hardware_sha256"] = "e" * 64
            if change == "missing": data["measurements"] = []
            if change == "host_time": data["measurements"][0]["reference_kind"] = "wallclock"
            with self.assertRaises(ValueError): validate(data)


if __name__ == "__main__": unittest.main()
