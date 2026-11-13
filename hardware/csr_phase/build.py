#!/usr/bin/env python3
"""Add a read-only CSR observer to the existing compiled standalone RTL model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    loader=ROOT/'build/rtl-loader-diag/loader-build.json';base=json.loads(loader.read_text())
    for path,digest in base['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('changed compiled RTL input '+path)
    model=ROOT/'build/rtl-verilator/model';header=model/'VTestDriver___024root.h';text=header.read_text()
    prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__'
    snapshots=[];field_evidence=[]
    for hart in range(3):
        tile='tile_prci_domain'+('' if hart==0 else '_'+str(hart))
        tile+='__DOT__element_reset_domain_'+('shuttle_tile' if hart<2 else 'rockettile')+'__DOT__core__DOT__'
        pre=prefix+tile
        module='CSRFile' if hart<2 else 'CSRFile_2'
        sv=ROOT/'build/rtl-verilator/gen-collateral'/(module+'.sv')
        data_name=re.search(r'assign io_rw_rdata = (\w+)',sv.read_text())[1]
        def field(name):
            full=pre+name
            if not re.search(r'\b'+re.escape(full)+r'\s*;',text):raise ValueError('missing observed RTL field '+full)
            field_evidence.append({'hart':hart,'name':name,'cpp_member':full})
            return 'iris_root->'+full
        def counter(index):
            small='csr__DOT__small_'+str(index);large='csr__DOT__large_'+str(index)
            width=re.search(r'/\*(\d+):0\*/\s*'+re.escape(pre+small)+r'\s*;',text)
            if not width:raise ValueError('unknown native counter low width')
            return '('+field(large)+' << '+str(int(width[1])+1)+') | '+field(small)
        fields={'valid':field('com_uops_reg_0_valid' if hart<2 else 'wb_valid'),
                'pc':field('com_uops_reg_0_bits_pc' if hart<2 else 'wb_reg_pc'),
                'raw':field('com_uops_reg_0_bits_inst' if hart<2 else 'wb_reg_inst'),
                'cmd':field('__Vcellinp__csr__io_rw_cmd'),
                'retire':field('csr_io_retire' if hart<2 else '__Vcellinp__csr__io_retire'),
                'inhibit':field('csr__DOT__reg_mcountinhibit'),
                'ir':counter(0),'mc':counter(1),
                'rdata':field('csr__DOT__'+data_name)}
        if hart<2:
            fields.update({'wb_valid':field('wb_uops_reg_0_valid'),'wb_raw':field('wb_uops_reg_0_bits_inst'),
                           'wb_data':field('wb_uops_reg_0_bits_wdata_bits'),
                           'wb_data_valid':field('wb_uops_reg_0_bits_wdata_valid'),
                           'wb_wxd':field('wb_uops_reg_0_bits_ctrl_wxd')})
            for reg in (11,29,30,31):fields['x'+str(reg)]=field('iregfile_'+str(reg))
        snapshots.append(fields)
    members=list(dict.fromkeys(name for fields in snapshots for name in fields))
    code='#include <array>\n#include <cstdio>\n#include <cstdint>\n'
    code+='struct IrisCsrPhase {'+''.join('uint64_t '+name+'=0;' for name in members)+'};\n'
    code+='static std::array<IrisCsrPhase,3> iris_phase_snapshot(){std::array<IrisCsrPhase,3> a{};\n'
    for hart,fields in enumerate(snapshots):
        code+=''.join('a['+str(hart)+'].'+name+'='+value+';\n' for name,value in fields.items())
    code+='return a;}\n'
    code+='static bool iris_phase_interesting(const IrisCsrPhase& p){ auto csr=p.raw>>20;return p.valid && (p.raw&127)==0x73 && (csr==0xb00 || csr==0xb02 || csr==0xc00 || csr==0xc02) && p.cmd; }\n'
    code+='static void iris_phase_emit(const IrisCsrPhase& p,unsigned hart){fprintf(stderr,"{");\n'
    for i,name in enumerate(members):
        label=('' if i==0 else ',')+'\\"'+name+'\\":'
        missing=[h for h,fields in enumerate(snapshots) if name not in fields]
        if missing:
            code+='if('+ ' || '.join('hart=='+str(h) for h in missing)+')fprintf(stderr,"'+label+'null");else '
        code+='fprintf(stderr,"'+label+'%llu",(unsigned long long)p.'+name+');\n'
    code+='fprintf(stderr,"}");}\n'
    code+='static void iris_phase_after(const std::array<IrisCsrPhase,3>& before,uint64_t time){ static unsigned tail[3]{};static uint64_t edges[3]{}; auto after=iris_phase_snapshot();\n'
    code+='for(unsigned h=0;h<3;++h){bool changed=before[h].mc!=after[h].mc || before[h].ir!=after[h].ir;if(!changed)continue;++edges[h];bool selected=iris_phase_interesting(before[h]) || iris_phase_interesting(after[h]);if(selected)tail[h]=3;if(!tail[h])continue;--tail[h];\n'
    code+='fprintf(stderr,"CSR_PHASE {\\"hart\\":%u,\\"time_ps\\":%llu,\\"counter_update_edge\\":%llu,\\"before\\":",h,(unsigned long long)time,(unsigned long long)edges[h]);iris_phase_emit(before[h],h);fprintf(stderr,",\\"after\\":");iris_phase_emit(after[h],h);fprintf(stderr,"}\\n");}}\n'
    inc=out/'phase_fields.inc';inc.write_text(code)
    source=ROOT/'board/rtl-loader/main.cc';main=source.read_text()
    main=main.replace('static uint64_t iris_preloaded;','static uint64_t iris_preloaded;\n#include "phase_fields.inc"')
    marker='        topp->eval();'
    if main.count(marker)!=1:raise ValueError('unexpected base simulation loop')
    main=main.replace(marker,'        const auto phase_before=iris_phase_snapshot();\n'+marker+'\n        iris_phase_after(phase_before,contextp->time());')
    local=out/'main.cc';local.write_text(main);obj=out/'main.o';binary=out/'simulator-csr-phase'
    compile=list(base['commands'][0]);compile[compile.index(str(source))]=str(local);compile[-1]=str(obj)
    link=list(base['commands'][-1]);link[1]=str(obj);link[-1]=str(binary)
    commands=[compile,link]
    for i,cmd in enumerate(commands):
        result=subprocess.run(cmd,cwd=model,capture_output=True,text=True);(out/('build-'+str(i)+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError('observer build failed; see logs')
    inputs={**base['input_sha256'],str(loader):sha(loader),str(Path(__file__).resolve()):sha(Path(__file__)),
            str(inc):sha(inc),str(local):sha(local)}
    for module in ('CSRFile','CSRFile_2'):
        path=ROOT/'build/rtl-verilator/gen-collateral'/(module+'.sv');inputs[str(path)]=sha(path)
    receipt={'schema':'iris.csr_phase_observer_build.v1','binary':str(binary),'binary_sha256':sha(binary),
             'argv':commands,'base_loader_manifest_sha256':sha(loader),'input_sha256':inputs,'observed_fields':field_evidence,
             'rtl_design_changed':False,'hardware_contacted':False,'source_read_only_observer':True,
             'sampling':'before/after eval pairs when native counter state changes; edge ordinal is not asserted to be an absolute target clock',
             'limitations':['Two-state saved-Iris native-memory RTL reference, not attested Ethan image.',
                            'Rocket RF observation fields are absent; only Shuttle RF and all-hart CSR signals are sampled.',
                            'No counter read-value or model-phase correction is applied.']}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(binary)


if __name__=='__main__':main()
