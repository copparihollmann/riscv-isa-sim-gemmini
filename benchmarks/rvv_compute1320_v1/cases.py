"""Source geometry only. No timing labels or cycle lookup."""
import struct
KINDS=('integer','fp','load','store','load_use','load_independent','store_compute','rowmove','matrix_int','matrix_fp8')
def generate():
 out=[]
 def add(kind,sew,lmul,mode,n,bytes_,vl,streams,harts,reserved):
  for t in range(3):
   for h in harts:
    parent=f'rvv.identify.{kind}.e{sew}.m{lmul}.mode{mode}.n{n}.b{bytes_}'
    out.append(dict(case_id=parent+f'.hart{h}.trial{t}',parent_case_id=parent+f'.hart{h}',semantic_parent_case_id=parent,kind=kind,kind_id=KINDS.index(kind),sew=sew,lmul=lmul,mode=mode,n=n,bytes=bytes_,vl=vl,streams=streams,hart=h,trial_id=t,internal_split='reserved_holdout'if reserved else'train'))
 for kind,sews in [('integer',(8,16,32,64)),('fp',(16,32,64))]:
  for sew in sews:
   for lm in(1,2,4,8):
    for mode in range(3):
     for n in(16,64):add(kind,sew,lm,mode,n,32*lm,256*lm//sew,1 if mode==0 else 2,range(3),lm==4)
 for kind in('load','store'):
  for b in(16,32,64,128,256):
   for n in(16,64):add(kind,32,max(1,b//32),0,n,b,b//4,1,range(3),b==64)
 for kind in('load_use','load_independent','store_compute'):
  for b in(32,128):
   for n in(16,64):add(kind,32,b//32,0,n,b,b//4,2,range(3),b==128)
 for n in(1,4,16,64):add('rowmove',32,4,0,n,128,32,1,range(2),n==16)
 for kind in ('matrix_int','matrix_fp8'):
  for edge in (16,32):
   for tk in (2,4):
    for n in (16,64):add(kind,32,edge//8,tk,n,edge*4,edge,1,range(2),edge==16 and tk==4)
 out=[c for c in out if not(c['hart']==2 and c['kind']in('load','store')and c['bytes']==256)]
 out=[c for c in out if c['hart']<2]
 out.sort(key=lambda c:c['hart'])
 assert len(out)==1320
 return out
def words(c):
 n,vl,kind,mode=c['n'],c['vl'],c['kind'],c['mode'];out=[]
 if kind in ('matrix_int','matrix_fp8'):
  value=n*mode*(6 if kind=='matrix_int' else 1)
  if kind=='matrix_fp8':value=int.from_bytes(struct.pack('<f',float(value)),'little')
  return [value if row<vl and col<vl else 0 for row in range(32) for col in range(32)]
 for stream in range(c['streams']):
  for i in range(vl):
   if kind in('integer','fp'):v=n+(1 if mode==2 and stream else 0)
   elif kind=='rowmove':v=6
   elif kind=='store':v=3
   elif kind=='load':v=i+3
   elif kind=='load_use':v=i+3+stream
   elif kind=='load_independent':v=i+3 if stream==0 else n
   else:v=3 if stream==0 else n
   if kind=='fp':v=int.from_bytes(struct.pack({16:'<e',32:'<f',64:'<d'}[c['sew']],float(v)),'little')
   out.append(v)
 return out
def golden(c):
 h=14695981039346656037
 for word in words(c):h=((h^word)*1099511628211)&((1<<64)-1)
 return h
