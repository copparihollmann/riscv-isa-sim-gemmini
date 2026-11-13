"""Prospective source-only identities; no timing labels or parameter fitting."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
VALUES=[1,2,3,4,5,6,7,8,10,12,14,16,20,24,28,32]
FORMATS=['int8.u_u','fp8.e4m3_e4m3','fp8.e4m3_e5m2','fp8.e5m2_e4m3','fp8.e5m2_e5m2']
def generate():
 groups=[];regions=[];offset=0
 for kind in [0,1]:
  geometries=[(s,l,0,0) for s in [8,16,32] for l in [1,2,4,8]] if kind==0 else [(8,1,m,f) for m in [8,16,32] for f in range(5)]
  for sew,lmul,shape,fmt in geometries:
   for n in [17,65]:
    for mask in [1,2,3]:
     for trial in range(3):
      gid=len(groups);prefix=('rvv.e%d.m%d'%(sew,lmul)) if kind==0 else ('vme.%s.m%d'%(FORMATS[fmt],shape));parent='zephyr.pow2.v1.%s.n%d.mask%d'%(prefix,n,mask);cid=parent+'.trial%d'%trial
      g=dict(group=gid,case_id=cid,parent_case_id=parent,kind=kind,sew=sew,lmul=lmul,shape=shape,format=fmt,operations=n,hart_mask=mask,trial=trial,first_region=len(regions))
      groups.append(g)
      for h in [0,1]:
       if mask&(1<<h):
        count=32*lmul*8//sew if kind==0 else shape*shape;width=sew//8 if kind==0 else 4;size=count*width
        reserved=(lmul==4 if kind==0 else shape==16)
        offset=((offset+8+127)//128)*128-8
        r=dict(g,region_index=len(regions),hart=h,logical_cpu=h,pin=h,role='rvv.compute' if kind==0 else 'vme.compute',elements=count,element_bytes=width,bytes=size,offset=offset,data_offset=offset+8,split='protected_validation' if reserved else 'training_eligible')
        regions.append(r);offset+=size+16
 assert (len(groups),len(regions),sum(r['elements']for r in regions),sum(r['split']=='protected_validation'for r in regions))==(486,648,181440,192)
 return dict(schema='iris.zephyr_hart2_pow2_corpus.v1',groups=groups,regions=regions,required_regions=648,groups_count=486,elements=181440,storage_bytes=offset,trials=3,training_eligible=456,protected_validation=192,calibration_authorized=False,hardware_reference_required=True)
def signed_value(i):return VALUES[i&15]*(-1 if i&16 else 1)
def fpbits(n):
 if not n:return 0
 sign=int(n<0);n=abs(n);e=n.bit_length()-1
 assert e<=23
 return(sign<<31)|((e+127)<<23)|((n-(1<<e))<<(23-e))
def fp8bits(n,e5):
 sign=int(n<0);n=abs(n);e=n.bit_length()-1;m=2 if e5 else 3;bias=15 if e5 else 7
 assert e<=5 and ((n-(1<<e))<<m)%(1<<e)==0
 return(sign<<7)|((e+bias)<<m)|(((n-(1<<e))<<m)>>e)
def operands(r,i):
 h=r['hart'];t=r['trial']
 if not r['kind']:return 1+2*((i+t+h)&1),3+(i*5+7*t+11*h)%31
 row,col=divmod(i,r['shape'])
 if r['format']==0:return 1+(row+t+h)%3,1+(col+2*t+h)%4
 return signed_value(row+3*t+5*h),signed_value(col+7*t+3*h)
def golden(r):
 out=[]
 for i in range(r['elements']):
  a,b=operands(r,i);v=b+r['operations']*a if not r['kind'] else r['operations']*a*b
  out.append((v&((1<<r['sew'])-1))if not r['kind']else(fpbits(v)if r['format']else v))
 return out
def checksum(values):
 s=14695981039346656037
 for v in values:s=((s^v)*1099511628211)&((1<<64)-1)
 return s
def write():
 base=Path(__file__).resolve().parent;c=generate();(base/'corpus.json').write_text(json.dumps(c,indent=2)+'\n')
 split=dict(schema='iris.zephyr_hart2_pow2_split.v1',frozen_before_hardware=True,label_access=False,calibration_authorized=False,grouping='all masks, harts, operations and trials for RVV LMUL4 or matrix shape16 reserved',training_eligible=[r['region_index']for r in c['regions']if r['split']=='training_eligible'],protected_validation=[r['region_index']for r in c['regions']if r['split']=='protected_validation'])
 (base/'split.json').write_text(json.dumps(split,indent=2)+'\n')
 s=['/* Generated from source-only cases.py; frozen before timing labels. */','static const group_t groups[486]={']
 for g in c['groups']:s.append('{%d,%d,%d,%d,%d,%d,%d,%d,%d},'%(g['kind'],g['sew'],g['lmul'],g['shape'],g['format'],g['operations'],g['hart_mask'],g['trial'],g['first_region']))
 s+=['};','static const descriptor_t descriptors[648]={']
 for r in c['regions']:s.append('{%d,%d,%d,%d,%d,%d},'%(r['group'],r['hart'],r['offset'],r['bytes'],r['elements'],r['element_bytes']))
 s+=['};','static const char*const case_ids[486]={']+['"'+g['case_id']+'",' for g in c['groups']]+['};']
 (base/'src/cases.inc').write_text('\n'.join(s)+'\n')
 return c
if __name__=='__main__':
 c=write();print(json.dumps({k:c[k]for k in ['required_regions','groups_count','elements','storage_bytes','training_eligible','protected_validation']}))
