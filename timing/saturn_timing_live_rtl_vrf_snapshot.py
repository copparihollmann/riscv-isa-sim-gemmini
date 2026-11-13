#!/usr/bin/env python3
"""Read final physical row state from the exact owned live saved-RTL process."""
import argparse,hashlib,json,os,struct,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=a.run.resolve();ref=a.reference.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);receipt=json.loads((run/'run.json').read_text());build=json.loads((ref/'build.json').read_text());pids=[]
 for d in Path('/proc').iterdir():
  if d.name.isdigit():
   try:cmd=[x.decode()for x in(d/'cmdline').read_bytes().split(b'\0')if x]
   except(OSError,UnicodeError):continue
   if cmd==receipt['argv']and d.stat().st_uid==os.getuid():pids.append(int(d.name))
 if len(pids)!=1:raise ValueError('One live owned exact-argv process required')
 pid=pids[0];binary=Path(receipt['argv'][0])
 if sha(Path(f'/proc/{pid}/exe'))!=build['binary_sha256']:raise ValueError('Live binary identity changed')
 header=next(Path(p)for p in build['input_sha256']if p.endswith('/VTestDriver___024root.h'));header_data=header.read_text();base='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain__DOT__element_reset_domain_shuttle_tile__DOT__';core=base+'core__DOT__';unit=base+'vector_unit__DOT__';members={'tb':'TestDriver__DOT__trace_count','core_clock':'TestDriver__DOT__testHarness__DOT__source__DOT__clk_i','COM_PC':core+'com_uops_reg_0_bits_pc','readout_valids':unit+'vu__DOT__vos__DOT__mvout_valids','source_vl':core+'csr__DOT__reg_vconfig_vl','source_vsew':core+'csr__DOT__reg_vconfig_vtype_vsew','source_vlmul_mag':core+'csr__DOT__reg_vconfig_vtype_vlmul_mag','source_vtwiden':core+'csr__DOT__reg_vconfig_vtype_vtwiden','cycle_small':core+'csr__DOT__small_0','cycle_large':core+'csr__DOT__large_0','mcountinhibit':core+'csr__DOT__reg_mcountinhibit'}
 for bank in range(4):members['bank'+str(bank)]=unit+'vu__DOT__vrf__DOT__vrf__DOT__vrf_'+str(bank)+'__DOT__vrf_ext__DOT__Memory'
 for member in members.values():
  if member not in header_data:raise ValueError('Missing exact compiled physical state '+member)
 code='#include "VTestDriver___024root.h"\n#include <cstdio>\n#include <cstddef>\nint main(){\n'
 for name,member in members.items():code+='std::printf("'+name+' %zu %zu\\n",offsetof(VTestDriver___024root,'+member+'),sizeof(((VTestDriver___024root*)0)->'+member+'));\n'
 code+='}\n';(out/'layout.cpp').write_text(code);cmd=['/usr/bin/g++','-O2','-std=c++20','-I'+str(header.parent),'-I/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(out/'layout.cpp'),'-o',str(out/'layout')]
 with(out/'compile.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 layout={n:{'offset':int(o),'bytes':int(s)}for n,o,s in(line.split()for line in subprocess.check_output([str(out/'layout')],text=True).splitlines())};(out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n');symbols=[x for x in subprocess.check_output(['nm','-an',str(binary)],text=True).splitlines()if x.endswith(' _ZL9iris_root')];address=int(symbols[0].split()[0],16);fd=os.open(f'/proc/{pid}/mem',os.O_RDONLY)
 try:
  root=int.from_bytes(os.pread(fd,8,address),'little');snapshots=[]
  for _ in range(2):
   values={};banks={}
   for name,row in layout.items():
    raw=os.pread(fd,row['bytes'],root+row['offset'])
    if name.startswith('bank'):
     if len(raw)!=256:raise ValueError('Configured physical VRF bank extent changed')
     banks[name]=list(struct.unpack('<64I',raw))
    else:values[name]=int.from_bytes(raw,'little')
   row=[]
   for eg in range(48,56):row.extend(banks['bank'+str(eg%4)][(eg//4)*4:(eg//4)*4+4])
   snapshots.append({'control':values,'all_physical_banks':banks,'logical_v24_to_v27_row_words':row,'host_monotonic':time.monotonic()});time.sleep(.05)
 finally:os.close(fd)
 if snapshots[1]['control']['tb']<=snapshots[0]['control']['tb']or snapshots[0]['logical_v24_to_v27_row_words']!=[6]*32 or snapshots[1]['logical_v24_to_v27_row_words']!=[6]*32:raise ValueError('Stable final physical full row does not equal independent2*3golden')
 if any(s['control']['readout_valids']for s in snapshots):raise ValueError('Source readout pipe still active during final-state snapshot')
 (out/'snapshots.json').write_text(json.dumps(snapshots,indent=2)+'\n');report={'schema':'iris.saturn_K1_actual_RTL_final_physical_VRF_row.v1','pass':True,'owned_PID':pid,'binary_sha256':build['binary_sha256'],'ELF_sha256':sha(run/'guest.elf'),'read_only_proc_mem':True,'process_paused_or_modified':False,'physical_banks':4,'DLEN_bits':128,'physical_bank_rows':16,'global_element_groups':list(range(48,56)),'mapping':'bank=globalEG%4; physicalrow=globalEG//4; eachrow4littleendianuint32. Logicalbyteoffset=globalEG*16; noaddedbankoffset.','expected_all32_words':6,'observed_all32_words':snapshots[1]['logical_v24_to_v27_row_words'],'source_config':{k:v for k,v in snapshots[1]['control'].items()if k.startswith('source_')},'snapshots':len(snapshots),'tail_timing_or_missing_edge_count_claimed':False,'whole_guest_UART_or_HTIF_completion_claimed':False,'input_sha256':{str(p):sha(p)for p in[Path(__file__),binary,ref/'build.json',header,run/'guest.elf']},'artifact_sha256':{p.name:sha(p)for p in out.iterdir()if p.is_file()},'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'all32_words':snapshots[-1]['logical_v24_to_v27_row_words'],'source_config':report['source_config']}))
if __name__=='__main__':main()
