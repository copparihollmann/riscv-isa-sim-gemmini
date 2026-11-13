#!/usr/bin/env python3
"""Relink immutable whole-Iris objects with a read-only reset-to-RAS witness."""
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = ROOT / 'build/vme-column-preload-reference-v1'
    receipt = json.loads((base / 'build.json').read_text())
    text = (base / 'main.cc').read_text()
    header = Path(next(x[2:] for x in receipt['compile_argv'] if x.startswith('-I') and x.endswith('/model'))) / 'VTestDriver___024root.h'
    declaration = header.read_text()
    used = []

    def field(name):
        if not re.search(r'\b' + re.escape(name) + r'\s*[;\[]', declaration):
            raise ValueError('Missing actual read-only field ' + name)
        used.append(name)
        return 'r->' + name

    prefix = 'TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__'
    observer = '''
#include <deque>
struct RASWholeSnapshot {bool reset=true,need=false,write=false,repair=false,flush=false,call=false,s2valid=false;unsigned head=0,index=0,repairhead=0,retmask=0,nexthead=0;uint64_t pc=0,pendingaddr=0,ras[6]{};bool commit[2]{};uint64_t cpc[2]{};unsigned craw[2]{},chead[2]{};};
static RASWholeSnapshot prior_ras[2];static bool prior_source_clock=false;static uint64_t source_edges=0;static unsigned known_ras[2]{};
struct ActualCommit {uint64_t edge,pc;unsigned raw,head;};static std::deque<ActualCommit> commit_tail[2];
static bool observe_RAS_whole(VTestDriver___024root*r){
 bool clock=r->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i;
 if(!clock){
'''
    for h in range(2):
        tile = prefix + 'tile_prci_domain' + ('' if h == 0 else '_1') + '__DOT__element_reset_domain_shuttle_tile__DOT__'
        f = lambda s: field(tile + 'frontend__DOT__' + s)
        c = lambda s: field(tile + 'core__DOT__' + s)
        t = lambda s: field(tile + s)
        observer += '{auto&x=prior_ras[' + str(h) + '];x.reset=r->TestDriver__DOT__reset||' + t('vector_unit__DOT__reset') + ';'
        observer += 'x.head=' + f('s2_ras_head') + ';x.pc=' + f('s2_vpc') + ';x.s2valid=' + f('s2_valid') + ';x.retmask=' + f('_f2_do_ret_T_2') + ';'
        observer += 'x.flush=' + t('_core_io_imem_redirect_flush') + ';x.call=' + f('_GEN_8') + ';x.nexthead=' + f('ras_next_head') + ';'
        observer += 'x.need=' + f('f2_do_redirect') + '&&x.retmask&&' + f('_GEN_7') + '&&!x.flush&&!' + f('jump_to_reset') + ';'
        observer += 'x.write=' + f('_GEN_9') + ';x.repair=' + t('_core_io_imem_ras_update_valid') + ';x.repairhead=' + t('_core_io_imem_ras_update_bits_head') + ';x.index=x.repair?x.repairhead:' + f('idx_REG') + ';x.pendingaddr=' + f('addr_REG') + ';'
        for j in range(6):
            observer += 'x.ras[' + str(j) + ']=' + f('ras_' + str(j)) + ';'
        for j in range(2):
            k = str(j)
            observer += 'x.commit[' + k + ']=' + c('com_retire_' + k) + ';x.cpc[' + k + ']=' + c('com_uops_reg_' + k + '_bits_pc') + ';x.craw[' + k + ']=' + c('com_uops_reg_' + k + '_bits_inst') + ';x.chead[' + k + ']=' + c('com_uops_reg_' + k + '_bits_ras_head') + ';'
        observer += '}\n'
    observer += ''' }
 bool fire=clock&&!prior_source_clock;prior_source_clock=clock;if(!fire)return false;++source_edges;bool stop=false;
 for(unsigned h=0;h<2;++h){const auto&x=prior_ras[h];if(x.reset){known_ras[h]=0;commit_tail[h].clear();continue;}
 for(unsigned j=0;j<2;++j)if(x.commit[j]){commit_tail[h].push_back({source_edges,x.cpc[j],x.craw[j],x.chead[j]});if(commit_tail[h].size()>64)commit_tail[h].pop_front();}
 unsigned selected=x.head<6?x.head:0;bool unknown=x.need&&!(known_ras[h]&(1u<<selected));
 if(x.need||x.write||x.call)fprintf(stderr,"WHOLE_RAS {\\"hart\\":%u,\\"edge\\":%lu,\\"pc\\":%lu,\\"head\\":%u,\\"known_before\\":%u,\\"required_read\\":%s,\\"unwritten_read\\":%s,\\"write\\":%s,\\"write_index\\":%u,\\"repair\\":%s,\\"repair_head\\":%u,\\"call_activity\\":%s,\\"next_head\\":%u,\\"ret_mask\\":%u,\\"flush\\":%s,\\"concrete_two_state_selected_bits\\":%lu}\\n",h,source_edges,x.pc,x.head,known_ras[h],x.need?"true":"false",unknown?"true":"false",x.write?"true":"false",x.index,x.repair?"true":"false",x.repairhead,x.call?"true":"false",x.nexthead,x.retmask,x.flush?"true":"false",x.ras[selected]);
 if(unknown){fprintf(stderr,"WHOLE_UNWRITTEN_RAS_READ hart=%u edge=%lu pc=%lx head=%u known=%u\\n",h,source_edges,x.pc,x.head,known_ras[h]);for(const auto&c:commit_tail[h])fprintf(stderr,"WHOLE_RAS_COM_TAIL {\\"hart\\":%u,\\"edge\\":%lu,\\"pc\\":%lu,\\"raw\\":%u,\\"ras_head\\":%u}\\n",h,c.edge,c.pc,c.raw,c.head);stop=true;}
 if(x.write&&x.index<6)known_ras[h]|=1u<<x.index;
 }return stop;
}
'''
    text = text.replace('//======================', observer + '\n//======================', 1)
    text = text.replace('        topp->eval();', '        topp->eval();\n        if(observe_RAS_whole(iris_root))break;', 1)
    source = out / 'main.cc'
    source.write_text(text)
    comp = receipt['compile_argv'][:]
    comp[comp.index('-c') + 1] = str(source)
    comp[comp.index('-o') + 1] = str(out / 'main.o')
    comp[comp.index('-MF') + 1] = str(out / 'main.d')
    link = receipt['link_argv'][:]
    link[1] = str(out / 'main.o')
    link[link.index('-o') + 1] = str(out / 'simulator-preload')
    started = time.monotonic()
    for name, argv in (('compile', comp), ('link', link)):
        q = subprocess.run(argv, capture_output=True)
        (out / (name + '.stdout')).write_bytes(q.stdout)
        (out / (name + '.stderr')).write_bytes(q.stderr)
        if q.returncode:
            raise RuntimeError('Host ' + name + ' failed')
    inputs = {str(q): sha(q) for q in (base / 'build.json', base / 'main.cc', source, header, Path(__file__))}
    for name, digest in receipt['input_sha256'].items():
        if sha(name) != digest:
            raise ValueError('Frozen reference input changed ' + name)
        inputs[name] = digest
    for token in link:
        q = Path(token)
        if q.is_file():
            inputs[str(q)] = sha(q)
    r = dict(schema='iris.merlin_RAS_readonly_whole_CPU_reference.v1', status='built',
             compile_argv=comp, link_argv=link, input_sha256=inputs,
             binary_sha256=sha(out / 'simulator-preload'), read_only_fields=sorted(set(used)),
             source_FIR_sha256=receipt['source_fir_sha256'],
             all_target_RTL_objects_unchanged=True, internal_state_driven=False,
             hardware_contacted=False, source_image_association_verified=False,
             full_four_state_definedness_available=False,
             knownness_scope='shadow ledger marks only actual post-reset RAS writes; payload addresses remain source-derived concrete two-state outputs',
             stop_condition='first required pre-edge RAS read whose entry has never been written since reset',
             host_seconds=time.monotonic() - started)
    (out / 'build.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(dict(status='built', binary_sha256=r['binary_sha256'])))


if __name__ == '__main__':
    main()
