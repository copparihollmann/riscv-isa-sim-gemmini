#!/usr/bin/env python3
"""Typed SDK: replay raw payload proof, receipt joins and refusal/lifecycle tests."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    a=argparse.ArgumentParser(__doc__);a.add_argument('--sdk-build',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);sdkbuild=args.sdk_build.resolve();sdk=sdkbuild/'sdk';started=time.monotonic();rows=[]
    build=json.loads((sdkbuild/'build.json').read_text());assert build['pass']is True
    raw=ROOT/'build/saturn-storefront-component-v1';ports=json.loads((raw/'extraction.json').read_text())['ports'];inputs=[p for p in ports if p['direction']=='input'and p['name']!='clock'];outputs=[p for p in ports if p['direction']=='output']
    lines=['#pragma once','#include "saturn_storefront_v1.hpp"','#include "verilated.h"','#include <map>','#include <tuple>','#include <stdexcept>','namespace T=iris::saturn_storefront;','class TypedFacade {','std::unique_ptr<T::Model>model; std::array<std::uint64_t,32>generation{};std::optional<T::Owner>load,store;std::uint64_t tick=0,command=0;bool prior_clock=false;','struct Chain {T::Owner owner;unsigned phase;};std::map<std::pair<unsigned,std::uint64_t>,Chain>chains;','public:','inline static unsigned instances=0;inline static std::uint64_t receipt_count=0;','unsigned hart;']
    for p in ports:
        if p['width']<=64:lines.append('std::uint64_t '+p['name']+'=0;')
        else:lines.append('std::array<std::uint32_t,'+str((p['width']+31)//32)+'>'+p['name']+'{};')
    lines+=['TypedFacade(VerilatedContext*c):hart(instances++%2){model=std::make_unique<T::Model>(hart,c->randSeed(),std::vector<std::string>{},T::Calendar{2,0},std::vector<T::Domain>{{0x80010000,0x30000}});if(Verilated::threadContextp()!=c)throw std::runtime_error("typed ctor foreign context");}',
      '~TypedFacade(){auto*before=Verilated::threadContextp();model.reset();if(Verilated::threadContextp()!=before)std::terminate();}',
      'void eval(){auto*foreign=Verilated::threadContextp();std::vector<T::Input>in;for(auto f:model->input_fields())in.push_back(T::concrete(f.width));']
    for n,p in enumerate(inputs):
        if p['width']<=64:lines.append(f'in[{n}].value.limbs[0]={p["name"]};')
        else:
            for w in range((p['width']+31)//32):lines.append(f'in[{n}].value.limbs[{w//2}]|=std::uint64_t({p["name"]}[{w}])<<{32*(w%2)};')
    lines+=['auto metadata=[&](bool is_load){auto&owner=is_load?load:store;const bool valid=is_load?io_vec_load_req_valid:io_vec_store_req_valid;const unsigned tag=is_load?io_vec_load_req_bits_tag:io_vec_store_req_bits_tag;const unsigned source=tag+(is_load?16:0);if(!valid){owner.reset();return;}if(!owner||owner->tag!=tag){owner=T::Owner{hart,tag,model->reset_epoch(),++command,++generation[source],0x80001000+4*command,is_load?0x02056007u:0x02056027u};}};metadata(false);metadata(true);',
      'model->evaluate_control(in,load,store);auto out=model->sample();']
    for n,p in enumerate(outputs):
        if p['width']<=64:lines.append(f'{p["name"]}=out.words[{n}].limbs[0];')
        else:
            for w in range((p['width']+31)//32):lines.append(f'{p["name"]}[{w}]=std::uint32_t(out.words[{n}].limbs[{w//2}]>>{32*(w%2)});')
    lines+=['if(clock&&!prior_clock){model->prepare(tick);model->commit();for(const auto&e:model->last_receipts()){const auto key=std::make_pair(e.source,e.owner.generation);const auto phase=unsigned(e.phase);if(e.master_tick!=tick||e.source_edge+1!=model->committed_source_edges()||e.owner.hart!=hart)throw std::runtime_error("typed receipt clock/hart");if(e.phase==T::Phase::VMURequest){if(chains.contains(key))throw std::runtime_error("duplicate typed owner sequence");chains[key]={e.owner,0};if(e.load)load.reset();else store.reset();}else{auto i=chains.find(key);if(i==chains.end()||i->second.owner!=e.owner||i->second.phase+1!=phase)throw std::runtime_error("typed receipt immutable owner/phase join");i->second.phase=phase;if(e.phase==T::Phase::VMUResponse)chains.erase(i);}++receipt_count;}tick+=2;}prior_clock=clock;if(Verilated::threadContextp()!=foreign)throw std::runtime_error("typed phase foreign context");}', '};']
    facade=out/'saturn_storefront_test_facade.hpp';facade.write_text('\n'.join(lines)+'\n')
    original=ROOT/'timing/saturn_storefront_payload_check_v2.cpp';text=original.read_text().replace('#include "VComputeStorefront.h"','#include "saturn_storefront_test_facade.hpp"').replace('VComputeStorefront p(&context);','TypedFacade p(&context);')
    needle='std::cout<<"{\\"pass\\":true,\\"checks\\":"<<checks'
    assert text.count(needle)==1
    text=text.replace(needle,'std::cout<<"{\\"pass\\":true,\\"typed_receipts\\":"<<TypedFacade::receipt_count<<",\\"checks\\":"<<checks')
    positive=out/'payload-through-typed.cpp';positive.write_text(text)
    bound=[Path(__file__).resolve(),original,ROOT/'timing/saturn_storefront_typed_guards_v1.cpp',sdk/'saturn_storefront_v1.hpp',sdk/'libiris_saturn_storefront.a',sdkbuild/'build.json',raw/'extraction.json'];initial={str(p):sha(p)for p in bound}
    def run(name,argv,timeout=120):
        with(out/(name+'.stdout')).open('wb')as so,(out/(name+'.stderr')).open('wb')as se:
            proc=subprocess.Popen(list(map(str,argv)),stdout=so,stderr=se,start_new_session=True)
            try:rc=proc.wait(timeout=timeout);timed=False
            except subprocess.TimeoutExpired:
                timed=True
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:rc=proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    rc=proc.wait()
        rows.append(dict(name=name,argv=list(map(str,argv)),exit_status=rc,timed_out=timed));return rc==0 and not timed
    checks=[];passed=True
    for name,source in [('payload',positive),('guards',ROOT/'timing/saturn_storefront_typed_guards_v1.cpp')]:
        exe=out/name;cmd=['/usr/bin/g++','-O2','-std=c++20','-I'+str(sdk),'-I'+str(out),'-isystem','/scratch/eygao/iris-cy/.conda-env/share/verilator/include',source,sdk/'libiris_saturn_storefront.a','-pthread','-latomic','-o',exe]
        ok=run(name+'-compile',cmd)
        if ok:ok=run(name,[exe])
        checks.append(dict(name=name,**{'pass':ok},result=json.loads((out/(name+'.stdout')).read_text())if ok else None));passed &= ok
    unchanged=all(sha(p)==digest for p,digest in initial.items());passed &= unchanged
    report=dict(schema='iris.compute_Saturn_storefront_typed_check.v2',**{'pass':bool(passed)},checks=checks,commands=rows,input_sha256=initial,inputs_unchanged=unchanged,host_seconds=time.monotonic()-started,
      same_raw_source_payload_oracle_replayed_through_typed=True,public_receipts_real_source_phase_only=True,native_or_System_qualified=False,hardware_contacted=False,protected_performance_labels_consumed=False)
    report['generated_test_inputs_sha256']={str(p):sha(p)for p in [facade,positive]};report['output_sha256']={str(p):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=passed,report_sha256=sha(out/'report.json'))));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
