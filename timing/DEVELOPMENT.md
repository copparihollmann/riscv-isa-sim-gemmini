# Building and checking the timing extension

The `mlsys27/megaphase` branch contains the optional annotated Spike runtime
and Gemmini timing providers. The runtime observes architectural execution.
Providers translate accelerator commands into timing events without changing
the functional Gemmini extension. Model parameters and provider selection are
explicit inputs, not defaults inferred from a benchmark.

## Dependencies

Native tests require Python 3.10+, a C++20 compiler, CMake, Boost headers and
OpenSSL development libraries. A full Spike build additionally requires Make,
Boost system/regex libraries and the device-tree compiler. On Debian/Ubuntu,
the corresponding packages are `build-essential`, `cmake`, `libboost-dev`,
`libboost-system-dev`, `libboost-regex-dev`, `libssl-dev` and
`device-tree-compiler`.

Gemmini source-export checks also require Merlin's standalone `merlin-timing`
Python package. Install the companion source into a virtual environment:

```sh
python3 -m venv /path/to/check-env
/path/to/check-env/bin/python -m pip install /path/to/merlin/packages/merlin-timing
```

The package supplies bundle verification and build helpers. These checks do not
require PyTorch, xDSL, captured models or generated compiler implementations.

## Native checks without guest execution

Run from the Spike source root. Use build directories outside the source tree
and point `TMPDIR` at a writable temporary directory.

```sh
export TMPDIR=/path/to/temporary-directory
export PYTHONDONTWRITEBYTECODE=1
python3 -B timing/tests/test_build.py
python3 -B timing/tests/run_unit.py --build-dir /path/to/native-model-checks
cmake -S timing/core -B /path/to/core-checks -DBUILD_TESTING=ON
cmake --build /path/to/core-checks --parallel 2
ctest --test-dir /path/to/core-checks --output-on-failure
/path/to/check-env/bin/python -B examples/gemmini/timing/source_service/tests/run_checks.py \
  --build-dir /path/to/source-service-checks
```

The source-service runner compiles every standalone C++ test in its directory,
then checks source-bundle membership, hashes and tamper rejection. Pass
`--sanitize` to enable AddressSanitizer and UndefinedBehaviorSanitizer.
`--cxx` selects the compiler. The native model runner also accepts `--sanitize`.
Neither runner launches Spike or a hardware simulator.

The original Gemmini provider has a separate test suite. Its exporter requires
the exact public `libgemmini` revision
`ea8f7ed7afd68e001fb06ddccad9a023c990961d`, including the generated
`gemmini_params.h` selected by `stock_u250.json`:

```sh
/path/to/check-env/bin/python -B examples/gemmini/timing/tests/run_tests.py \
  --engine-include timing/core/include \
  --spike-root /absolute/path/to/this/checkout \
  --public-library /path/to/pinned/libgemmini \
  --build-dir /path/to/new-original-provider-checks
```

This suite checks the original provider under address/undefined-behavior
sanitizers and verifies the pinned source facts. It does not execute a guest.
The experimental source-service provider is selected and exported separately
by `examples/gemmini/timing/export_source_service.py`.

`examples/gemmini/timing/export_execute_service.py` specializes a verified
original-provider bundle for operand-sensitive input service. It accepts the
two explicitly pinned bridge revisions, retains the remaining bundle members
unchanged and records the actual input bridge hash. The export tests compile
the specialized bundle, in addition to checking membership and tamper rejection.

## Source identity and experimental reproducibility

`timing/core/source-manifest.json` records the complete vendored engine source
roster and SHA-256 hashes. This copy includes local engine changes and uses
the `spike.timing_core.source_manifest.v1` schema. It is not an unmodified
export from a different revision of `merlin-timing`.

`timing/build.py --build-dir /path/to/build --identity-only` generates a source
identity without compiling or running a simulator. A full build embeds that
identity in the observer. Provider source bundles have their own membership
and content hashes, and model files bind the loaded libraries in load order.

To reproduce an existing timing result, retain its exact simulator binary,
source identity, functional extension, provider library, model, executable,
input digest and timing scope. A newer release source revision does not
replace those recorded inputs. Native tests establish implementation behavior,
not cycle accuracy or qualification against a hardware configuration.

