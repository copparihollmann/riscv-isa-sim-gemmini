#!/usr/bin/env python3
"""Freeze first live-bridge guest, real toolchain/header inputs and functional gate."""
import argparse,hashlib,json,os,re,shutil,stat,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--functional',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build=a.build.resolve();functional=a.functional.resolve();out=a.output.resolve()
 if out.exists():raise ValueError('Preserve previous guest capsule')
 report=json.loads((build/'build.json').read_text());positive=json.loads((functional/'report.json').read_text())
 if not positive['pass']:raise ValueError('Real three-hart functional gate required')
 files={Path(__file__)}|{p for base in[build,functional]for p in base.rglob('*')if p.is_file()};receipts=[report,positive]
 for receipt in receipts:
  for name,wanted in receipt['input_sha256'].items():
   path=Path(name)
   if sha(path)!=wanted:raise ValueError('Changed exact guest input '+name)
   files.add(path)
 gcc=Path(report['argv'][0]);tools={}
 for name in ['cc1','as','collect2','ld']:
  tool=Path(subprocess.check_output([str(gcc),'-print-prog-name='+name],text=True).strip())
  if not tool.is_file():raise ValueError('Missing actual compiler child '+name)
  tools[name]={'path':str(tool),'sha256':sha(tool)};files.add(tool)
 libgcc=Path(subprocess.check_output([str(gcc),'-print-libgcc-file-name'],text=True).strip());files.add(libgcc);tools['libgcc']={'path':str(libgcc),'sha256':sha(libgcc)}
 dependency_command=[str(gcc),'-M','-march=rv64gcv_zicsr_zifencei','-mabi=lp64d','-I'+str(R/'benchmarks'),'-I'+str(R/'third_party/saturn/benchmarks/common'),str(R/'timing/saturn_timing_live_guest.c')];dependencies=subprocess.check_output(dependency_command,text=True);names=dependencies.replace('\\\n',' ').split(':',1)[1].split()
 for name in names:
  path=Path(name)
  if not path.is_absolute():path=R/path
  if not path.is_file():raise ValueError('Missing actual preprocessor input '+str(path))
  files.add(path)
 runtime={}
 for name in ['spike','libsifive_uart.so']:
  binary=next(p for p in files if p.name==name and'combined-frozen-35901887'in str(p));text=subprocess.check_output(['ldd',str(binary)],text=True);runtime[name]={'ldd':text,'libraries':{}}
  for raw in re.findall(r'(?:=>\s+)?(/[^\s()]+)',text):
   path=Path(raw)
   if path.is_file():files.add(path);runtime[name]['libraries'][raw]=sha(path)
 out.mkdir();artifacts=[];seen={}
 for original in sorted(files):
  relative=original.relative_to(R)if original.is_relative_to(R)else Path('external')/str(original).lstrip('/');target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);digest=sha(original);mode=stat.S_IMODE(original.stat().st_mode);key=(digest,mode)
  if key in seen:os.link(seen[key],target)
  else:shutil.copy2(original,target);seen[key]=target
  artifacts.append({'path':str(relative),'source_path':str(original),'sha256':digest,'mode':mode,'bytes':target.stat().st_size})
 closure={'schema':'iris.saturn_initial_live_guest_capsule.v1','pass':True,'source_pins':report['source_pins'],'ELF_sha256':report['ELF_sha256'],'admission_sha256':report['admission_sha256'],'functional_receipt_sha256':sha(functional/'report.json'),'compiler_child_tools':tools,'preprocessor_dependency_command':dependency_command,'preprocessor_dependencies':dependencies,'runtime_libraries':runtime,'artifact_count':len(artifacts),'artifacts':artifacts,'timing_hook_executed':False,'cycle_accuracy_claimed':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(closure,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'artifact_count':len(artifacts)}))
if __name__=='__main__':main()
