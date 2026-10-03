import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "eval" / "faults.csv"
SETTINGS = Path(__file__).resolve().parent / "debug.json"


def sh(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("COMMAND FAILED:", " ".join(cmd))
        print(result.stderr)
        sys.exit(1)
    return result.stdout.strip()


def now():
    return datetime.now().isoformat(timespec="seconds")


def net_delay(service, seconds, delay_ms):
    # settings that let the extra container change the pod's network
    SETTINGS.write_text(json.dumps({"securityContext": {
        "runAsUser": 0, "runAsNonRoot": False,
        "capabilities": {"add": ["NET_ADMIN"]}}}))

    pod = sh(["kubectl", "get", "pod", "-l", f"app={service}",
              "-o", "jsonpath={.items[0].metadata.name}"])
    print(f"{now()}  adding {delay_ms} ms delay to {pod}")
    start = now()

    cmd = (f"tc qdisc add dev eth0 root netem delay {delay_ms}ms "
           f"&& echo DELAY_ON || echo DELAY_FAILED; sleep 900")
    sh(["kubectl", "debug", f"pod/{pod}", "--image=nicolaka/netshoot",
        f"--custom={SETTINGS}", "--container=net-delay", "--", "sh", "-c", cmd])

    time.sleep(15)
    logs = subprocess.run(["kubectl", "logs", pod, "-c", "net-delay"],
                          capture_output=True, text=True).stdout
    print("delay check:", "ON" if "DELAY_ON" in logs else "NOT CONFIRMED")

    time.sleep(max(seconds - 15, 0))

    sh(["kubectl", "delete", "pod", pod, "--ignore-not-found"])
    end = now()
    print(f"{end}  fault removed, pod replaced")

    LOG.parent.mkdir(exist_ok=True)
    new_file = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["fault", "service", "start", "end"])
        w.writerow(["net_delay", service, start, end])


if __name__ == "__main__":
    service = sys.argv[1] if len(sys.argv) > 1 else "productcatalogservice"
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 180
    delay_ms = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    net_delay(service, seconds, delay_ms)