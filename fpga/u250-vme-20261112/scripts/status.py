#!/usr/bin/env python3
from pathlib import Path
import json,datetime,os,sys,fcntl
root=Path(__file__).resolve().parents[1]
data={"updated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"phase":sys.argv[1],"status":sys.argv[2],"pid":int(os.environ.get("BUILD_COORDINATOR_PID",os.getppid())),"frequencies_mhz":[15,25],"cpu_budget":12}
if len(sys.argv)>3:data["exit_code"]=int(sys.argv[3])
with (root/"status-write.lock").open("a") as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 with (root/"status-history.jsonl").open("a") as history:history.write(json.dumps(data)+"\n")
 previous=json.loads((root/"status.json").read_text()) if (root/"status.json").exists() else {}
 if not (data["phase"]=="awaiting-setup" and data["status"]=="failed" and previous.get("status")=="failed"):
  if (root/"provenance/parallel-build-plan.json").exists():
   runs=previous.get("frequency_runs",{})
   if "15" in data["phase"]:runs["15"]={"phase":data["phase"],"status":data["status"],"pid":data["pid"],"cpu_affinity":"0-11","jobs":12}
   if data["phase"]=="all-builds" and data["status"]=="complete":runs["15"]={"status":"complete","cpu_affinity":"0-11","jobs":12}
   if (root/"status-25mhz.json").exists():runs["25"]=json.loads((root/"status-25mhz.json").read_text())
   data["frequency_runs"]=runs;data["execution_mode"]="parallel"
  tmp=root/("status.json.tmp."+str(os.getpid()));tmp.write_text(json.dumps(data,indent=2)+"\n");os.replace(tmp,root/"status.json")
print("BUILD_STATUS",data["phase"],data["status"],flush=True)
