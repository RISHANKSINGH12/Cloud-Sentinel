# Cloud Sentinel - Self-Healing Cloud System

An experiment-driven prototype for cloud fault detection and root-cause analysis. It analyzes recorded service metrics and shop-page latency, evaluates detectors on held-out experiments, and presents evidence in a Streamlit dashboard.

> **Current scope:** The dashboard analyzes saved CSV recordings; it does not connect to Kubernetes, and its recovery demo is a synthetic simulation. Separately, `remediator/live_heal.py` is a closed-loop controller that was run against a disposable local kind cluster (Online Boutique, namespace `default`). Only with `--approve` does it restart pods, in response to injected CPU and memory faults. It is a prototype for that sandbox, not a production system. The fault injectors and `--approve` can delete pods, so use them only in a disposable test cluster.

## Run the dashboard

The dashboard uses the experiment recordings included in this project. You do **not** need Kubernetes, Prometheus, or a running shop to view them.

### Requirements

- Python 3.12
- Internet access to install Python packages
- The complete project folder, including `data/` and `eval/`

### Windows (PowerShell)

Open PowerShell in the project folder and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run dashboard\app.py
```

Open the local URL printed by Streamlit, usually <http://localhost:8501>.

### macOS or Linux

Open a terminal in the project folder and run:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run dashboard/app.py
```

Open the local URL printed by Streamlit, usually <http://localhost:8501>.

To stop the dashboard, press `Ctrl+C` in the terminal running Streamlit.

## What the project contains

| Area | Purpose |
| --- | --- |
| `data/collect.py` | Collects Prometheus service metrics and Home, Product, and Cart page latency. |
| `infra/` | Injects CPU, memory, or network-delay faults and runs experiments. These tools can affect Kubernetes workloads. |
| `detector/detect_v1.py`, `detector/detect_v2.py` | Evaluate resource and page-latency fault signals on recorded experiments. |
| `eval/` | Stores experiment metadata, evaluation scripts, results, and the held-out manifest. |
| `rca/rca_v1.py` | Ranks possible causes from CPU and memory changes and reports successful page latency separately from timeouts. |
| `remediator/dry_run.py` | Prints a `REVIEW ONLY` or `NO ACTION` recommendation; it executes no cluster action. |
| `remediator/recovery_simulation.py` | Provides the dashboard's allowlisted detect/action/verify sandbox demo using synthetic in-memory metrics. |
| `dashboard/app.py` | Displays recorded evidence, page impact, recommendations, and the sandbox recovery demo. |
| `tests/` | Contains regression tests for page latency, timeouts, manifest integrity, and the sandbox simulation. |

For a presentation walkthrough, see [DEMO.md](DEMO.md). Evaluation details and known limitations are in [eval/RESULTS.md](eval/RESULTS.md).

## Run tests and evaluations

Run these commands from the project root after activating the virtual environment.

### Regression tests

```powershell
python -m unittest discover -s tests -v
```

### Held-out and healthy-baseline evaluations

```powershell
python eval\evaluate_test.py
python eval\evaluate_healthy_latency.py
```

The healthy evaluator uses only manifest entries marked as healthy training runs. It does not tune detector thresholds.

### Analyze one recording

```powershell
python rca\rca_v1.py data\data_net_delay_cartservice_2.csv
python remediator\dry_run.py data\data_net_delay_cartservice_2.csv
```

## Collect new experiment data

Data collection requires a running shop and Prometheus reachable at:

- Shop: `http://localhost:8080`
- Prometheus: `http://localhost:9090`

Kubernetes context and port forwarding are environment-specific. Before running any script in `infra/`, verify the active Kubernetes context and confirm the target is a disposable cluster. Do not run fault injection against a production or shared cluster. The experiment runner's health check may delete the selected service's pod while attempting recovery.

## Data and evaluation notes

- `eval/make_manifest.py` is the source of truth for experiment roles. After an intentional manifest change, regenerate it with:

  ```powershell
  python eval\make_manifest.py
  ```

- Keep training, partial, excluded, and held-out test recordings in their assigned roles. Do not tune thresholds on held-out runs and then report those same runs as an untouched evaluation.
- Page timeouts are recorded as `5.0` seconds. Detectors treat these as failed requests, not successful slow responses; the RCA and dashboard report timeout counts separately.
- Two five-minute healthy three-page recordings produced zero latency alert starts, zero flagged successful samples, and zero timeouts in 46 probes after the baseline window. This is an initial check, not enough data to establish a long-term false-positive rate.
- An interrupted partial recording is intentionally not registered.

## Evaluation snapshot

The held-out set contains eight runs:

| Detector | Result |
| --- | --- |
| v1 resource detector | 4/8 detections; 17 flagged resource rows outside fault windows |
| v2 resource detector | 4/8 detections; zero flagged resource rows outside fault windows |
| v2 Home-latency detector | 2/8 detections; zero flagged successful samples outside fault windows |
| Combined v2 resource or Home-latency detector | 6/8 detections |

