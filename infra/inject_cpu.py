import csv
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ground-truth log: which fault hit which service, and when
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


def cpu_hog(service, seconds):
    pod = sh(["kubectl", "get", "pod", "-l", f"app={service}",
              "-o", "jsonpath={.items[0].metadata.name}"])
    print(f"{now()}  starting CPU hog inside {pod}")
    start = now()

    # attach an extra container to the pod that spins forever
    sh(["kubectl", "debug", f"pod/{pod}", "--image=busybox:1.36",
        "--container=cpu-hog", "--", "sh", "-c", "while true; do :; done"])

    time.sleep(seconds)

    # cleanup: delete the pod, Kubernetes replaces it with a healthy one
    sh(["kubectl", "delete", "pod", pod, "--ignore-not-found"])
    end = now()
    print(f"{end}  fault removed, pod replaced")

    LOG.parent.mkdir(exist_ok=True)
    new_file = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["fault", "service", "start", "end"])
        w.writerow(["cpu_hog", service, start, end])


if __name__ == "__main__":
    service = sys.argv[1] if len(sys.argv) > 1 else "productcatalogservice"
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 180
    cpu_hog(service, seconds)