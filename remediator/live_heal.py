"""Closed-loop self-healing controller for the disposable kind cluster.

detect -> choose target -> (approved) restart pod -> verify -> audit log

Safety rules, all enforced in code:
  * It only acts when the kubectl context and namespace are on an allowlist.
  * Only an allowlisted set of services can be restarted.
  * Without --approve it is a dry run: it logs what it WOULD do and changes nothing.
  * Cooldown per service, a cap on total actions, and a lock after a failed recovery.
  * The only action is deleting the target's pod so its Deployment replaces it.
  * Page latency alone never triggers an action: it cannot say which service is slow.
  * Every decision is appended to eval/heal_log.jsonl.

Usage (from the project root, port-forwards for Prometheus :9090 and shop :8080 running):
    python remediator/live_heal.py                 # dry run, 30 minutes
    python remediator/live_heal.py --approve       # real restarts in the sandbox
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "data"))

import collect  # noqa: E402  (data/collect.py: Prometheus + page probes)
from detector.online import (  # noqa: E402
    BASELINE_S, CONSEC, FLOORS, THRESH, TIMEOUT_S, OnlineDetector, latency_cutoff,
)

ALLOWED_CONTEXTS = {"kind-aiops"}
ALLOWED_NAMESPACES = {"default"}
ALLOWED_SERVICES = {
    "adservice", "cartservice", "checkoutservice", "currencyservice",
    "emailservice", "frontend", "paymentservice", "productcatalogservice",
    "recommendationservice", "shippingservice",
}
DEFAULT_LOG = ROOT / "eval" / "heal_log.jsonl"
MIN_VERIFY_SAMPLES = 3


# ---------------------------------------------------------------- pure logic
def check_guard(context, namespace, service, *, last_action, locked, actions_done,
                max_actions, cooldown_s, now):
    """Return None if an action is allowed, otherwise the reason it is refused."""
    if context not in ALLOWED_CONTEXTS:
        return f"kubectl context {context!r} is not allowlisted"
    if namespace not in ALLOWED_NAMESPACES:
        return f"namespace {namespace!r} is not allowlisted"
    if service not in ALLOWED_SERVICES:
        return f"service {service!r} is not allowlisted"
    if service in locked:
        return f"{service} is locked after a failed recovery; operator review needed"
    if actions_done >= max_actions:
        return f"action budget of {max_actions} reached"
    if service in last_action and (now - last_action[service]) < cooldown_s:
        return f"{service} is in cooldown"
    return None


def is_recovered(params, samples, lat_cutoff, lat_values):
    """Decide whether a restarted service is back within its old normal range.

    params     {metric: (median, wiggle)} learned before the fault
    samples    reading dicts for the target service after the restart
    lat_cutoff home-page latency limit learned before the fault (or None)
    lat_values home-page latencies measured during verification
    """
    if len(samples) < MIN_VERIFY_SAMPLES:
        return False, "not enough verification samples"
    for col in FLOORS:
        med, wiggle = params[col]
        current = median(s[col] for s in samples)
        limit = med + THRESH * wiggle
        if current > limit:
            return False, f"{col} median {current:.3f} still above limit {limit:.3f}"
    if lat_values:
        if any(v >= TIMEOUT_S for v in lat_values):
            return False, "page request timed out during verification"
        if lat_cutoff is not None and median(lat_values) > lat_cutoff:
            return False, "page latency still above its baseline cutoff"
    return True, "CPU, memory and page latency are back within baseline"


# ------------------------------------------------------------------ kubectl
def kubectl(*args, timeout=150):
    return subprocess.run(["kubectl", *args], capture_output=True, text=True,
                          timeout=timeout)


def current_context():
    return kubectl("config", "current-context").stdout.strip()


def restart_service(service, namespace):
    """Delete the service's pod(s); the Deployment starts a clean replacement."""
    pods = kubectl("get", "pod", "-n", namespace, "-l", f"app={service}",
                   "-o", "jsonpath={.items[*].metadata.name}").stdout.split()
    if not pods:
        return False, f"no pod found for app={service}"
    for pod in pods:
        r = kubectl("delete", "pod", pod, "-n", namespace, "--grace-period=10",
                    "--ignore-not-found")
        if r.returncode != 0:
            return False, r.stderr.strip()
    r = kubectl("wait", "--for=condition=Ready", "pod", "-n", namespace,
                "-l", f"app={service}", "--timeout=120s")
    if r.returncode != 0:
        return False, r.stderr.strip() or "replacement pod did not become Ready"
    return True, f"replaced {', '.join(pods)}"


# -------------------------------------------------------------------- audit
def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def audit(path, event, **fields):
    record = {"time": now_iso(), "event": event, **fields}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"{record['time']}  {event}  " + "  ".join(f"{k}={v}" for k, v in fields.items()))
    return record


