.PHONY: check timing profile-example benchmarks validate-benchmarks build-functional check-functional check-live-timing check-board check-board-integration build-benchmarks-v2 check-benchmarks-v2

DTC ?= /scratch/eygao/iris-cy/.conda-env/bin/dtc

build-functional:
	python3 spike/build.py --dtc $(DTC)

# Requires a built pinned Spike fork; kept separate from the fast unit checks.
check-functional: benchmarks
	spike/run_selftest.sh
	python3 spike/run_functional.py --dtc $(DTC)
	$(MAKE) validate-benchmarks

benchmarks:
	python3 benchmarks/build.py
	python3 benchmarks/build_heldout.py

# Functional Spike logs, never treated as RTL timing calibration.
validate-benchmarks:
	python3 benchmarks/validate_console.py spike/results/smoke.stdout --smoke
	python3 benchmarks/validate_console.py spike/results/batch.stdout

timing:
	cmake -S timing -B build/timing -DCMAKE_BUILD_TYPE=Debug
	cmake --build build/timing -j4

check: timing
	ctest --test-dir build/timing --output-on-failure
	python3 -m unittest discover -s tests -v
	python3 -m unittest discover -s firesim/tests -v
	python3 -m unittest discover -s spike/tests -v
	python3 -m unittest discover -s benchmarks/v2/tests -v
	python3 -m iris_model.provenance hardware/manifest.json
	python3 hardware/dtypes.py --verify
	python3 hardware/memory_paths.py --verify

check-live-timing:
	python3 timing/live_check.py

check-board:
	python3 board/build.py

check-board-integration:
	python3 board/integration_check.py --binary spike/bin/spike-iris-functional --uart spike/bin/libsifive_uart.so

build-benchmarks-v2:
	python3 benchmarks/v2/build.py

check-benchmarks-v2:
	python3 benchmarks/v2/run.py
	python3 -m unittest discover -s benchmarks/v2/tests -v

# Explicitly synthetic example, never presented as measured Iris performance.
profile-example: timing
	build/timing/iris_timing_test --json > build/timing/test-graph.json
	python3 -m iris_model.report profile build/timing/test-graph.json --clock-hz 100000000 --clock-source 'synthetic test fixture, not Iris calibration' --output build/timing/profile
