#!/usr/bin/env python3
"""Write reviewed integration deltas only into a caller-owned candidate root."""
import argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Changed integration source; review replacement: '+old[:80])
    return text.replace(old,new)
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args();out=a.root.resolve()
    path=Path('integration/iris-mlir/configure_model.py');text=(ROOT/path).read_text()
    text=replace(text,'    binary = Path(verified["binary"])','    binary = Path(verified["binary"])\n    native = Path(verified.get("native_binary", binary))\n    native_sha = verified.get("native_binary_sha256", verified["binary_sha256"])\n    if sha(native) != native_sha:\n        raise ValueError("Verified native simulator changed")')
    text=replace(text,'test = {"pass": passed, "binary_sha256": sha(binary), "argv": argv,','test = {"pass": passed, "binary_sha256": sha(binary), "native_binary_sha256": native_sha, "argv": argv,')
    text=replace(text,'inputs = [provider_path, prov_path, binary, uart, elf, rom, dtb, test_path, out / "selftest.stdout", out / "selftest.stderr"]','inputs = [provider_path, prov_path, binary, native, uart, elf, rom, dtb, test_path, out / "selftest.stdout", out / "selftest.stderr"]')
    text=replace(text,'"binary_sha256": sha(binary), "model_provider": str(provider_path),','"binary_sha256": sha(binary), "native_binary": str(native), "native_binary_sha256": native_sha,\n                "model_provider": str(provider_path),')
    target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    path=Path('integration/iris-mlir/simulator.py');text=(ROOT/path).read_text()
    text=replace(text,'        binary = manifest["binary"]','        binary = manifest["binary"]\n        native = verified.get("native_binary", binary)\n        native_sha = verified.get("native_binary_sha256", manifest["binary_sha256"])\n        if sha(native) != native_sha:\n            raise ValueError("native simulator binary changed")\n        if manifest.get("native_binary_sha256", native_sha) != native_sha or manifest.get("native_binary", native) != native:\n            raise ValueError("manifest native identity differs from verified model")')
    text=replace(text,'"isa_extensions": manifest["isa_extensions"], "per_hart_isa": manifest["per_hart_isa"],','"isa_extensions": manifest["isa_extensions"], "per_hart_isa": manifest["per_hart_isa"],\n                "native_binary": native, "native_binary_sha256": native_sha,\n                "native_device_abi": verified.get("native_device_abi"),\n                "execution_input_sha256": dict(manifest["input_sha256"], **{str(native): native_sha}),')
    target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    path=Path('integration/merlin/src/merlin/runtime/backends/device_simulator.py');text=(ROOT/path).read_text()
    marker='\ndef resolve(matrix) -> dict[str, Any]:\n'
    helper='''\ndef execution_inputs(descriptor: dict[str, Any]) -> dict[str, str]:
    """Validate launcher/native/support bytes without inferring certification."""
    expected = descriptor.get("execution_input_sha256", {})
    if not isinstance(expected, dict):
        raise DeviceSimulatorError("execution_input_sha256 must be a mapping")
    expected = dict(expected)
    for name, value in [(descriptor.get("binary"), descriptor.get("binary_sha256")),
                        (descriptor.get("native_binary"), descriptor.get("native_binary_sha256"))]:
        if name is None and value is None:
            continue
        if not isinstance(name, str) or not isinstance(value, str) or len(value) != 64:
            raise DeviceSimulatorError("invalid launcher/native input identity")
        if name in expected and expected[name] != value:
            raise DeviceSimulatorError("conflicting simulator input identity")
        expected[name] = value
    for name, value in expected.items():
        if not isinstance(name, str) or not isinstance(value, str) or not Path(name).is_file() or sha256(name) != value:
            raise DeviceSimulatorError("simulator execution input missing or changed: " + str(name))
    return expected

'''
    text=replace(text,marker,'\n'+helper+marker)
    text=replace(text,'    return descriptor\n','    execution_inputs(descriptor)\n    return descriptor\n')
    text=replace(text,'    before = sha256(elf)\n','    before = sha256(elf)\n    inputs = execution_inputs(descriptor)\n')
    text=replace(text,'        raise DeviceSimulatorError("execution inputs changed during run")','        raise DeviceSimulatorError("execution inputs changed during run")\n    if any(sha256(name) != value for name, value in inputs.items()):\n        raise DeviceSimulatorError("launcher/native/support inputs changed during run")')
    text=replace(text,'"elf_sha256": before, "simulator": descriptor}','"elf_sha256": before, "execution_input_sha256": inputs, "simulator": descriptor}')
    target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    mirror=out/'integration/merlin/merlin/python/merlin/runtime/backends/device_simulator.py';mirror.parent.mkdir(parents=True,exist_ok=True);mirror.write_text(text)
if __name__=='__main__':main()
