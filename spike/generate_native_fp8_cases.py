#!/usr/bin/env python3
"""Independent arbitrary-precision oracle for source-defined native FP8 arithmetic."""
from pathlib import Path
import json,random,hashlib
from generate_fp8_cases import decode8
HERE=Path(__file__).resolve().parent

def ieee(n,q,zero_sign,eb,mb,rm,special=None,sign=0,invalid=False):
    maxexp=(1<<eb)-1;bias=(1<<(eb-1))-1
    if invalid or special=='nan':return (maxexp<<mb)|(1<<(mb-1)),16 if invalid else 0
    if special=='inf':return (sign<<(eb+mb))|(maxexp<<mb),0
    if not n:return zero_sign<<(eb+mb),0
    sign=int(n<0);n=abs(n);e=n.bit_length()-1+q
    outq=max(e-mb,1-bias-mb);drop=outq-q
    if drop>0:
      out,rem=divmod(n,1<<drop);half=1<<(drop-1)
      up=rem>half or (rem==half and out&1) if rm==0 else bool(rem and sign) if rm==2 else bool(rem and not sign) if rm==3 else rem>=half if rm==4 else False
      out+=up
    else:out=n<<-drop;rem=0
    if out and out.bit_length()-1+outq>bias:
      infinity=rm in (0,4) or (rm==2 and sign) or (rm==3 and not sign)
      return (sign<<(eb+mb))|((maxexp<<mb) if infinity else (maxexp<<mb)-1),5
    tiny=not out or out.bit_length()-1+outq<1-bias
    flags=(3 if tiny else 1) if rem else 0
    if not out:return sign<<(eb+mb),flags
    if tiny:return (sign<<(eb+mb))|(out<<(outq-(1-bias-mb))),flags
    width=out.bit_length()-1
    sig=(out>>(width-mb)) if width>mb else out<<(mb-width)
    return (sign<<(eb+mb))|((width+outq+bias)<<mb)|(sig&((1<<mb)-1)),flags

def native(a,b,c,fmt,rm,op,lane):
    sa,ma,ea,ta=decode8(a,fmt);sb,mb,eb,tb=decode8(b,fmt);sc,mc,ec,tc=decode8(c,fmt)
    ps=sa^sb^bool(op&2);cs=sc^bool(op&1)
    signaling=lambda x: fmt and (x&127)==125
    invalid=bool(lane&1) and any(map(signaling,[a,b,c]))
    invalid|=(ta=='inf' and tb=='finite' and mb==0) or (tb=='inf' and ta=='finite' and ma==0)
    invalid|=(ta!='nan' and tb!='nan' and (ta=='inf' or tb=='inf') and tc=='inf' and ps!=cs)
    special='nan' if 'nan' in (ta,tb,tc) else 'inf' if 'inf' in (ta,tb,tc) else None
    n=q=zs=0
    if special is None and not invalid:
      q=min(ea+eb,ec);product=ma*mb
      n=((-1 if ps else 1)*product<<(ea+eb-q))+((-1 if cs else 1)*mc<<(ec-q))
      zs=ps if not product and not mc and ps==cs else rm==2
    sign=ps if ta=='inf' or tb=='inf' else cs
    if fmt:
      bits,flags=ieee(n,q,zs,5,2,rm,special,sign,invalid)
      if bits&124==124 and bits&3:bits=127
      return bits,flags
    x,_=ieee(n,q,zs,4,3,rm,special,sign,invalid);y,_=ieee(n,q,zs,5,3,rm,special,sign,invalid)
    exp=(y>>3)&31;frac=y&7
    if exp>=24 or exp==23:
      if exp>=24 or frac==7:return 127,0
      return (x&128)|120|frac,0
    return x,0

def main():
    rng=random.Random(0x4e465038);rows=[]
    edges=[0,128,1,2,3,7,8,0x38,0x3c,0x77,0x78,0x7b,0x7c,0x7d,0x7e,0x7f,0xfb,0xfc,0xfd,0xff]
    for fmt in range(2):
     for rm in range(5):
      for op in range(4):
       for i in range(512):
        a,b,c=[rng.randrange(256) for _ in range(3)]
        if i<256:a=i;b=edges[i%len(edges)];c=edges[(i//len(edges))%len(edges)]
        lane=i%8;out,flags=native(a,b,c,fmt,rm,op,lane)
        rows.append((a,b,c,fmt,rm,op,lane,out,flags))
    h='// Independent arbitrary-precision source-defined FP8 arithmetic oracle.\nstruct NativeCase { uint8_t a,b,c,fmt,rm,op,lane,out,flags; };\nstatic const NativeCase native_cases[] = {\n'
    h+=''.join('  {'+','.join(str(v) for v in row)+'},\n' for row in rows)+'};\n'
    (HERE/'native_fp8_cases.hpp').write_text(h)
    (HERE/'native-fp8-oracle.json').write_text(json.dumps({'cases':len(rows),'seed':0x4e465038,'header_sha256':hashlib.sha256(h.encode()).hexdigest(),'host_float_used':False,'rtl_executed':False,'source_semantics':'single-round exact fused sum; dual independent IEEE rounds for OFP E4; odd-lane signalingness per recoded same-exp widening'},indent=2)+'\n')
if __name__=='__main__':main()
