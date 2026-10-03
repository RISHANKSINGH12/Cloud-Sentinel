# Closed-loop healing in the sandbox cluster

`remediator/live_heal.py` is the part of the project that acts on a live (disposable) kind cluster:

```
Prometheus + shop probes -> streaming detector -> pick target -> guard checks
        -> restart pod (only with --approve) -> verify recovery -> audit log
```

## What it does and does not do

| Fault | Detected by | Action |
| --- | --- | --- |
| CPU hog | resource detector (`detector/online.py`) | restart the service's pod |
| Memory leak | resource detector | restart the service's pod |
| Network delay | page-latency alarm only | **none**: latency does not identify a service, so it escalates to the operator |

The target is chosen without `faults.csv`: it is the flagged service furthest from its own normal range.
Verification passes only if the replacement pod's CPU and memory are back inside the pre-fault range and
the home page answers without timeouts under its baseline latency cutoff. If verification fails the
service is locked and the controller stops acting on it.

## Safety rules (enforced in code, covered by `tests/test_live_heal.py`)

- kubectl context must be `kind-aiops` and namespace `default`.
- Only the ten Online Boutique application services can be restarted (not redis-cart or loadgenerator).
- Dry run by default; `--approve` is required to change anything.
- 300 s cooldown per service, at most 3 actions per run, lock after a failed recovery.
- Every decision is appended to `eval/heal_log.jsonl`.

## Run it

Keep the two port-forwards running (Prometheus on 9090, shop on 8080), then from the project root:

```powershell
# 1. Dry run first: it logs what it would do and changes nothing
python remediator\live_heal.py

# 2. In a second terminal, wait about a minute for the baseline, then inject a fault
python infra\run_experiment.py cpu_hog cartservice

# 3. Real recovery in the sandbox
python remediator\live_heal.py --approve
python infra\run_experiment.py cpu_hog cartservice

# 4. After several runs, summarize
python eval\closed_loop_report.py
```

The injectors now call `kubectl delete pod --ignore-not-found`, so the end-of-fault cleanup does not fail
when the controller already replaced the pod.

## Measuring the result

`eval\closed_loop_report.py` joins the heal log with `eval/faults.csv` and reports, per run, whether the
right service was chosen, the detection delay, the recovery time with the controller, and the unassisted
baseline (the injected window, because without the controller the fault only ends when the injector deletes
the pod). Do 3-5 runs per fault type and service and report the spread, not a single number.

## Offline check (no cluster needed)

```powershell
python eval\replay_online.py
```

Replays the eight held-out recordings through the streaming detector: 4/8 detected, all four chosen
correctly without `faults.csv`, zero flags outside the fault window (same as `detect_v2.py`).
