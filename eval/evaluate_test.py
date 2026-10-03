from pathlib import Path
from typing import TypedDict

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MANIFEST = ROOT / "eval" / "manifest.csv"
FAULTS = ROOT / "eval" / "faults.csv"

BASELINE_S = 50
THRESH = 6.0
CONSEC = 3
GRACE_S = 30
WARMUP_S = 120
DROP_RATIO = 0.5
FLOORS = {"cpu_cores": 0.01, "memory_mb": 1.0}
LAT_FLOOR = 0.05
LAT_THRESH = 6.0
LATENCY_COLUMNS = ["latency_s", "latency_product_s", "latency_cart_s"]
REQUIRED_COLUMNS = {
    "time", "service", "memory_mb", "cpu_cores", "restarts", "latency_s", "label"
}


class EvaluationResult(TypedDict):
    experiment: str
    v1_detected: bool
    v1_delay: float | None
    v1_first: str
    v1_correct_first: bool
    v1_false_rows: int
    v2_resource_detected: bool
    v2_resource_delay: float | None
    v2_first: str
    v2_correct_first: bool
    v2_resource_false_rows: int
    v2_latency_detected: bool
    v2_latency_delay: float | None
    v2_latency_false_rows: int
    v2_latency_false_episodes: int
    page_latency: dict[str, dict[str, bool | float | int | str | None]]
    timeouts_during_fault: dict[str, int]
    timeouts_after_fault: dict[str, int]
    page_latency_columns: list[str]


def learn_normal(base):
    params = {}
    for service, group in base.groupby("service"):
        for column, floor in FLOORS.items():
            median = group[column].median()
            mad = (group[column] - median).abs().median() * 1.4826
            params[(service, column)] = (
                median,
                max(mad, floor, 0.1 * abs(median)),
            )
    return params


def score_resources(frame, params):
    scores = pd.Series(0.0, index=frame.index)
    for column in FLOORS:
        medians = frame.apply(
            lambda row: params.get((row["service"], column), (0, 1))[0],
            axis=1,
        )
        wiggles = frame.apply(
            lambda row: params.get((row["service"], column), (0, 1))[1],
            axis=1,
        )
        scores = pd.concat(
            [scores, (frame[column] - medians).abs() / wiggles],
            axis=1,
        ).max(axis=1)
    return scores


def run_v2_service(group, start_time):
    group = group.sort_values("time").reset_index(drop=True)
    baseline = group[group["time"] < start_time + pd.Timedelta(seconds=BASELINE_S)]
    if baseline.empty:
        raise ValueError(f"No baseline readings for service {group['service'].iloc[0]}")

    params = {}
    for column, floor in FLOORS.items():
        median = baseline[column].median()
        mad = (baseline[column] - median).abs().median() * 1.4826
        params[column] = (median, max(mad, floor, 0.1 * abs(median)))

    warm_until = None
    relearn_from = None
    raw = []
    previous_memory = None

    for _, row in group.iterrows():
        timestamp = row["time"]
        if (
            previous_memory is not None
            and previous_memory > 5
            and row["memory_mb"] < DROP_RATIO * previous_memory
        ):
            warm_until = timestamp + pd.Timedelta(seconds=WARMUP_S)
            relearn_from = warm_until
        previous_memory = row["memory_mb"]

        if (
            relearn_from is not None
            and timestamp >= relearn_from + pd.Timedelta(seconds=BASELINE_S)
        ):
            window = group[
                (group["time"] >= relearn_from)
                & (group["time"] < relearn_from + pd.Timedelta(seconds=BASELINE_S))
            ]
            if not window.empty:
                for column, floor in FLOORS.items():
                    median = window[column].median()
                    mad = (window[column] - median).abs().median() * 1.4826
                    params[column] = (median, max(mad, floor, 0.1 * abs(median)))
            relearn_from = None
            warm_until = None

        if warm_until is not None:
            raw.append(0)
            continue

        z_score = max(
            abs(row[column] - params[column][0]) / params[column][1]
            for column in FLOORS
        )
        raw.append(int(z_score > THRESH))

    group["raw"] = raw
    group["flag"] = group["raw"].rolling(CONSEC).sum() == CONSEC
    return group


