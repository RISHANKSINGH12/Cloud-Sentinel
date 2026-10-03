import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

# (fault, service): the four experiments that failed last time
PLAN = [
    ("mem_leak", "checkoutservice"),
    ("net_delay", "paymentservice"),
    ("cpu_hog", "checkoutservice"),
    ("mem_leak", "paymentservice"),
]
PAUSE_S = 90


def now():
    return datetime.now().strftime("%H:%M:%S")


def tunnels_ok():
    ok = True
    for name, url in [("shop (8080)", "http://localhost:8080"),
                      ("prometheus (9090)", "http://localhost:9090/-/ready")]:
        try:
            requests.get(url, timeout=5).raise_for_status()
            print(f"{now()}  tunnel {name}: ok")
        except Exception as e:
            print(f"{now()}  tunnel {name}: DOWN ({e})")
            ok = False
    return ok


if not tunnels_ok():
    print("Fix the tunnel(s) above and run again. Nothing was started.")
    sys.exit(1)

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