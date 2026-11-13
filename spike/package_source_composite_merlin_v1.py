#!/usr/bin/env python3
"""NEW additive Merlin descriptors; never edits the frozen v2 package/provider."""
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike import empirical_provider_source_composite_merlin_v1 as A

def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);p=A.base_module();profiles={}
 for profile,(base,expected)in A.BASES.items():
  p.need(p.sha(base)==expected,'Frozen base descriptor changed');m=copy.deepcopy(p.document(base));r=p.experimental_empirical_simulator(base);p.need(r['available'],'Frozen base profile unavailable')
  m.update(package_kind=A.KIND,model_provider=str(Path(A.__file__).resolve()),base_manifest=str(base),base_manifest_sha256=expected,isa_extensions=list(A.EXTENSIONS),isa_metadata_scope='Iris source ISA declarations and actual frozen per-hart positive/refusal gates; not a timing/image certificate')
  for file in[base,Path(A.__file__).resolve(),Path(__file__).resolve(),*A.HOST_CONTRACTS]:m['input_sha256'][str(file)]=p.sha(file)
  d=out/profile;d.mkdir();f=d/'manifest.json';f.write_text(json.dumps(m,indent=2)+'\n');r=A.experimental_empirical_simulator(f);p.need(r['available'],r.get('reason'));profiles[profile]=dict(manifest=str(f),sha256=p.sha(f))
 (out/'package.json').write_text(json.dumps(dict(schema='iris.additive_source_composite_Merlin_package.v1',**{'pass':True},profiles=profiles,native_or_fixture_changed=False,base_v2_unchanged=True,default_changed=False,source_image_attested=False),indent=2)+'\n')
 (out/'RUN.txt').write_text('Optional additive Merlin adapter; original v2 package and defaults remain unchanged.\n\nSet for source compute:\nexport MERLIN_TARGET_PATH='+str(ROOT/'integration/iris-mlir')+'\nexport MERLIN_IRIS_TIMING=empirical\nexport MERLIN_IRIS_ALLOW_EXPERIMENTAL_TIMING=1\nexport MERLIN_IRIS_MODEL_MANIFEST='+profiles['source_compute']['manifest']+'\n\nUse source_os/manifest.json for the separately tested OS profile (OPU/FENCE off; no compute timing qualification transfer).\n\nMerlin: MatrixRouting(support_target="iris", unit="saturn_vme", config="IrisConfig"); device_simulator.run(matrix, ELF, harts=3, active_hart_ids=(0,) or (0,1), isa="rv64gcv_zfh_zvfh_zvl256b_zvbb", memory=(0x80000000,0x100000000), timeout=360). Hart2 cannot be selected for VME.\n\nGeneric execution also works: python3 -m iris_model.empirical_run --model '+profiles['source_compute']['manifest']+' --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_DIRECTORY --timeout 600\n\nFinite source prototype restrictions and all original qualification limits remain. No physical/image/full2% certificate.\n')
 print(json.dumps(profiles))
if __name__=='__main__':main()
