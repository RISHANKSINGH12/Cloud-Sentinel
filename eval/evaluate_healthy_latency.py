from pathlib import Path
from typing import TypedDict

import pandas as pd

if __package__:
    from .evaluate_test import (
        BASELINE_S,
        CONSEC,
        DATA,
        LAT_FLOOR,
        LAT_THRESH,
        LATENCY_COLUMNS,
        MANIFEST,
    )
else:
    from evaluate_test import (
        BASELINE_S,
        CONSEC,
        DATA,
        LAT_FLOOR,
        LAT_THRESH,
        LATENCY_COLUMNS,
        MANIFEST,
    )


class PageResult(TypedDict):
    baseline_median_s: float
    cutoff_s: float
    alerts: int
    flagged_samples: int
    timeouts: int
    scored_probes: int


def score_recording(path: Path) -> dict[str, PageResult]:
    frame = pd.read_csv(path, parse_dates=["time"])
    required = {"time", *LATENCY_COLUMNS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name}: missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{path.name}: recording contains no data rows")

    latency = (
        frame.drop_duplicates("time")[["time", *LATENCY_COLUMNS]]
        .sort_values("time")
        .reset_index(drop=True)
    )
    recording_start = latency["time"].min()
    baseline_end = recording_start + pd.Timedelta(seconds=BASELINE_S)
    baseline_window = latency["time"] < baseline_end
    scoring_window = latency["time"] >= baseline_end
    if not scoring_window.any():
        raise ValueError(f"{path.name}: no probes after the {BASELINE_S}s baseline")

    results: dict[str, PageResult] = {}
    for column in LATENCY_COLUMNS:
        baseline_values = latency.loc[
            baseline_window & (latency[column] < 5.0), column
        ]
        if baseline_values.empty:
            raise ValueError(f"{path.name}: no successful baseline samples for {column}")

        median = float(baseline_values.median())
        mad = float((baseline_values - median).abs().median() * 1.4826)
        wiggle = max(mad, LAT_FLOOR, 0.1 * median)
        successful = latency[column] < 5.0
        raw = successful & (
            (latency[column] - median) / wiggle > LAT_THRESH
        )
        flagged = raw.rolling(CONSEC).sum() == CONSEC
        alert_starts = flagged & ~flagged.shift(fill_value=False)

        results[column] = {
            "baseline_median_s": median,
            "cutoff_s": median + LAT_THRESH * wiggle,
            "alerts": int((alert_starts & scoring_window).sum()),
            "flagged_samples": int((flagged & scoring_window).sum()),
            "timeouts": int((latency[column] >= 5.0).sum()),
            "scored_probes": int(scoring_window.sum()),
        }

    return results


def main() -> None:
    manifest = pd.read_csv(MANIFEST, dtype=str).fillna("")
    required_manifest = {"file", "fault", "role"}
    missing = required_manifest - set(manifest.columns)
    if missing:
        raise ValueError(f"Manifest missing columns: {sorted(missing)}")

    healthy_runs = manifest[
        (manifest["role"] == "train") & (manifest["fault"] == "none")
    ]
    if healthy_runs.empty:
        raise ValueError("Manifest contains no healthy training runs")

    evaluated = 0
    for _, run in healthy_runs.iterrows():
        path = DATA / run["file"]
        if not path.is_file():
            raise FileNotFoundError(f"Manifest data file does not exist: {path}")

        columns = set(pd.read_csv(path, nrows=0).columns)
        if not set(LATENCY_COLUMNS).issubset(columns):
            print(f"{run['file']}: skipped; three-page latency columns unavailable")
            continue

        results = score_recording(path)
        evaluated += 1
        print(f"{run['file']}:")
        for page, result in results.items():
            print(
                f"  {page}: alerts={result['alerts']}, "
                f"flagged_samples={result['flagged_samples']}, "
                f"timeouts={result['timeouts']}, "
                f"scored_probes={result['scored_probes']}, "
                f"baseline_median={result['baseline_median_s']:.4f}s, "
                f"cutoff={result['cutoff_s']:.4f}s"
            )

    if evaluated == 0:
        raise ValueError("No healthy training runs had all three page-latency columns")
    print(f"Healthy three-page recordings evaluated: {evaluated}")
    print(
        "Thresholds were not tuned from these scores; use them as a healthy "
        "baseline check, not as a long-term false-positive rate."
    )


if __name__ == "__main__":
    main()
