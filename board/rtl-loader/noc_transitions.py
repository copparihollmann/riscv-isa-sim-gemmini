#!/usr/bin/env python3
"""Source-derived arbiter transitions checked against actual saved RTL frames."""
import argparse,copy,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def rr(valid,mask,width):
    valid&=(1<<width)-1
    choices=valid&~mask
    return (choices&-choices) if choices else (valid&-valid)

def after(mask,selected):return (selected<<1)-1 if selected else mask

def evaluate(t):
    i=t['input'];s=t['state'];o={}
    a=rr(i['waiting_vcs'],s['input_unit_mask'],6)
    o['selected_vc']=a
    o['input_unit_mask_next']=((1<<i['incoming_route_vc'])-1)&63 if i['incoming_route_fire'] else after(s['input_unit_mask'],a)
    g=rr(i['eligible_input_units'],s['single_vc_input_mask'],4)
    o['input_unit_grants']=g
    o['single_vc_input_mask_next']=after(s['single_vc_input_mask'],g)
    b=rr(i['selected_eligible_output_vcs'],s['islip_output_mask'],13)
    o['islip_output_selection']=b
    o['output_vc_grants']=b if g else 0
    o['islip_output_mask_next']=after(s['islip_output_mask'],b) if g else s['islip_output_mask']
    return o

def validate(data):
    for t in data['vectors']:
        if evaluate(t)!=t['expected']:raise ValueError('Arbiter transition mismatch at TB'+str(t['tb']))
    return len(data['vectors'])

def extract(base):
    schema=json.loads((base/'board/rtl-loader/noc_fields.json').read_text());lookup={(x['field'],x['array_index'],x['word_index']):i for i,x in enumerate(schema)};rows=[]
    for l in (base/'build/rtl-loader-diag/vector-memory-h2-9-noc.stderr').read_text().splitlines():
        if l.startswith('RTL_NOC '):
            a=l[8:].split(',');rows.append((int(a[0]),[int(x,16) for x in a[1:]]))
    P='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5__DOT__routers__DOT__';I=P+'input_unit_0_from_4__DOT__';V=P+'vc_allocator__DOT__'
    def get(v,n):return v[lookup[n,None,None]]
    vectors=[]
    for (tb,v),(ntb,n) in zip(rows,rows[1:]):
        if ntb!=tb+2:raise ValueError('Nonconsecutive transition frame')
        waiting=sum(get(v,I+'vcalloc_vals_'+str(k))<<k for k in range(6));eligible=sum(get(v,V+'in_arb_vals_'+str(k))<<k for k in range(4));outeligible=sum(get(v,V+'_in_vc_sel_T_'+str(10+7*k))<<k for k in range(13));grants=sum(get(v,V+'in_alloc_'+str(0 if k<6 else 1 if k<12 else 2)+'_'+str(k if k<6 else k-6 if k<12 else 0))<<k for k in range(13))
        t={'tb':tb,'input':{'waiting_vcs':waiting,'incoming_route_fire':bool(get(v,I+'_route_arbiter_io_out_valid')),'incoming_route_vc':get(v,I+'_route_arbiter_io_out_bits_src_virt_id'),'eligible_input_units':eligible,'selected_eligible_output_vcs':outeligible},'state':{'input_unit_mask':get(v,I+'mask'),'single_vc_input_mask':get(v,V+'mask'),'islip_output_mask':get(v,V+'mask_1')},'expected':{'selected_vc':get(v,I+'vcalloc_sel'),'input_unit_mask_next':get(n,I+'mask'),'input_unit_grants':get(v,V+'in_arb_sel'),'single_vc_input_mask_next':get(n,V+'mask'),'islip_output_selection':get(v,V+'sel'),'output_vc_grants':grants,'islip_output_mask_next':get(n,V+'mask_1')}}
        vectors.append(t)
    data={'schema':'iris.source_noc_arbiter_transitions.v1','node':5,'input_unit':0,'input_virtual_channels':6,'router_input_units':4,'flattened_output_vcs':{'port0_to4':[0,1,2,3,4,5],'port1_to6':[6,7,8,9,10,11],'port2_local_nif3':[12]},'rtl_frame_first_tb':rows[0][0],'rtl_frame_last_tb':rows[-1][0],'vectors':vectors,'scope':'Three exact arbitration stages at the selected router; eligible masks are post routing/occupancy inputs, not a complete NoC model. Actual RTL outputs and next-mask states are golden.','whole_noc_certified':False,'timing_calibrated':False,'hardware_contacted':False}
    validate(data);return data

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path,default=ROOT/'build/rtl-loader-diag/noc-arbiter-transitions.json');a=p.parse_args()
    if a.input:
        data=json.loads(a.input.read_text());print(json.dumps({'pass':True,'transitions':validate(data)}));return
    if a.output.exists():raise ValueError('Refuse to overwrite transition vectors')
    data=extract(ROOT)
    # Each rejection is a meaningful future timing-adapter contract check.
    mutations=[]
    for key in ['selected_vc','input_unit_mask_next','input_unit_grants','output_vc_grants','islip_output_mask_next']:
        bad=copy.deepcopy(data);bad['vectors'][0]['expected'][key]^=1
        try:validate(bad)
        except ValueError:mutations.append(key)
        else:raise ValueError('Invalid transition admitted')
    data['mutation_rejections']=mutations;a.output.write_text(json.dumps(data,indent=2)+'\n');print(json.dumps({'pass':True,'transitions':len(data['vectors']),'mutation_rejections':mutations,'path':str(a.output)}))
if __name__=='__main__':main()
