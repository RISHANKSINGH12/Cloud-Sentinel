# Cloud Sentinel demo runbook

This is a short, read-only demonstration using existing recordings. It does not inject faults or change a cluster.

## Before the demo

From the project root, start the dashboard if it is not already running:

```powershell
python -m streamlit run dashboard\app.py
```

Open the local URL printed by Streamlit. The sidebar should say **Read-only · No cluster actions**. The experiment selector contains the eight held-out test runs; healthy training recordings are intentionally not selectable.

For a quick pre-demo check:

```powershell
python -m unittest discover -s tests -v
```

## Suggested three-run walkthrough

### 1. Cartservice network delay — visible impact, unknown cause

Select **Network delay · Cartservice · Run 2**.

Expected:

- RCA status: **UNKNOWN**
- Recommendation: **NO ACTION**
- Home: approximately `0.096 s` before and `0.673 s` during
- Product: approximately `0.044 s` before and `0.641 s` during
- Cart: approximately `0.046 s` before and `0.639 s` during
- Timeouts: `0`

The chart shows grouped before/during bars for Home, Product, and Cart. Explain that the measurements demonstrate customer-facing impact, but page latency alone is not treated as proof of which service caused it. Therefore the system does not recommend an automatic change.

### 2. Paymentservice network delay — no measured page impact

Select **Network delay · Paymentservice · Run 2**.

Expected:

- RCA status: **UNKNOWN**
- Recommendation: **NO ACTION**
- Home, Product, and Cart successful-request latencies stay approximately flat
- Timeouts: `0`

Contrast this result with the cartservice run. The current probes did not expose the paymentservice delay as a user-facing latency increase.

### 3. Frontend CPU hog — resource evidence and failed probes

Select **CPU issue · Frontend · Run 1**.

Expected:

- Leading resource-supported candidate: `frontend`
- Recommendation: **REVIEW ONLY**
- Timeouts during the fault: `4`
- Timeouts after the fault window: `14`

Clarify that timeout sentinels are failed probes, not slow successful responses. The recommendation remains operator-reviewed; the dashboard does not perform remediation.

## Self-healing sandbox demonstration

On a run with a resource-supported candidate, select **Run sandbox recovery** in the Self-healing simulation section.

Expected:

- The simulation reports a detected synthetic CPU, memory, or latency threshold breach.
- It displays the allowlisted simulated action for the selected fault type.
- It shows before/after sandbox metrics and whether the simulated health check passed.

Explain that the selected recording provides the fault type and RCA target, but the sandbox uses synthetic in-memory metrics. No recorded CSV is changed, no Kubernetes connection is made, and no real service is restarted. This demonstrates the recovery-control flow, not live remediation.

## Honest limits to mention

- The held-out set contains eight runs. Combined v2 resource-or-home-latency detection is `6/8`; v2 resource detection is `4/8`.
- The RCA resource-score threshold is provisional, not a calibrated probability.
- Only two held-out recordings have separate Product and Cart latency measurements.
- The other six held-out recordings have Home data only; the dashboard calls out missing Product/Cart data instead of treating it as evidence that those pages were unaffected.
- Two five-minute healthy recordings produced no page-latency alerts or timeouts, but that is not enough data to claim a long-term false-positive rate.
- Real automatic remediation, production approvals, and production readiness are not implemented; the self-healing section is an isolated sandbox simulation.

## Reproducibility

Run the held-out evaluation and healthy-latency check without retuning thresholds:

```powershell
python eval\evaluate_test.py
python eval\evaluate_healthy_latency.py
```

See [README.md](README.md) for setup and [eval/RESULTS.md](eval/RESULTS.md) for the detailed results.
