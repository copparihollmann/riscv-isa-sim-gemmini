#!/usr/bin/env python3
from pathlib import Path
import subprocess,hashlib,json,shutil,yaml
root=Path(__file__).resolve().parents[1]
cy=root/"chipyard-vme-u250"
handoff=root/"handoff"
expected=json.loads((handoff/"sources.json").read_text())
repos={"chipyard":cy,"saturn":cy/"generators/saturn","shuttle":cy/"generators/shuttle","rocket_chip":cy/"generators/rocket-chip","firesim":cy/"sims/firesim"}
actual={}
for name,path in repos.items():
    actual[name]=subprocess.check_output(["git","-C",str(path),"rev-parse","HEAD"],text=True).strip()
    assert actual[name]==expected[name],"Source revision mismatch for "+name
for name,digest in expected["file_sha256"].items():
    assert hashlib.sha256((handoff/name).read_bytes()).hexdigest()==digest,"Handoff hash mismatch "+name
for name,relative in [
    ("VMEDualShuttleConfigs.scala","generators/chipyard/src/main/scala/config/VMEDualShuttleConfigs.scala"),
    ("FireSimVMEDualShuttleConfigs.scala","generators/firechip/chip/src/main/scala/FireSimVMEDualShuttleConfigs.scala")
]:
    target=cy/relative
    assert not target.exists() or target.read_bytes()==(handoff/name).read_bytes(),"Existing differing Scala source"
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(handoff/name,target)
    shutil.copy2(handoff/name,root/"provenance"/name)
patch=handoff/"saturn-firesim-clockgate.patch"
check=subprocess.run(["git","-C",str(repos["saturn"]),"apply","--check",str(patch)],capture_output=True,text=True)
if check.returncode==0:
    subprocess.run(["git","-C",str(repos["saturn"]),"apply",str(patch)],check=True)
else:
    subprocess.run(["git","-C",str(repos["saturn"]),"apply","--reverse","--check",str(patch)],check=True)
actual_patch=subprocess.check_output(["git","-C",str(repos["saturn"]),"diff","--binary"])
(root/"provenance/saturn-firesim-clockgate.patch").write_bytes(actual_patch)
# Select the handoff's pinned board definition without modifying shared Vivado files.
board_repo=root/"provenance/open-nic-board-files"
main_tcl=repos["firesim"]/"platforms/xilinx_alveo_u250/cl_firesim/scripts/main.tcl"
board_line='set_param board.repoPaths [list {'+str(board_repo)+'}]\n'
tcl_text=main_tcl.read_text()
if not tcl_text.startswith(board_line):
    main_tcl.write_text(board_line+tcl_text)
platform_env=repos["firesim"]/"platforms/xilinx_alveo_u250/cl_firesim/scripts/platform_env.tcl"
env_text=platform_env.read_text()
assert env_text.count("set jobs 8")==1 or env_text.count("set jobs 12")==1,"Unexpected Vivado jobs setting"
platform_env.write_text(env_text.replace("set jobs 8","set jobs 12"))
build_script=repos["firesim"]/"platforms/xilinx_alveo_u250/build-bitstream.sh"
script_text=build_script.read_text()
old_vivado='vivado -mode batch -source $CL_DIR/scripts/main.tcl'
new_vivado='"'+str(root/"bin/vivado")+'" -mode batch -source $CL_DIR/scripts/main.tcl'
assert script_text.count(old_vivado)==1 or script_text.count(new_vivado)==1,"Unexpected Vivado invocation"
build_script.write_text(script_text.replace(old_vivado,new_vivado))
shutil.copy2(root/"bin/vivado",root/"provenance/vivado-wrapper.sh")
(root/"provenance/firesim-build-environment.patch").write_bytes(subprocess.check_output(["git","-C",str(repos["firesim"]),"diff","--binary","--","platforms/xilinx_alveo_u250/cl_firesim/scripts/main.tcl","platforms/xilinx_alveo_u250/cl_firesim/scripts/platform_env.tcl","platforms/xilinx_alveo_u250/build-bitstream.sh"]))
deploy=repos["firesim"]/"deploy"
base=yaml.safe_load((handoff/"config_build_recipes_vme_u250.yaml").read_text())
base_name=next(iter(base))
recipes={}
for frequency in [15,25]:
    name=base_name+"_"+str(frequency)+"mhz"
    recipe=json.loads(json.dumps(base[base_name]))
    assert recipe["PLATFORM_CONFIG"]=="FRFCFS16GBQuadRank_BaseXilinxAlveoU250Config"
    recipe["platform_config_args"]["fpga_frequency"]=frequency
    recipe["TARGET_PROJECT_MAKEFRAG"]=str(cy/"generators/firechip/chip/src/main/makefrag/firesim")
    recipes[name]=recipe
    build_dir=root/"vivado-builds"/(str(frequency)+"mhz")
    build_dir.mkdir(parents=True,exist_ok=True)
    config={
        "build_farm":{"base_recipe":"build-farm-recipes/externally_provisioned.yaml","recipe_arg_overrides":{"default_build_dir":str(build_dir),"build_farm_hosts":["localhost"]}},
        "builds_to_run":[name],"agfis_to_share":[],"share_with_accounts":{}
    }
    (deploy/("config_build_vme_u250_"+str(frequency)+"mhz.yaml")).write_text(yaml.safe_dump(config,sort_keys=False))
(deploy/"config_build_recipes_vme_u250.yaml").write_text(yaml.safe_dump(recipes,sort_keys=False))
(root/"provenance/submodule-pins.txt").write_text(subprocess.check_output(["git","-C",str(cy),"submodule","status","--recursive"],text=True))
request={"source_revisions":actual,"host_fpga_clocks_mhz":[15,25],"target_memory_clock_mhz":1000,"target_memory_bytes":17179869184,
         "platform_config":"FRFCFS16GBQuadRank_BaseXilinxAlveoU250Config","memory_model":"FASED FirstReadyFCFSConfig","scheduler_entries":8,"transaction_entries":8,
         "harts":[0,1],"vlen":256,"dlen":128,"dtype":"INT8 OPU","system_bus_bits":128,"tile_beat_bytes":16,
         "clockgate_patch_sha256":hashlib.sha256(actual_patch).hexdigest(),"recipes":list(recipes)}
(root/"provenance/build-request.json").write_text(json.dumps(request,indent=2)+"\n")
print("Verified all five source revisions and prepared both frequency recipes")
