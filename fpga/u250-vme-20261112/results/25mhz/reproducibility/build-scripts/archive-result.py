#!/usr/bin/env python3
from pathlib import Path
import sys,shutil,json,hashlib,datetime
root=Path(__file__).resolve().parents[1]
fs=root/"chipyard-vme-u250/sims/firesim"
frequency=int(sys.argv[1])
name="alveo_u250_vme_v256d128_dual_int8_ddr3frfcfs_"+str(frequency)+"mhz"
out=root/"results"/(str(frequency)+"mhz")
out.mkdir(parents=True,exist_ok=True)
build_fs=fs
if frequency==25 and (root/"provenance/parallel-build-plan.json").exists():
    build_fs=root/"parallel-25mhz/firesim"
packages=[p for p in (build_fs/"deploy/results-build").rglob("firesim.tar.gz") if name in str(p)]
if not packages:raise SystemExit("Manager produced no bitstream package for "+name)
package=max(packages,key=lambda p:p.stat().st_mtime)
existing=out/"manifest.json"
if existing.exists():
    old=json.loads(existing.read_text())
    entry=next((x for x in old["files"] if x["path"]=="firesim.tar.gz"),None)
    if entry and (out/"firesim.tar.gz").exists():
        def digest(path):
            h=hashlib.sha256()
            with path.open("rb") as f:
                for block in iter(lambda:f.read(1048576),b""):h.update(block)
            return h.hexdigest()
        if digest(package)==entry["sha256"] and digest(out/"firesim.tar.gz")==entry["sha256"]:
            print("Existing independently archived result verified",frequency)
            raise SystemExit(0)

shutil.copy2(package,out/"firesim.tar.gz")
entries=build_fs/"deploy/built-hwdb-entries"
if entries.exists():
    for p in entries.iterdir():
        if name in p.name and p.is_file():shutil.copy2(p,out/p.name)
for base_name in ["generated-src","output"]:
    parent=fs/"sim"/base_name
    if not parent.exists():continue
    for platform in parent.iterdir():
        if not platform.is_dir():continue
        for path in platform.iterdir():
            if path.is_dir() and "FireSimVMEV256D128DualShuttleConfig" in path.name:
                dest=out/"simulator-collateral"/base_name/platform.name/path.name
                shutil.copytree(path,dest,dirs_exist_ok=True)
staging=fs.parent.parent/"sims/firesim-staging/generated-src"
if staging.exists():
    for path in staging.iterdir():
        if path.is_dir() and "FireSimVMEV256D128DualShuttleConfig" in path.name:
            shutil.copytree(path,out/"simulator-collateral/chipyard-staging"/path.name,dirs_exist_ok=True)
build=next((p for p in package.parents if name in p.name),package.parent)
reports=[]
for path in build.rglob("*.rpt"):
    dest=out/"vivado-reports"/path.relative_to(build)
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(path,dest)
    reports.append(str(dest.relative_to(out)))
if frequency==25 and build_fs!=fs:
    shutil.copytree(build_fs/"platforms/xilinx_alveo_u250",out/"frozen-platform-inputs",dirs_exist_ok=True)
shutil.copytree(root/"provenance",out/"provenance",dirs_exist_ok=True)
shutil.copytree(root/"scripts",out/"reproducibility/build-scripts",dirs_exist_ok=True)
shutil.copy2(root/"BUILD-INFO.txt",out/"reproducibility/BUILD-INFO.txt")
jar=fs/"sim/generated-src/firesim-main.jar"
if jar.exists():
    destination=out/"simulator-collateral/firesim-main.jar"
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(jar,destination)

for p in (build_fs/"deploy").glob("config_build*vme_u250*.yaml"):shutil.copy2(p,out/p.name)
manifest={"frequency_mhz":frequency,"memory_model":"FASED FRFCFS16GBQuadRank","collected_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"files":[],"reports":reports}
for p in out.rglob("*"):
    if not p.is_file():continue
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""):h.update(block)
    manifest["files"].append({"path":str(p.relative_to(out)),"bytes":p.stat().st_size,"sha256":h.hexdigest()})
(out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
print("Archived",frequency,"MHz result",out)