# --------------------------------------------------------------------- loop
def verify(service, params, lat_cutoff, args):
    """Wait for the replacement to settle, then watch it for --verify-s seconds."""
    time.sleep(args.settle_s)
    samples, lats = [], []
    end = time.time() + args.verify_s
    while time.time() < end:
        rows = collect.collect_once("verify")
        if rows:
            lats.append(rows[0][5])  # home-page latency, same in every row
        for row in rows:
            if row[1] == service:
                samples.append({"memory_mb": row[2], "cpu_cores": row[3]})
        time.sleep(args.interval)
    return is_recovered(params, samples, lat_cutoff, lats)


def run(args):
    log = Path(args.log)
    context = current_context()
    detector = OnlineDetector()
    last_action, locked, actions_done, reported = {}, set(), 0, set()
    lat_baseline, lat_cutoff, lat_streak, alarm_open = [], None, 0, False
    started = time.time()
    audit(log, "start", context=context, namespace=args.namespace,
          mode="ACTIVE" if args.approve else "DRY-RUN")

    while time.time() - started < args.minutes * 60:
        try:
            rows = collect.collect_once("live")
        except Exception as error:  # Prometheus or shop port-forward is down
            print(f"{now_iso()}  collection failed: {error}")
            time.sleep(args.interval)
            continue
        now = datetime.now()
        elapsed = time.time() - started

        # page-latency watcher (alarm only, never an action)
        if rows:
            home = rows[0][5]
            if elapsed < BASELINE_S:
                lat_baseline.append(home)
            else:
                if lat_cutoff is None:
                    lat_cutoff = latency_cutoff(lat_baseline)
                abnormal = lat_cutoff is not None and home < TIMEOUT_S and home > lat_cutoff
                lat_streak = lat_streak + 1 if abnormal else 0
                if lat_streak >= CONSEC and not alarm_open:
                    alarm_open = True
                    audit(log, "latency_alarm", home_latency_s=home,
                          action="ESCALATE: page latency does not identify a service; no change made")
                if lat_streak == 0:
                    alarm_open = False

        # resource detector
        flagged = []
        for row in rows:
            service, memory_mb, cpu_cores = row[1], row[2], row[3]
            reading = detector.update(now, service, memory_mb, cpu_cores)
            if reading and reading.flag:
                flagged.append((reading.z, service, reading.metric))
        if not flagged:
            time.sleep(args.interval)
            continue

        z, service, metric = max(flagged)  # blind RCA: furthest from its own normal
        reason = check_guard(
            context, args.namespace, service, last_action=last_action, locked=locked,
            actions_done=actions_done, max_actions=args.max_actions,
            cooldown_s=args.cooldown_s, now=time.time())
        if reason:
            # a persistent fault is re-flagged every cycle: log each refusal once
            if (service, reason) not in reported:
                reported.add((service, reason))
                audit(log, "detected", service=service, metric=metric, z=round(z, 1))
                audit(log, "refused", service=service, reason=reason)
            time.sleep(args.interval)
            continue

        reported = {k for k in reported if k[0] != service}
        t_detect = now_iso()
        audit(log, "detected", service=service, metric=metric, z=round(z, 1))
        last_action[service] = time.time()
        if not args.approve:
            audit(log, "would_restart", service=service,
                  note="dry run; pass --approve to act")
            time.sleep(args.interval)
            continue

        params = detector.params(service)
        t_action = now_iso()
        ok, detail = restart_service(service, args.namespace)
        actions_done += 1
        audit(log, "restart", service=service, ok=ok, detail=detail)
        detector.reset_service(service, datetime.now())
        if not ok:
            locked.add(service)
            audit(log, "escalate", service=service, reason=detail)
            continue

        recovered, why = verify(service, params, lat_cutoff, args)
        if recovered:
            audit(log, "recovered", service=service, metric=metric, t_detect=t_detect,
                  t_action=t_action, t_recovered=now_iso(), detail=why)
        else:
            locked.add(service)
            audit(log, "escalate", service=service, t_detect=t_detect,
                  t_action=t_action, reason=why)

    audit(log, "stop", actions=actions_done)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--approve", action="store_true",
                   help="really restart pods (default: dry run)")
    p.add_argument("--namespace", default="default")
    p.add_argument("--minutes", type=float, default=30)
    p.add_argument("--interval", type=float, default=5)
    p.add_argument("--settle-s", type=float, default=30,
                   help="wait after the new pod is Ready before verifying")
    p.add_argument("--verify-s", type=float, default=45)
    p.add_argument("--max-actions", type=int, default=3)
    p.add_argument("--cooldown-s", type=float, default=300)
    p.add_argument("--log", default=str(DEFAULT_LOG))
    args = p.parse_args()
    try:
        run(args)
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
