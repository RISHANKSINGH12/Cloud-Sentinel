import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (fault, service). cpu_hog on cartservice is already done.
PLAN = [
    ("cpu_hog", "currencyservice"),
    ("mem_leak", "cartservice"),
    ("net_delay", "cartservice"),
    ("cpu_hog", "recommendationservice"),
    ("mem_leak", "recommendationservice"),
]
PAUSE_S = 90


def now():
    return datetime.now().strftime("%H:%M:%S")


results = []
for i, (fault, service) in enumerate(PLAN, 1):
    print(f"\n{now()}  === experiment {i} of {len(PLAN)}: {fault} on {service} ===")
    r = subprocess.run([sys.executable, str(ROOT / "infra" / "run_experiment.py"), fault, service])
    results.append((fault, service, "ok" if r.returncode == 0 else "FAILED"))
    if i < len(PLAN):
        print(f"{now()}  pausing {PAUSE_S}s so the cluster can settle...")
        time.sleep(PAUSE_S)

print(f"\n{now()}  batch finished")
for fault, service, status in results:
    print(f"  {fault:10s} {service:24s} {status}")