
# Local adaptation: reuse validated, frozen simulator RTL/driver in an isolated manager.
class FrozenU250BitBuilder(XilinxAlveoU250BitBuilder):
    def _verify_frozen_inputs(self):
        import pathlib, hashlib, json
        root=pathlib.Path(__file__).resolve().parents[3]
        fs=root/"firesim"
        manifest=json.loads((root/"frozen-inputs.json").read_text())
        expected_folder="cl_"+self.build_config.get_chisel_quintuplet()
        assert (fs/"platforms/xilinx_alveo_u250"/expected_folder).is_dir()
        for item in manifest["files"]:
            path=fs/item["path"]
            assert path.is_file() and path.stat().st_size==item["bytes"]
            assert hashlib.sha256(path.read_bytes()).hexdigest()==item["sha256"], "Frozen build input changed: "+item["path"]
        rootLogger.info("Verified immutable RTL, driver, and platform snapshot; frequency selection remains native Vivado flow")
    def replace_rtl(self):
        self._verify_frozen_inputs()
    def build_driver(self):
        self._verify_frozen_inputs()
