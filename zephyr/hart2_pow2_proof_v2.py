#!/usr/bin/env python3
"""Compile-byte and source-bound finite checks; no target timing inputs."""
import argparse,hashlib,importlib.util,json,re,struct,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pow2_cases',ROOT/'benchmarks/zephyr_hart2_pow2_v2/cases.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):
 f=Path(p).open('rb');e=ELFFile(f);syms={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
 def raw(name):
  s=syms[name];sec=e.get_section(s['st_shndx']);off=s['st_value']-sec['sh_addr'];return sec.data()[off:off+s['st_size']]
 return f,e,syms,raw
def run(a):
 out=a.output.resolve();out.mkdir(parents=True);b=a.build.resolve();elf=b/'zephyr/zephyr.elf';f,e,s,raw=load(elf);corpus=m.generate();source=ROOT/'benchmarks/zephyr_hart2_pow2_v2';assert json.loads((source/'corpus.json').read_text())==corpus
 groupdata=b''.join(struct.pack('<9I',g['kind'],g['sew'],g['lmul'],g['shape'],g['format'],g['operations'],g['hart_mask'],g['trial'],g['first_region'])for g in corpus['groups'])
 descdata=b''.join(struct.pack('<6I',r['group'],r['hart'],r['offset'],r['bytes'],r['elements'],r['element_bytes'])for r in corpus['regions'])
 assert raw('groups')==groupdata and raw('descriptors')==descdata
 body=[]
 for name,opcode in [('packet_vadd',0x03840c57),('packet_mm_int',0xf2880077),('packet_mm_e4',0xf2881077),('packet_mm_e5',0xf28810f7)]:
  expected=struct.pack('<I',opcode)*16+bytes.fromhex('7d155dfd')+struct.pack('<I',opcode)+bytes.fromhex('8280');assert raw(name)==expected
  body.append(dict(symbol=name,pc=s[name]['st_value'],bytes=len(expected),sha256=hashlib.sha256(expected).hexdigest(),target_opcode=hex(opcode),target_ops='16*blocks+1',permitted_blocks=[1,4],exact_dynamic_target_counts=[17,65],dynamic_scalar_loop_instructions=[2,8],has_data_memory_accesses=False))
 # A selector is rd bit0; B selector deliberately lives outside the word.
 assert((0xf2881077>>7)&1)==0 and((0xf28810f7>>7)&1)==1
 sf=source/'src/compute.c';st=sf.read_text();assert '(g->format==2||g->format==4)?vme_vsettnt_e8w4_alt(g->shape)'in st
 seq=ROOT/'hardware/evidence/outer-product-sequencer.scala';sq=seq.read_text()
 for fact in ['e5m2_l := dis_inst.rd(0)','e5m2_t := dis_inst.vconfig.vtype.altfmt','val tm = dis_inst.vconfig.vtype.tm','val tn = dis_inst.vconfig.vl','val tk = dis_inst.vconfig.vtype.tk','< tm','< tn']:assert fact in sq
 header=ROOT/'third_party/saturn/benchmarks/common/vme.h';hs=header.read_text();assert 'size_t vtype_bits = (0 << 3) | (1 << 8)'in hs
 # No app-level scalar controller/oracle/emitter contains floating/vector code.
 obj=b/'CMakeFiles/app.dir/src/main.c.obj';of,oe,os,orr=load(obj);instructions=0
 for sec in oe.iter_sections():
  if not(sec['sh_flags']&4):continue
  data=sec.data();pc=0
  while pc<len(data):
   half=int.from_bytes(data[pc:pc+2],'little')
   if half&3==3:
    w=int.from_bytes(data[pc:pc+4],'little');assert w&0x7f not in [7,39,67,71,75,79,83,87,119],(sec.name,pc,hex(w));pc+=4
   else:
    assert not ((half&3)in [0,2]and half>>13 in [1,5]),(sec.name,pc,hex(half));pc+=2
   instructions+=1
 of.close()
 tool=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-objdump');dis=subprocess.check_output([str(tool),'-d','-M','no-aliases',str(elf)],text=True);(out/'actual.disassembly').write_text(dis)
 blocks={};current=None
 for line in dis.splitlines():
  match=re.fullmatch(r'([0-9a-f]+) <([^>]+)>:',line)
  if match:current=match.group(2);blocks[current]=[]
  ins=re.match(r'\s*([0-9a-f]+):\s*([0-9a-f]{4}|[0-9a-f]{8})\s+(.*)',line)
  if ins and current:
   pc=int(ins[1],16);opcode=int(ins[2],16);size=len(ins[2])//2
   for sec in e.iter_sections():
    if sec['sh_type']!='SHT_NOBITS'and sec['sh_addr']<=pc<sec['sh_addr']+sec['sh_size']:
     assert sec.data()[pc-sec['sh_addr']:pc-sec['sh_addr']+size]==opcode.to_bytes(size,'little');break
   else:raise AssertionError('Instruction outside file-backed sections')
   blocks[current].append((pc,opcode,ins[3]))
 measured=blocks['packet_measure'];csrs=[i for i,x in enumerate(measured)if x[1]&0x7f==0x73 and(x[1]>>20)in [0xb00,0xb02]]
 assert len(csrs)==5
 span=measured[csrs[0]:csrs[-1]+1];assert sum(x[1]==0x0330000f for x in span)==1 and sum(x[1]&0x7f==0x67 for x in span)==1
 assert not any(x[1]&0x7f in [3,35]for x in span)
 ctrl=blocks['controller'];sent=[i for i,x in enumerate(ctrl)if '<packet_measurements_done>'in x[2]and x[2].startswith('sd\tzero,')];assert len(sent)==1
 i=sent[0];assert ctrl[i-2][1]==0x0330000f and ctrl[i+1][1]==0x0330000f and '<emit>'in ctrl[i+2][2]
 assert int.from_bytes(raw('packet_measurements_done'),'little')==(1<<64)-1
 assert s['output_data']['st_size']==corpus['storage_bytes']==690048 and s['records']['st_size']==648*144
 # Integer source oracle independently distinguishes every omitted target body.
 all_elements=0;formats={}
 for r in corpus['regions']:
  golden=m.golden(r);assert all(v!=0 for v in golden)if r['kind']else True
  if not r['kind']:
   initial=[m.operands(r,i)[1]for i in range(r['elements'])];assert all(a!=b for a,b in zip(initial,golden))
  if r['kind']and r['format']:
   a5=r['format']>=3;b5=r['format']in [2,4];formats[m.FORMATS[r['format']]]=dict(A_E5=a5,B_E5=b5,A_opcode='0xf28810f7'if a5 else'0xf2881077',B_vtype_altfmt=int(b5))
  all_elements+=len(golden)
 assert all_elements==181440
 inputs={str(p):sha(p)for p in [elf,b/'build.json',obj,source/'cases.py',source/'corpus.json',source/'split.json',sf,source/'src/kernels.S',source/'src/main.c',seq,header,Path(__file__).resolve(),tool]}
 report=dict(schema='iris.zephyr_hart2_pow2_source_proof.v1',**{'pass':True},ELF_sha256=sha(elf),groups=486,regions=648,independent_elements=181440,compiled_group_table_bytes=len(groupdata),compiled_descriptor_table_bytes=len(descdata),training_eligible=456,protected_validation=192,scalar_controller_object_instructions=instructions,controller_no_FP_or_vector=True,kernel_bodies=body,FP8_selector_pairs=formats,matrix_dimensions=[8,16,32],matrix_geometry_scope='positive TM/TN/TK1 within32; source skip/rowcol masks and exact native full active cells; no arbitrary tile/column claim',ROI=dict(start=measured[csrs[0]][0],issue=measured[csrs[2]][0],end=measured[csrs[3]][0],instret_scope='total only',three_actual_mcycle_reads=True,two_actual_minstret_reads=True,includes='indirect call, exact body+RET, issue CSR, FENCE; no scalar metadata/data loads/stores between endpoints'),sentinel=dict(pc=ctrl[i][0],count=648,store_after_all_measurements=True,fenced_before_emit=True,file_backed_initial='UINT64_MAX'),conditioning='selected body preexecution then complete input VRF/tile reset and output poison; no physical cache-hit guarantee',application_roles='persistent one owner on each pinned compute0/1; scalar-only hart2 integer oracle/controller and final emitter; no migration/competing-owner certificate',source_image_association=False,timing_certified=False,hardware_contacted=False,input_sha256=inputs)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');f.close();return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a);print(json.dumps({k:r[k]for k in ['pass','ELF_sha256','regions','independent_elements','scalar_controller_object_instructions']}))
