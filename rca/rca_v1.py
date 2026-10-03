import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
FAULTS_PATH = ROOT / "eval" / "faults.csv"

BASELINE_S = 50
MIN_CAUSE_SCORE = 1.5
FLOORS = {"cpu_cores": 0.01, "memory_mb": 1.0}
LATENCY_COLUMNS = ["latency_s", "latency_product_s", "latency_cart_s"]


def find_fault_window(frame, faults):
    start = frame["time"].min()
    end = frame["time"].max()
    matches = faults[
        (faults["start"] >= start)
        & (faults["end"] <= end)
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one fault window inside this recording; "
            f"found {len(matches)}."
        )

    return matches.iloc[0]


def service_scores(frame, baseline_window, fault_window):
    baseline = frame[
        (frame["time"] >= baseline_window[0])
        & (frame["time"] < baseline_window[1])
    ]
    during = frame[
        (frame["time"] >= fault_window[0])
        & (frame["time"] <= fault_window[1])
    ]

    if baseline.empty:
        raise ValueError("No metric rows found in the 50-second pre-fault baseline.")
    if during.empty:
        raise ValueError("No metric rows found during the fault window.")

    scores = []
    for service, during_group in during.groupby("service"):
        baseline_group = baseline[baseline["service"] == service]
        if baseline_group.empty:
            continue

        evidence = {}
        for column, floor in FLOORS.items():
            before = baseline_group[column].median()
            during_value = during_group[column].median()
            mad = (baseline_group[column] - before).abs().median() * 1.4826
            wiggle = max(mad, floor, 0.1 * abs(before), 1e-9)
            evidence[column] = {
                "before": before,
                "during": during_value,
                "rise_score": max(0.0, (during_value - before) / wiggle),
            }

        score = max(item["rise_score"] for item in evidence.values())
        scores.append((service, score, evidence))

    return sorted(scores, key=lambda item: item[1], reverse=True)


def report_page_latency(frame, baseline_window, fault_window):
    columns = [column for column in LATENCY_COLUMNS if column in frame.columns]
    if not columns:
        print("No page-latency columns are available.")
        return

    unique_times = frame.drop_duplicates("time")
    baseline_mask = (
        (unique_times["time"] >= baseline_window[0])
        & (unique_times["time"] < baseline_window[1])
    )
    fault_mask = (
        (unique_times["time"] >= fault_window[0])
        & (unique_times["time"] <= fault_window[1])
    )

    print("\nPage latency (successful-request medians; timeouts counted separately):")
    for column in columns:
        baseline_values = unique_times.loc[baseline_mask, column]
        fault_values = unique_times.loc[fault_mask, column]
        baseline_success = baseline_values[baseline_values < 5.0]
        fault_success = fault_values[fault_values < 5.0]
        timeouts = int((fault_values >= 5.0).sum())
        after_fault_values = unique_times.loc[
            unique_times["time"] > fault_window[1], column
        ]
        timeouts_after_fault = int((after_fault_values >= 5.0).sum())

        before = (
            f"{baseline_success.median():.3f}s"
            if not baseline_success.empty
            else "unavailable"
        )
        during = (
            f"{fault_success.median():.3f}s"
            if not fault_success.empty
            else "unavailable"
        )
        print(
            f"  {column}: before={before}, during={during}, "
            f"timeouts_during_fault={timeouts}, "
            f"timeouts_after_fault={timeouts_after_fault}"
        )


