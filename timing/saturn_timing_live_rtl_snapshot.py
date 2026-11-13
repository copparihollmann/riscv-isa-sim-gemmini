#!/usr/bin/env python3
"""Read-only owned-process snapshot of completed K1 CSR results before UART calls clobber them."""
import argparse,hashlib,json,os,struct,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=a.run.resolve();ref=a.reference.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);receipt=json.loads((run/'run.json').read_text());build=json.loads((ref/'build.json').read_text());binary=Path(receipt['argv'][0]);matches=[]
 for directory in Path('/proc').iterdir():
  if not directory.name.isdigit():continue
  try:argv=[x.decode()for x in(directory/'cmdline').read_bytes().split(b'\0')if x]
  except(OSError,UnicodeError):continue
  if argv==receipt['argv']and directory.stat().st_uid==os.getuid():matches.append(int(directory.name))
 if len(matches)!=1:raise ValueError('Exactly one owned matching local RTL process required')
 pid=matches[0]
 if sha(Path(f'/proc/{pid}/exe'))!=build['binary_sha256']:raise ValueError('Live executable differs from qualified build')
 if struct.unpack_from('<H',binary.read_bytes(),16)[0]!=2:raise ValueError('Explicit non-PIE target binary required')
 symbol=[line for line in subprocess.check_output(['nm','-an',str(binary)],text=True).splitlines()if line.endswith(' _ZL9iris_root')]
 if len(symbol)!=1:raise ValueError('Exact source host root-pointer symbol required')
 pointer_address=int(symbol[0].split()[0],16);header=next(Path(name)for name in build['input_sha256']if name.endswith('/VTestDriver___024root.h'))
 if sha(header)!=build['input_sha256'][str(header)]:raise ValueError('Compiled model-layout header changed')
 prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain__DOT__element_reset_domain_shuttle_tile__DOT__core__DOT__';members={'tb':'TestDriver__DOT__trace_count','COM_valid':prefix+'com_uops_reg_0_valid','COM_retire':prefix+'com_retire_0','COM_PC':prefix+'com_uops_reg_0_bits_pc'}
 for register in[1,6,8,10,16,17,28,29]:members['x'+str(register)]=prefix+'iregfile_'+str(register)
 source='#include "VTestDriver___024root.h"\n#include <cstdio>\n#include <cstddef>\nint main(){\n'
 for name,member in members.items():source+='std::printf("'+name+' %zu %zu\\n",offsetof(VTestDriver___024root,'+member+'),sizeof(((VTestDriver___024root*)0)->'+member+'));\n'
 source+='}\n';(out/'layout.cpp').write_text(source);cmd=['/usr/bin/g++','-O2','-std=c++20','-I'+str(header.parent),'-I/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(out/'layout.cpp'),'-o',str(out/'layout')]
 with(out/'compile.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 offsets={name:{'offset':int(offset),'bytes':int(width)}for name,offset,width in (line.split()for line in subprocess.check_output([str(out/'layout')],text=True).splitlines())};(out/'layout.json').write_text(json.dumps(offsets,indent=2)+'\n');fd=os.open(f'/proc/{pid}/mem',os.O_RDONLY)
 try:
  root=int.from_bytes(os.pread(fd,8,pointer_address),'little');snapshots=[]
  for sample in range(1000):
   values={name:int.from_bytes(os.pread(fd,row['bytes'],root+row['offset']),'little')for name,row in offsets.items()};values['host_monotonic']=time.monotonic();snapshots.append(values)
   if sample>=1 and values['COM_valid']and values['COM_retire']and 0x8000013a<=values['COM_PC']<0x80000156 and values['x1']==0x80000604 and 0x80000740<=values['x10']<0x80000757:
    previous=snapshots[0]
    if values['tb']>previous['tb']and all(values['x'+str(n)]==previous['x'+str(n)]for n in[6,8,16,17,28,29]):break
   time.sleep(.01)
  else:raise ValueError('No advancing, stable, retired first-putstr source snapshot')
 finally:os.close(fd)
 values=snapshots[-1];counters={'before':values['x29'],'after_scalar':values['x28'],'after_drain':values['x6'],'after_readout':values['x8'],'minstret_before':values['x17'],'minstret_after_scalar':values['x16']}
 if not counters['before']<counters['after_scalar']<=counters['after_drain']<=counters['after_readout']:raise ValueError('Completed source CSR results are not ordered')
 (out/'snapshots.json').write_text(json.dumps(snapshots,indent=2)+'\n');(out/'running-receipt.json').write_bytes((run/'run.json').read_bytes());dis=R/'build/saturn-timing-live-guest-v1/guest.disassembly';(out/'guest.disassembly').write_bytes(dis.read_bytes());report={'schema':'iris.saturn_K1_completed_ROI_readonly_live_snapshot.v1','pass':True,'owned_PID':pid,'owned_exact_argv':receipt['argv'],'binary_sha256':build['binary_sha256'],'ELF_sha256':sha(run/'guest.elf'),'host_root_symbol_address':pointer_address,'live_root_pointer':root,'read_only_proc_mem':True,'process_paused_or_modified':False,'snapshot_count':len(snapshots),'source_counter_values':counters,'source_CSR_destinations':{'0x800004dc':'mcycle -> x29','0x800004e0':'minstret -> x17','0x8000056c':'mcycle -> x28','0x80000570':'minstret -> x16','0x80000578':'mcycle -> x6','0x8000059a':'mcycle -> x8'},'flow_qualification':'Actual COM valid+retire in putstr; RA0x80000604 and a0 inside first VALUES string. All ROI CSR reads, scalar/vector/matrix checks and saves precede that call. putstr machine body writes only x10,x13,x14,x15, preserving the observed CSR-result registers. Snapshots agree while TB advances.','whole_guest_UART_or_HTIF_completion_claimed':False,'input_sha256':{str(path):sha(path)for path in[Path(__file__),binary,ref/'build.json',header,run/'guest.elf',dis]},'artifacts_sha256':{path.name:sha(path)for path in out.iterdir()if path.is_file()},'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'source_counter_values':counters,'snapshots':len(snapshots)}))
if __name__=='__main__':main()
