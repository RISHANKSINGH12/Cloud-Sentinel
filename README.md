# Cloud Sentinel- Self-Healing Cloud System

An experiment-driven prototype for cloud fault detection and root-cause analysis. It analyzes recorded service metrics and shop-page latency, evaluates detectors on held-out experiments, and presents evidence in a Streamlit dashboard.

> **Current scope:** The dashboard analyzes saved CSV recordings. Its self-healing workflow is a synthetic sandbox demonstration only; it does not restart real services or connect to Kubernetes. Fault-injection tools do interact with Kubernetes and can delete pods. Use them only in a disposable test cluster.

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

## Limitations

This is an evaluation prototype, not an autonomous production remediation system. Real automatic remediation, approval workflows, production-grade monitoring, and comprehensive page-latency coverage are not implemented. The dashboard's recovery flow is a sandbox simulation, not a real service restart.

## Future enhancements

The following are planned extensions; they are not implemented in the current prototype:

- **Live monitoring:** ingest metrics from a connected, explicitly selected test environment instead of relying only on saved recordings.
- **Controlled Kubernetes recovery:** add real recovery actions limited to a disposable namespace, with explicit operator approval and a strict allowlist.
- **Recovery verification and rollback:** run post-action health checks, record the outcome, and provide a safe rollback or escalation path if recovery fails.
- **Broader evaluation:** add more fault scenarios and independent recordings, then evaluate detection quality and false alarms on a larger held-out dataset.
- **Access control and auditing:** add authentication, role-based permissions, and an audit trail for approved recovery actions.