def matching_fault(manifest_row, faults, frame):
    matches = faults[
        (faults["fault"] == manifest_row["fault"])
        & (faults["service"] == manifest_row["service"])
        & (faults["start"] >= frame["time"].min())
        & (faults["end"] <= frame["time"].max())
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{manifest_row['file']}: expected one matching fault row, found {len(matches)}"
        )
    return matches.iloc[0]


def evaluate_run(manifest_row, faults) -> EvaluationResult:
    path = DATA / manifest_row["file"]
    if not path.is_file():
        raise FileNotFoundError(f"Manifest test file does not exist: {path}")

    frame = pd.read_csv(path, parse_dates=["time"])
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name}: missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{path.name}: CSV has no data rows")
    frame = frame.sort_values("time").reset_index(drop=True)

    fault = matching_fault(manifest_row, faults, frame)
    start_time = frame["time"].min()
    fault_window = (frame["time"] >= fault["start"]) & (frame["time"] <= fault["end"])

    baseline = frame[frame["time"] < start_time + pd.Timedelta(seconds=BASELINE_S)]
    if baseline.empty:
        raise ValueError(f"{path.name}: no readings in the initial {BASELINE_S}s baseline")

    # v1: per-run robust resource baseline and per-service consecutive flags.
    params = learn_normal(baseline)
    v1 = frame.copy()
    v1["raw"] = (score_resources(v1, params) > THRESH).astype(int)
    v1["flag"] = v1.groupby("service")["raw"].transform(
        lambda values: values.rolling(CONSEC).sum() == CONSEC
    )
    faulty_service = v1["service"] == fault["service"]
    v1_hits = v1[v1["flag"] & faulty_service & fault_window]
    v1_all_flags = v1[v1["flag"] & fault_window].sort_values("time")
    v1_false = v1[
        v1["flag"]
        & ~fault_window
        & ~(
            (v1["time"] > fault["end"])
            & (v1["time"] <= fault["end"] + pd.Timedelta(seconds=GRACE_S))
        )
        & (v1["time"] >= start_time + pd.Timedelta(seconds=BASELINE_S))
    ]

    # v2: resource detector with restart warm-up, plus shop-wide home latency.
    v2_parts = [
        run_v2_service(group, start_time)
        for _, group in frame.groupby("service")
    ]
    v2 = pd.concat(v2_parts).sort_index()
    v2_window = (v2["time"] >= fault["start"]) & (v2["time"] <= fault["end"])
    v2_hits = v2[
        v2["flag"] & (v2["service"] == fault["service"]) & v2_window
    ]
    v2_all_flags = v2[v2["flag"] & v2_window].sort_values("time")
    v2_tail = (v2["time"] > fault["end"]) & (
        v2["time"] <= fault["end"] + pd.Timedelta(seconds=15)
    )
    v2_false = v2[
        v2["flag"]
        & ~v2_window
        & ~v2_tail
        & (v2["time"] >= start_time + pd.Timedelta(seconds=BASELINE_S))
    ]

    latency = (
        frame.drop_duplicates("time")[["time", "latency_s"]]
        .sort_values("time")
        .reset_index(drop=True)
    )
    latency_baseline = latency[
        latency["time"] < start_time + pd.Timedelta(seconds=BASELINE_S)
    ]["latency_s"]
    latency_median = latency_baseline.median()
    latency_mad = (latency_baseline - latency_median).abs().median() * 1.4826
    latency_wiggle = max(latency_mad, LAT_FLOOR, 0.1 * latency_median)
    successful_latency = latency["latency_s"] < 5.0
    latency["raw"] = (
        successful_latency
        & ((latency["latency_s"] - latency_median) / latency_wiggle > LAT_THRESH)
    ).astype(int)
    latency["flag"] = latency["raw"].rolling(CONSEC).sum() == CONSEC
    latency["alarm_start"] = latency["flag"] & ~latency["flag"].shift(
        fill_value=False
    )
    latency_window = (latency["time"] >= fault["start"]) & (
        latency["time"] <= fault["end"]
    )
    latency_hits = latency[latency["flag"] & latency_window]
    latency_false = latency[
        latency["flag"]
        & ~latency_window
        & (latency["time"] >= start_time + pd.Timedelta(seconds=BASELINE_S))
    ]
    latency_false_episodes = latency[
        latency["alarm_start"]
        & ~latency_window
        & (latency["time"] >= start_time + pd.Timedelta(seconds=BASELINE_S))
    ]

    page_columns = [column for column in LATENCY_COLUMNS if column in frame.columns]
    page_latency = {}

    for column in page_columns:
        page = frame.drop_duplicates("time")[["time", column]].copy()
        valid = page[column] < 5.0
        page_baseline = page[
            valid & (page["time"] < start_time + pd.Timedelta(seconds=BASELINE_S))
        ][column]

        if page_baseline.empty:
            raise ValueError(f"{path.name}: no successful baseline samples for {column}")

        page_median = page_baseline.median()
        page_mad = (page_baseline - page_median).abs().median() * 1.4826
        page_wiggle = max(page_mad, LAT_FLOOR, 0.1 * page_median)
        page["raw"] = (
            valid & ((page[column] - page_median) / page_wiggle > LAT_THRESH)
        ).astype(int)
        page["flag"] = page["raw"].rolling(CONSEC).sum() == CONSEC

        page_window = (page["time"] >= fault["start"]) & (page["time"] <= fault["end"])
        page_hits = page[page["flag"] & page_window]
        page_false = page[
            page["flag"]
            & ~page_window
            & (page["time"] >= start_time + pd.Timedelta(seconds=BASELINE_S))
        ]

        page_latency[column] = {
            "detected": not page_hits.empty,
            "delay_s": (
                (page_hits["time"].min() - fault["start"]).total_seconds()
                if not page_hits.empty
                else None
            ),
            "false_alarm_rows": len(page_false),
            "timeouts": int((page.loc[fault_window, column] >= 5.0).sum()),
            "timeouts_after_fault": int(
                (page.loc[page["time"] > fault["end"], column] >= 5.0).sum()
            ),
        }

    return {
        "experiment": manifest_row["file"],
        "v1_detected": not v1_hits.empty,
        "v1_delay": (
            (v1_hits["time"].min() - fault["start"]).total_seconds()
            if not v1_hits.empty
            else None
        ),
        "v1_first": (
            v1_all_flags["service"].iloc[0] if not v1_all_flags.empty else "-"
        ),
        "v1_correct_first": (
            not v1_all_flags.empty
            and v1_all_flags["service"].iloc[0] == fault["service"]
        ),
        "v1_false_rows": len(v1_false),
        "v2_resource_detected": not v2_hits.empty,
        "v2_resource_delay": (
            (v2_hits["time"].min() - fault["start"]).total_seconds()
            if not v2_hits.empty
            else None
        ),
        "v2_first": (
            v2_all_flags["service"].iloc[0] if not v2_all_flags.empty else "-"
        ),
        "v2_correct_first": (
            not v2_all_flags.empty
            and v2_all_flags["service"].iloc[0] == fault["service"]
        ),
        "v2_resource_false_rows": len(v2_false),
        "v2_latency_detected": not latency_hits.empty,
        "v2_latency_delay": (
            (latency_hits["time"].min() - fault["start"]).total_seconds()
            if not latency_hits.empty
            else None
        ),
        "v2_latency_false_rows": len(latency_false),
        "v2_latency_false_episodes": len(latency_false_episodes),
        "timeouts_during_fault": {
            column: metrics["timeouts"] for column, metrics in page_latency.items()
        },
        "timeouts_after_fault": {
            column: metrics["timeouts_after_fault"]
            for column, metrics in page_latency.items()
        },
        "page_latency": page_latency,
        "page_latency_columns": page_columns,
    }


