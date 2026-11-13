#!/usr/bin/env python3
"""Synthetic parser/binding controls; these are not execution predictions."""
import copy
import json
from pathlib import Path
import tempfile
import replay_zephyr_h2_pow2_prediction_v1 as m


def main():
    corpus,layout,binary,elf,_,_,bindings=m.inputs()
    stop=layout['postmeasurement_stop']
    terminal=[0,648,stop['pc'],int.from_bytes(binary.memory(stop['pc']&~7,8),'little')]
    values=terminal[:];acks=[0,0];first_data=None;first_guard=None;seq=[0,0];prefix=[]
    for r in corpus['regions']:
        h=r['hart'];acks[h]+=1;i=r['region_index'];base=10000+100*i
        words=m.golden(r);raw=b''.join(v.to_bytes(r['element_bytes'],'little') for v in words)
        record=dict(rid=i,gid=r['group'],hart=h,logical=h,pin=h,start=base,issued=base+20,
                    end=base+25,ir0=base+30,ir1=base+60,elements=r['elements'],failed=0,
                    checksum=m.fnv(words),actual_vl=r['elements'] if not r['kind'] else r['shape'],
                    rows=1 if not r['kind'] else r['shape'],
                    cols=r['elements'] if not r['kind'] else r['shape'],guard_ok=1,ack=acks[h])
        values.extend(record[k] for k in m.FIELDS)
        if first_data is None:first_data=len(values)
        values.extend(int.from_bytes(raw[j:j+8],'little') for j in range(0,len(raw),8))
        if first_guard is None:first_guard=len(values)
        values.extend([m.GUARD,m.GUARD])
        for pc,value,global_edge in zip(m.CSR_SITES,[base,base+20,base+25],[base+100,base+120,base+125]):
            seq[h]+=1;word=int.from_bytes(binary.memory(pc,4),'little')
            prefix.append(dict(hart=h,sequence=seq[h],value=value,read_cycle=global_edge,
                               pc=pc,raw=word,csr=word>>20,destination=(word>>7)&31,
                               result_discarded=False,calibration_identity='synthetic-test-only'))
    values+=terminal
    stream=lambda v:':\n'+''.join('0x%016x\n'%x for x in v)
    rows,_=m.decode(stream(values),corpus,layout,binary)
    controls=[]
    def reject(name,fn):
        try:fn()
        except (ValueError,KeyError,AssertionError,TypeError):controls.append(name)
        else:raise AssertionError('Admitted '+name)
    for name,index,changed in [('done-not-complete',0,1),('wrong-count',1,647),
                               ('wrong-stop-PC',2,stop['pc']+2),('changed-code-byte',3,values[3]^1),
                               ('wrong-role',6,2),('wrong-fullword',first_data,values[first_data]^1),
                               ('broken-trailing-guard',first_guard+1,0),
                               ('post-readback-PC-change',len(values)-2,stop['pc']+2)]:
        v=values[:];v[index]=changed;reject(name,lambda v=v:m.decode(stream(v),corpus,layout,binary))
    reject('truncated',lambda:m.decode(stream(values[:-1]),corpus,layout,binary))
    reject('extra-value',lambda:m.decode(stream(values+[1]),corpus,layout,binary))
    reject('malformed-value',lambda:m.decode(stream(values).replace('0x0000000000000000','0x0',1),corpus,layout,binary))
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'prefix.jsonl'
        def qualify(events):
            p.write_text(''.join(json.dumps(x)+'\n' for x in events))
            return m.qualify_prefix(p,copy.deepcopy(rows),elf,m.ROOT/'board/evidence/bootrom.rv64.img')
        assert qualify(prefix)==('synthetic-test-only',1944)
        reject('missing-dynamic-endpoint',lambda:qualify(prefix[:-1]))
        reject('duplicate-endpoint',lambda:qualify(prefix+[prefix[-1]]))
        bad=copy.deepcopy(prefix);bad[0]['hart']=2;reject('cross-hart-join',lambda:qualify(bad))
        bad=copy.deepcopy(prefix);bad[0]['raw']^=128;reject('changed-ELF-opcode',lambda:qualify(bad))
        bad=copy.deepcopy(prefix);bad[0]['value']+=1;reject('changed-RAM-counter-join',lambda:qualify(bad))
    commands=m.commands(layout)
    assert len(commands)==97931 and commands[1]=='until pc 2 80000844'
    # Every data read is exactly an initialized 8-byte record/data/guard/code object.
    allowed={stop['done_address'],stop['count_address'],stop['pc']&~7}
    for x in layout['regions']:
        allowed.update(x['record_address']+8*j for j in range(18))
        allowed.update(x['active_data_address']+j for j in range(0,x['active_bytes'],8))
        allowed.update([x['leading_guard_address'],x['trailing_guard_address']])
    assert all(int(s.split()[1],16) in allowed for s in commands if s.startswith('mem '))
    out=m.ROOT/'build/zephyr-hart2-pow2-prediction-guards-v1';out.mkdir(exist_ok=False)
    report=dict(schema='iris.zephyr_pow2_prediction_controls.v1',**{'pass':True},
                synthetic_parser_only=True,regions=648,elements=181440,dynamic_mcycle_joins=1944,
                minstret_dynamic_joins_invented=False,initialized_only_commands=len(commands),
                refusal_controls=controls,input_sha256=bindings,
                source_sha256={str(Path(__file__).resolve()):m.sha(__file__)},hardware_contacted=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(**{'pass':True},controls=len(controls),report_sha256=m.sha(out/'report.json'))))


if __name__=='__main__':main()
