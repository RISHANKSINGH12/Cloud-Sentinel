import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "eval" / "faults.csv"


def sh(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("COMMAND FAILED:", " ".join(cmd))
        print(result.stderr)
        sys.exit(1)
    return result.stdout.strip()


def now():
    return datetime.now().isoformat(timespec="seconds")


# shell loop: every 5 seconds, grow a string by 2 MB and keep it in memory
LEAK = (
    "a=''; "
    "while true; do "
    "a=\"$a$(head -c 2097152 /dev/zero | tr '\\0' 'x')\"; "
    "sleep 5; "
    "done"
)


def mem_leak(service, seconds):
    pod = sh(["kubectl", "get", "pod", "-l", f"app={service}",
              "-o", "jsonpath={.items[0].metadata.name}"])
    print(f"{now()}  starting memory leak inside {pod}")
    start = now()

    sh(["kubectl", "debug", f"pod/{pod}", "--image=busybox:1.36",
        "--container=mem-leak", "--", "sh", "-c", LEAK])

    time.sleep(seconds)

    sh(["kubectl", "delete", "pod", pod, "--ignore-not-found"])
    end = now()
    print(f"{end}  fault removed, pod replaced")

    LOG.parent.mkdir(exist_ok=True)
    new_file = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["fault", "service", "start", "end"])
        w.writerow(["mem_leak", service, start, end])


if __name__ == "__main__":
    service = sys.argv[1] if len(sys.argv) > 1 else "currencyservice"
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 180
    mem_leak(service, seconds)