Only two held-out recordings include separate Product and Cart latency columns. The other six contain Home latency only; the dashboard marks the missing comparisons unavailable rather than treating them as unaffected. In the newer cartservice network-delay run, all three measured pages slowed. The paymentservice run did not show a page-latency increase. Page impact alone is not used to infer a delayed service.

## Closed-loop healing (sandbox cluster)

`remediator/live_heal.py` runs the full loop on the disposable kind cluster: it reads live Prometheus
metrics, detects CPU and memory faults with the streaming detector in `detector/online.py`, chooses the
target without using `faults.csv`, restarts that service's pod only when `--approve` is passed and every
safety check allows it, then verifies recovery and writes an audit log. Network-delay faults raise a
page-latency alarm only; no action is taken because page latency does not identify the service.

See [docs/CLOSED_LOOP.md](docs/CLOSED_LOOP.md) for how to run it and `python eval\closed_loop_report.py`
to summarize results. The dashboard's recovery demo remains a synthetic simulation.

### Measured results (kind cluster, 7 attempts)

Each run injected one fault for about 3 minutes. The controller was started about a minute earlier with `--approve`.

| Fault | Service | Detected after | Pod replaced after | Result |
| --- | --- | --- | --- | --- |
| CPU hog | cartservice | 36 s | 69 s | escalated: verification ran too early (see below) |
| CPU hog | cartservice | 40 s | 72 s | recovered |
| CPU hog | checkoutservice | 32 s | 44 s | recovered |
| CPU hog | currencyservice | 36 s | 49 s | recovered |
| Memory leak | paymentservice | 74 s | 87 s | recovered |
| Memory leak | checkoutservice | 29 s | 40 s | recovered |
| Memory leak | cartservice | 85 s | 118 s | recovered |

- The controller chose the correct service in 7 of 7 attempts without reading `eval/faults.csv`, and 6 of 7 were verified as recovered.
- Median detection delay was 36 s. Median time to fix (fault start until the replacement pod was Ready) was 60 s for the six recovered runs. Confirming recovery adds the settle time and a 45 s watch, so the verdict arrived a median of 198 s after fault start.
- The unassisted figure of about 181 s is the length of the injected fault window, not a measure of how long a human operator would take.
- The one escalation used the default 30 s settle time. The new cartservice pod was still starting up, and its CPU was above the pre-fault limit at the check and back to normal about 20 s later. The other six runs used `--settle-s 90`; the default in the code is unchanged.
- One further cartservice memory-leak run is not counted: Kubernetes restarted the container after a failed liveness probe before the leak grew, and the controller took no action. The report only counts attempts where the controller acted, so a run like this does not appear in its totals.
- With 7 attempts on four services and two fault types, treat these as demonstration results, not statistics. Raw results are in `eval/closed_loop_results.csv` and the audit log is `eval/heal_log.jsonl`.

## Limitations

This is a prototype evaluated on one disposable kind cluster, not a production remediation system.

- **Small sample.** There are 7 closed-loop attempts on four services (cartservice, checkoutservice, currencyservice, paymentservice), one fault per run.
- **Fault coverage.** The controller acts only on CPU and memory faults. Network-delay faults are not caught by the resource detector in the held-out replay, and page latency alone does not identify a service, so no action is taken for them.
- **Detection margin.** Two of the three memory-leak detections scored only just above the threshold (z = 6.3 and 6.5 against 6.0), so smaller or slower leaks relative to a service's normal memory may be missed. This was not tested further.
- **Baseline.** "Normal" is learned from the first 50 seconds after the controller starts. This assumes the system is healthy then, and it does not adapt to later drift.
- **Verification timing.** Verification can fail on a healthy replacement that is still starting up. This happened once, with the default 30 s settle time.
- **Single action.** The only remediation is restarting one pod. There is no rollback, scaling, or operator notification.
- **Safety scope.** The guards allow only the `kind-aiops` context, the `default` namespace and the ten application services. Nothing has been tested outside that.
- **Dashboard.** The dashboard's recovery flow is still a synthetic simulation, not a real service restart.

## Future enhancements

The following are planned extensions; they are not implemented in the current prototype:

- **More environments:** run the controller against other explicitly selected test environments. So far it has run only on one kind cluster.
- **Better verification:** wait for each service's readiness and warm-up instead of a fixed settle time, and add a rollback or operator-notification path when recovery fails.
- **Broader evaluation:** more runs per fault and service, more fault types (including a service-level signal for network delay), long healthy runs to measure false alarms, and reporting of missed detections, which the current report does not count.
- **Adaptive detection:** re-learn baselines over time and scale thresholds to each service's normal memory so smaller leaks are not missed.
- **Access control:** add authentication and role-based approval for recovery actions. The audit log exists but is a local file.