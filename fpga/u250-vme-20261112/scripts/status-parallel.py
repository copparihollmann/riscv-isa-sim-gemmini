#!/usr/bin/env python3
from pathlib import Path
import os,sys,json,datetime,fcntl
root=Path(__file__).resolve().parents[1]
data={"frequency_mhz":25,"phase":sys.argv[1],"status":sys.argv[2],"pid":int(os.environ.get("BUILD_COORDINATOR_PID",os.getppid())),"cpu_affinity":"12-23","jobs":12,"updated_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
if len(sys.argv)>3:data["exit_code"]=int(sys.argv[3])
with (root/"status-write.lock").open("a") as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 temp=root/"status-25mhz.tmp";temp.write_text(json.dumps(data,indent=2)+"\n");os.replace(temp,root/"status-25mhz.json")
 if (root/"status.json").exists():
  overall=json.loads((root/"status.json").read_text());runs=overall.setdefault("frequency_runs",{})
  if "15" not in runs:runs["15"]={"phase":overall["phase"],"status":overall["status"],"pid":overall["pid"],"cpu_affinity":"0-11","jobs":12}
  runs["25"]=data;overall["execution_mode"]="parallel";temp=root/"status-parallel.tmp";temp.write_text(json.dumps(overall,indent=2)+"\n");os.replace(temp,root/"status.json")
print("25MHZ_STATUS",data["phase"],data["status"],flush=True)
