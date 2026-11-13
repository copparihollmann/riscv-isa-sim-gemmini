#!/usr/bin/env python3
"""Read-only RPQ packed-command lookup; standalone and archived image differ."""
import argparse,hashlib,json,re
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh audit required')
 standalone=R/'build/rtl-verilator/gen-collateral/Queue16_ShuttleMSHRReq.sv';combined=R/'build/fased-service-source-v2/FireSim-generated.sv';mshr=R/'build/rtl-verilator/gen-collateral/ShuttleDCacheMSHR.sv';cache=R/'third_party/shuttle/src/main/scala/dmem/DCache.scala';host=R/'build/shuttle-memory-parent-sdk-v1/cache/host-single-thread.cpp';s=standalone.read_text();c=combined.read_text();assert sha(combined)=='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64';m=re.search(r'^module Queue16_ShuttleMSHRReq\b',c,re.M);end=c.index('endmodule',m.end());body=c[m.start():end]
 assert re.search(r'io_deq_bits_cmd\s*=\s*_ram_ext_R0_data\[51:47\]',s)
 assert re.search(r'io_deq_bits_cmd\s*=\s*ram_flattened_io_deq_bits_MPORT_data\[112:108\]',body)
 assert 'reg [159:0] ram_flattened [0:15]'in body and 'deq_ptr_value <= 4\'h0'in body
 assert 'Queue16_ShuttleMSHRReq rpq ('in mshr.read_text()
 def excerpts(text,patterns,base_line=1):return [{'line':base_line+n,'text':line}for n,line in enumerate(text.splitlines())if any(x in line for x in patterns)]
 result={'schema':'iris.Shuttle_RPQ_command_bit_layout.v1','status':'source_layouts_proved_distinct','standalone':{'source':str(standalone),'sha256':sha(standalone),'ram':'rpq.ram_ext','module':'ram_16x124','depth':16,'width':124,'command_bits':[51,47],'evidence':excerpts(s,['ram_16x124','W0_data','io_deq_bits_cmd ='])},'archived_image_RTL':{'source':str(combined),'sha256':sha(combined),'module':'Queue16_ShuttleMSHRReq','memory':'rpq.ram_flattened','depth':16,'width':160,'command_bits':[112,108],'cmd_bit0_physical_packed_bit':108,'module_source_start_line':c[:m.start()].count('\n')+1,'evidence':excerpts(body,['reg [159:0] ram_flattened','_GEN_30 =','_GEN_31 =','io_deq_bits_cmd =','ram_flattened_MPORT_data =','deq_ptr_value <='],c[:m.start()].count('\n')+1)},'offending_path_relative_to_DigitalTop':['tile_prci_domain.element_reset_domain_shuttle_tile.dcache.mshrs.mshrs_3.rpq','tile_prci_domain_1.element_reset_domain_shuttle_tile.dcache.mshrs.mshrs_3.rpq'],'invalid_head_after_source_reset':{'queue_index':3,'deq_row':0,'RAM_reset_defined':False,'no_admitted_FPGA_INIT_value':True},'native_strict_guard_source':str(host),'native_strict_guard_sha256':sha(host),'source_control':excerpts(cache.read_text(),['when (isWrite(mshrs.io.replay.bits.cmd) && io.req.fire && isWrite(io.req.bits.cmd))']),'input_sha256':{str(x):sha(x)for x in [Path(__file__),standalone,combined,mshr,cache,host]},'implemented_or_synthesized_primitive_INIT_checked':False,'loaded_image_association_verified':False,'hardware_contacted':False}
 out.mkdir();(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
