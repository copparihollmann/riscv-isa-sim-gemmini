import sys,json,re,gzip,hashlib
from pathlib import Path
R=Path('/scratch/copparihollmann/iris-model');sys.path.insert(0,str(R))
from iris_model.saturn_capture import layout_from_documents,verified_capture
physical={k:json.load(open(R/'build/saturn-timing-native-v1'/k/'ports.json'))for k in('compute','rocket')};activity=json.load(open(R/'build/saturn-timing-activity-schema-v1/schema.json'));layout=layout_from_documents(physical,activity)
path=R/'build/saturn-timing-activity-capture-v1/vme/activity.bin.gz';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();schema=layout.profiles['compute'].fields
queue_names=[n for n in schema if re.fullmatch(r'vu\.(vdq|vlissq\.q|vsissq\.q|vpissq\.q|vxissq_int\.q|vxissq_fp\.q)\.valids_\d+',n)]
seen=[False]*3;counts=[0]*3;w=[];windows=[]
with verified_capture(path,layout,sha(path))as frames:
 for f in frames:
  if f.hart==2:continue
  reset=f.raw_value('input.reset')
  if reset:seen[f.hart]=True;continue
  if not seen[f.hart]:continue
  hist=f.raw_value('vu.vos.fp8_hist_valid');full=f.raw_value('output.io_backend_busy');trap=f.raw_value('output.io_trap_check_busy');q=sum(f.raw_value(n)for n in queue_names)
  if hist and not full and not trap and not q:
   row=dict(hart=f.hart,edge=f.source_edge,tb=f.tb,full_backend_busy=full,trap_check_busy=trap,all_input_issue_queues_occupancy=q,seq_busy=f.raw_value('vu.vos.io_busy'),fp8_history=hist,TLreader_busy=f.raw_value('tl_if.reader.io_busy'),TLwriter_busy=f.raw_value('tl_if.writer.io_busy'),VU_busy=f.raw_value('vu.io_busy'),EX_vector_valid=f.raw_value('input.io_ex_valid'))
   counts[f.hart]+=1
   if len(w)<24:w.append(row)
print(json.dumps(dict(counts=counts,first_witnesses=w,queue_fields=queue_names,capture_sha256=sha(path)),indent=2))
