# Held-out evaluation results

This report summarizes the eight runs marked `test` in [manifest.csv](./manifest.csv). The evaluator reads only those held-out runs; the threshold and detector settings were not retuned for this report.

## Detector results

| Detector | Runs detected | False alarms / flags | Notes |
|---|---:|---|---|
| v1 resource | 4/8 | 17 flagged rows | Detected the four CPU/memory faults and ranked the injected service first in each. |
| v2 resource | 4/8 | 0 flagged rows | Detected the same four CPU/memory faults and ranked the injected service first in each. |
| v2 home latency | 2/8 | 0 new episodes; 0 flagged successful samples | Scores successful-request latency only; timeout sentinels are excluded and counted separately. |
| v2 resource or home latency | 6/8 | — | Combined run-level detection; network-delay runs remain dependent on observable successful page impact. |

The resource detectors did not detect the four network-delay runs. For the newer cartservice delay run, home, product, and cart latency were detected as elevated at 23 seconds. The corresponding paymentservice delay run did not produce a page-latency detection. These measurements show impact for the cartservice run, but do not identify a delayed service by themselves.

Latency false alarms are counted by **alert-episode starts**, not by every consecutive flagged sample. More importantly, the detector excludes values of `5.0` seconds or greater from latency scoring because the collector uses `5.0` as its request-timeout sentinel. Those values are failed probes, not slow successful responses. The held-out detector therefore has zero latency flags outside fault windows. In the training runs with home-latency data, no new outside-window episode starts were observed; one flagged sample outside a training fault window continued an in-fault episode under the old scoring behavior. The latency threshold was not changed.

Two new five-minute healthy recordings, [data_healthy_pages.csv](../data/data_healthy_pages.csv) and [data_healthy_pages_2_complete.csv](../data/data_healthy_pages_2_complete.csv), each had 46 post-baseline probes scored. Home, product, and cart each produced zero alert starts, zero flagged samples, and zero timeouts in both recordings. They are registered as `train`, not `test`, in the manifest. The older healthy recordings do not have page-latency columns. These two short windows provide an initial healthy check, not a reliable long-term false-positive rate.

Reproduce this healthy-only check, using the current thresholds without tuning them:

```powershell
python eval\evaluate_healthy_latency.py
```

## Timeouts and data coverage

The frontend CPU-hog test contains four home-page timeouts during its fault window **and 14 more after the fault window ended**. These are failed probes, not merely high successful-request latency. The other seven held-out runs have no timeouts during or after their fault windows in the recorded data.

Only the two newer network-delay test recordings contain separate product and cart latency columns. The other six test recordings support home-page latency analysis only, so page-level comparisons across the full set have incomplete coverage.

## RCA and remediation behavior

The RCA threshold of 1.5 is provisional and was selected from training examples; it is not a probability or calibrated confidence score. On the two newer network-delay runs, RCA reports `unknown`. The dry-run recommender reports `NO ACTION` for both, despite the measurable page impact in the cartservice run. The frontend CPU-hog run receives a `REVIEW ONLY` recommendation and reports its four timeouts.

The dashboard and recommender analyze recorded files only. They do not connect to Kubernetes or execute remediation.

## Reproduce

From the project root, install the pinned dependencies and run the held-out evaluator:

```powershell
pip install -r requirements.txt
python eval\evaluate_test.py
```

Run a read-only recommendation for one recording:

```powershell
python remediator\dry_run.py data\data_net_delay_cartservice_2.csv
```

Launch the offline dashboard:

```powershell
python -m streamlit run dashboard\app.py
```