def main():
    manifest = pd.read_csv(MANIFEST, dtype=str).fillna("")
    required_manifest = {"file", "fault", "service", "role"}
    missing_manifest = required_manifest - set(manifest.columns)
    if missing_manifest:
        raise ValueError(f"Manifest missing columns: {sorted(missing_manifest)}")

    test_runs = manifest[manifest["role"] == "test"]
    if test_runs.empty:
        raise ValueError("Manifest has no rows with role='test'")

    faults = pd.read_csv(FAULTS, parse_dates=["start", "end"])
    results: list[EvaluationResult] = [
        evaluate_run(row, faults) for _, row in test_runs.iterrows()
    ]
    output = pd.DataFrame(results)

    print(f"Test runs evaluated: {len(output)}")
    print(
        output[
            [
                "experiment",
                "v1_detected",
                "v1_delay",
                "v1_first",
                "v1_correct_first",
                "v1_false_rows",
                "v2_resource_detected",
                "v2_resource_delay",
                "v2_first",
                "v2_correct_first",
                "v2_resource_false_rows",
                "v2_latency_detected",
                "v2_latency_delay",
                "v2_latency_false_rows",
                "v2_latency_false_episodes",
            ]
        ].to_string(index=False)
    )

    count = len(output)
    print()
    print(
        f"v1 resource detector: {output['v1_detected'].sum()} of {count} detected; "
        f"culprit first {output['v1_correct_first'].sum()} of {count}; "
        f"false-alarm rows {output['v1_false_rows'].sum()}"
    )
    print(
        f"v2 resource detector: {output['v2_resource_detected'].sum()} of {count} detected; "
        f"culprit first {output['v2_correct_first'].sum()} of {count}; "
        f"false-alarm rows {output['v2_resource_false_rows'].sum()}"
    )
    print(
        f"v2 home-latency detector: {output['v2_latency_detected'].sum()} of {count} "
        f"detected; false-alarm episodes "
        f"{output['v2_latency_false_episodes'].sum()}; "
        f"flagged samples outside fault windows "
        f"{output['v2_latency_false_rows'].sum()}"
    )
    combined = output["v2_resource_detected"] | output["v2_latency_detected"]
    print(f"v2 resource or home-latency detector: {combined.sum()} of {count} detected")
    print()
    print("Timeouts during fault windows (5.0 means request timeout):")
    for row in results:
        counts = ", ".join(
            f"{column}={number}" for column, number in row["timeouts_during_fault"].items()
        )
        print(f"  {row['experiment']}: {counts or 'no latency columns'}")

    print("Timeouts after fault windows (remaining recording):")
    for row in results:
        counts = ", ".join(
            f"{column}={number}" for column, number in row["timeouts_after_fault"].items()
        )
        print(f"  {row['experiment']}: {counts or 'no latency columns'}")

    print()
    print("Page-specific latency detection:")
    for row in results:
        for column, metrics in row["page_latency"].items():
            print(
                f"  {row['experiment']} {column}: "
                f"detected={metrics['detected']} "
                f"delay_s={metrics['delay_s']} "
                f"false_alarm_rows={metrics['false_alarm_rows']} "
                f"timeouts={metrics['timeouts']}"
            )

    missing_pages = [
        row["experiment"]
        for row in results
        if "latency_product_s" not in row["page_latency_columns"]
        or "latency_cart_s" not in row["page_latency_columns"]
    ]
    if missing_pages:
        print()
        print(
            "Page-specific product/cart latency is unavailable in these test runs: "
            + ", ".join(missing_pages)
        )


if __name__ == "__main__":
    main()
