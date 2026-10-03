import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INFRA = ROOT / "infra"

FAULTS = {
    "cpu_hog": INFRA / "inject_cpu.py",
    "mem_leak": INFRA / "inject_memleak.py",
    "net_delay": INFRA / "inject_delay.py",
}

BASELINE_S = 60    # healthy stretch before the fault
FAULT_S = 180      # how long the fault runs
RECOVERY_S = 120   # healthy stretch after the fault
SLACK_S = 40       # extra time for the injector to start and clean up


def now():
    return datetime.now().strftime("%H:%M:%S")


def check_tunnels():
    try:
        requests.get("http://localhost:9090/-/ready", timeout=5).raise_for_status()
        requests.get("http://localhost:8080/", timeout=5).raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"STOP: a tunnel is not working ({e}). Restart the port-forward terminals.")


def shop_latency():
    start = time.time()
    try:
        requests.get("http://localhost:8080/", timeout=5)
    except requests.RequestException:
        return 5.0
    return time.time() - start


def has_leftover_container(service):
    out = subprocess.run(
        ["kubectl", "get", "pod", "-l", f"app={service}", "-o",
         "jsonpath={.items[0].spec.ephemeralContainers[*].name}"],
        capture_output=True, text=True).stdout.strip()
    return bool(out)


def check_healthy(service):
    for attempt in range(2):
        check_tunnels()
        leftover = has_leftover_container(service)
        times = []
        for _ in range(6):
            times.append(shop_latency())
            time.sleep(1)
        median = statistics.median(times[1:])  # skip the first, it is often slow
        if not leftover and median < 0.2:
            print(f"{now()}  shop is healthy (median answer time {median:.3f}s)")
            return
        print(f"{now()}  not healthy: leftover fault container={leftover}, "
              f"median answer time={median:.3f}s")
        if attempt == 0:
            print("replacing the pod and checking again...")
            subprocess.run(["kubectl", "delete", "pod", "-l", f"app={service}"],
                           capture_output=True)
            time.sleep(45)
    sys.exit("STOP: the shop is still not healthy. Nothing was recorded.")


def run(fault, service, delay_ms=300):
    n = 1
    while (DATA / f"data_{fault}_{service}_{n}.csv").exists():
        n += 1
    label = f"{fault}_{service}_{n}"
    total = BASELINE_S + FAULT_S + RECOVERY_S + SLACK_S

    check_healthy(service)

    print(f"{now()}  recording {label} for {total} seconds")
    collector = subprocess.Popen(
        [sys.executable, "collect.py", label, str(total / 60)],
        cwd=DATA, stdout=subprocess.DEVNULL)

    time.sleep(BASELINE_S)
    print(f"{now()}  injecting {fault} into {service}")
    cmd = [sys.executable, str(FAULTS[fault]), service, str(FAULT_S)]
    if fault == "net_delay":
        cmd.append(str(delay_ms))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        collector.terminate()
        sys.exit("STOP: the fault script failed. Delete the partial data file for this run.")

    print(f"{now()}  fault finished, recording the recovery...")
    collector.wait()
    if collector.returncode != 0:
        sys.exit("WARNING: the collector stopped with an error. Check data/ before using this run.")
    print(f"{now()}  done: data/data_{label}.csv")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in FAULTS:
        sys.exit("usage: python infra\\run_experiment.py <cpu_hog|mem_leak|net_delay> <service>")
    run(sys.argv[1], sys.argv[2])