"""Capture real container resource counters during long HTTP verification."""
import datetime
import json
from pathlib import Path
import subprocess
import time
import urllib.request
root=Path(__file__).resolve().parents[1]
probe='import json; from pathlib import Path; print(json.dumps({p:Path(p).read_text() for p in ["/sys/fs/cgroup/memory.current","/sys/fs/cgroup/memory.peak","/sys/fs/cgroup/memory.events","/sys/fs/cgroup/cpu.stat"]}))'
with (root/'artifacts/resource-timeline.jsonl').open('a') as f:
 for _ in range(120):
  with urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=10) as r: health=json.load(r)
  counters=json.loads(subprocess.check_output(['container','exec','one-system-model','python','-c',probe],text=True))
  f.write(json.dumps({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'health':health,'counters':counters})+'\n');f.flush()
  if health['completed_requests']>=15 and not health['busy']: break
  time.sleep(20)
