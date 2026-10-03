import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RCA_SCRIPT = ROOT / "rca" / "rca_v1.py"


def load_rca_report(csv_path):
    result = subprocess.run(
        [sys.executable, str(RCA_SCRIPT), str(csv_path), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("RCA did not return valid JSON output.") from error
    if report.get("schema_version") != 1:
        raise ValueError("Unsupported RCA report schema.")
    return report


def recommendation(report):
    decision = report["resource_decision"]
    if decision["status"] != "candidate" or not decision["service"]:
        return (
            "NO ACTION: cause unknown or resource evidence is below threshold. "
            "Review traces/logs and continue monitoring; no change is suggested."
        )

    candidate = next(
        (
            item
            for item in report["resource_ranking"]
            if item["service"] == decision["service"]
        ),
        None,
    )
    if candidate is None:
        raise ValueError("RCA decision candidate is missing from its ranking.")

    evidence = candidate["evidence"]
    cpu_score = evidence["cpu_cores"]["rise_score"]
    memory_score = evidence["memory_mb"]["rise_score"]
    if cpu_score >= memory_score:
        next_step = (
            "inspect CPU saturation and recent workload; consider capacity "
            "adjustments only after operator review"
        )
    else:
        next_step = (
            "inspect memory growth and limits; any restart or resource-limit "
            "change requires operator review"
        )

    return (
        f"REVIEW ONLY: investigate {decision['service']} "
        f"(resource score {decision['score']:.2f}); {next_step}. "
        "No action is executed."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Print a remediation recommendation without changing the cluster."
    )
    parser.add_argument(
        "csv",
        help="Experiment CSV path, for example data\\data_net_delay_cartservice_2.csv",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    if not csv_path.is_file():
        raise FileNotFoundError(f"Experiment CSV not found: {csv_path}")

    report = load_rca_report(csv_path)
    print(f"Dry-run report for: {report['recording']}")
    print("Mode: recommendation only; no cluster action will be executed.")
    print(f"RCA status: {report['resource_decision']['status']}")
    print(f"Recommendation: {recommendation(report)}")
    print("Page latency evidence:")
    if not report["page_latency"]:
        print("  unavailable")
    for page, metrics in report["page_latency"].items():
        before = metrics["before_seconds"]
        during = metrics["during_seconds"]
        increase = metrics["increase_seconds"]
        timeouts_during = metrics["timeouts"]
        timeouts_after = metrics["timeouts_after_fault"]
        before_text = f"{before:.3f}s" if before is not None else "unavailable"
        during_text = f"{during:.3f}s" if during is not None else "unavailable"
        increase_text = f"{increase:+.3f}s" if increase is not None else "unavailable"
        print(
            f"  {page}: before={before_text}, during={during_text}, "
            f"change={increase_text}, timeouts_during_fault={timeouts_during}, "
            f"timeouts_after_fault={timeouts_after}"
        )


if __name__ == "__main__":
    main()