def build_report(path, fault, baseline_window, fault_window, ranked, frame):
    candidates = [
        {
            "service": service,
            "score": float(score),
            "evidence": {
                metric: {
                    key: float(value)
                    for key, value in values.items()
                }
                for metric, values in evidence.items()
            },
        }
        for service, score, evidence in ranked
    ]
    selected = candidates[0] if candidates else None
    supported = selected is not None and selected["score"] >= MIN_CAUSE_SCORE

    unique_times = frame.drop_duplicates("time")
    baseline_mask = (
        (unique_times["time"] >= baseline_window[0])
        & (unique_times["time"] < baseline_window[1])
    )
    fault_mask = (
        (unique_times["time"] >= fault_window[0])
        & (unique_times["time"] <= fault_window[1])
    )
    page_latency = {}
    for column in LATENCY_COLUMNS:
        if column not in unique_times.columns:
            continue
        baseline_values = unique_times.loc[baseline_mask, column]
        fault_values = unique_times.loc[fault_mask, column]
        after_fault_values = unique_times.loc[
            unique_times["time"] > fault_window[1], column
        ]
        baseline_success = baseline_values[baseline_values < 5.0]
        fault_success = fault_values[fault_values < 5.0]
        before = (
            float(baseline_success.median())
            if not baseline_success.empty
            else None
        )
        during = (
            float(fault_success.median())
            if not fault_success.empty
            else None
        )
        page_latency[column] = {
            "before_seconds": before,
            "during_seconds": during,
            "increase_seconds": (
                during - before
                if before is not None and during is not None
                else None
            ),
            "timeouts": int((fault_values >= 5.0).sum()),
            "timeouts_after_fault": int((after_fault_values >= 5.0).sum()),
        }

    return {
        "schema_version": 1,
        "recording": path.name,
        "fault_window": {
            "start": fault["start"].isoformat(),
            "end": fault["end"].isoformat(),
        },
        "resource_ranking": candidates,
        "resource_decision": {
            "status": "candidate" if supported else "unknown",
            "threshold": MIN_CAUSE_SCORE,
            "service": selected["service"] if supported and selected is not None else None,
            "score": selected["score"] if selected else None,
        },
        "page_latency": page_latency,
        "interpretation": (
            "Evidence ranking only; not a probability or proof of cause. "
            "Page latency is not mapped to a service automatically."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Rank possible service causes from one recorded experiment."
    )
    parser.add_argument(
        "csv",
        help="Experiment CSV path, for example data\\data_net_delay_cartservice_2.csv",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable RCA evidence instead of the human-readable report.",
    )
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"Experiment CSV not found: {path}")

    frame = pd.read_csv(path, parse_dates=["time"])
    required = {"time", "service", "cpu_cores", "memory_mb"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Experiment CSV is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Experiment CSV has no data rows.")

    faults = pd.read_csv(FAULTS_PATH, parse_dates=["start", "end"])
    fault = find_fault_window(frame, faults)

    baseline_window = (
        fault["start"] - pd.Timedelta(seconds=BASELINE_S),
        fault["start"],
    )
    fault_window = (fault["start"], fault["end"])

    ranked = service_scores(frame, baseline_window, fault_window)
    if args.json:
        print(
            json.dumps(
                build_report(path, fault, baseline_window, fault_window, ranked, frame),
                indent=2,
            )
        )
        return

    print(f"Recording: {path.name}")
    print(f"Fault window: {fault['start']} to {fault['end']}")
    print("The labeled culprit is not used to calculate the service ranking.")
    print(
        f"\nService ranking by largest positive CPU/memory change "
        f"(50 seconds before fault vs fault window):"
    )

    if not ranked:
        print("  No services have both baseline and fault-window metrics.")
    else:
        for rank, (service, score, evidence) in enumerate(ranked, start=1):
            cpu = evidence["cpu_cores"]
            memory = evidence["memory_mb"]
            print(
                f"  {rank}. {service}: score={score:.2f} "
                f"(CPU {cpu['before']:.4f}->{cpu['during']:.4f}, "
                f"rise score {cpu['rise_score']:.2f}; "
                f"memory {memory['before']:.2f}->{memory['during']:.2f} MB, "
                f"rise score {memory['rise_score']:.2f})"
            )
    if not ranked:
        print("\nRCA result: UNKNOWN (no comparable service metrics).")
    elif ranked[0][1] < MIN_CAUSE_SCORE:
        service, score, _ = ranked[0]
        print(
            f"\nRCA result: UNKNOWN (top resource candidate {service} "
            f"scored {score:.2f}, below the provisional "
            f"{MIN_CAUSE_SCORE:.2f} cutoff)."
        )
    else:
        service, score, _ = ranked[0]
        print(
            f"\nRCA result: {service} is the leading resource-supported "
            f"candidate (score {score:.2f})."
        )
    report_page_latency(frame, baseline_window, fault_window)
    print(
        "\nInterpretation: this is an evidence ranking, not a probability or "
        "proof of cause. Page latency is reported separately and is not mapped "
        "to a service automatically."
    )


if __name__ == "__main__":
    main()