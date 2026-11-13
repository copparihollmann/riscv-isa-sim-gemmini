#!/usr/bin/env python3
from pathlib import Path
import json,time,sys
root=Path(__file__).resolve().parents[1]
print("Joining independent 25 MHz build; duplicate launch suppressed",flush=True)
while True:
 p=root/"status-25mhz.json"
 if p.exists():
  d=json.loads(p.read_text())
  if d["status"]=="complete":
   if not (root/"results/25mhz/manifest.json").exists():raise SystemExit("25 MHz archive is missing")
   raise SystemExit(0)
  if d["status"]=="failed":raise SystemExit(d.get("exit_code",1) or 1)
  if not (Path("/proc")/str(d["pid"])).exists():raise SystemExit("25 MHz worker is no longer running")
 time.sleep(20)
