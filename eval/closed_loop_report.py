"""Summarize closed-loop runs: detection delay, recovery time, correct target.

Joins eval/heal_log.jsonl (written by remediator/live_heal.py) with
eval/faults.csv (written by the injectors, which know the true fault).
Unassisted recovery is the injected window length, because without the
controller the injector only removes the fault by deleting the pod at the end.

Two controller timings are reported separately:
  fix_time_s       fault start -> replacement pod Ready (the fault is gone)
  recovery_time_s  fault start -> controller confirmed recovery (includes the
                   settle + verify watch, so it is longer than the real fix)
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "eval" / "heal_log.jsonl"
FAULTS = ROOT / "eval" / "faults.csv"
OUT = ROOT / "eval" / "closed_loop_results.csv"
GRACE_S = 30


def load_events(path):
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return pd.DataFrame(events)


def match_fault(faults, t_detect):
    hits = faults[(faults["start"] <= t_detect)
                  & (t_detect <= faults["end"] + pd.Timedelta(seconds=GRACE_S))]
    return hits.iloc[-1] if len(hits) else None


def restart_time(events, service, t_detect, t_end):
    """Time of the successful restart of `service` between detection and the verdict."""
    if "time" not in events.columns:
        return None
    hits = events[(events["event"] == "restart") & (events["service"] == service)]
    if "ok" in hits.columns:
        hits = hits[hits["ok"] == True]  # noqa: E712
    times = pd.to_datetime(hits["time"])
    times = times[(times >= t_detect) & (times <= t_end)]
    return times.max() if len(times) else None


def build_results(events, faults):
    rows = []
    done = events[events["event"].isin(["recovered", "escalate"])
                  & events.get("t_detect", pd.Series(dtype=object)).notna()]
    for _, e in done.iterrows():
        t_detect = pd.Timestamp(e["t_detect"])
        fault = match_fault(faults, t_detect)
        if fault is None:
            continue
        recovered = e["event"] == "recovered"
        t_rec = pd.Timestamp(e["t_recovered"]) if recovered else None
        t_fixed = restart_time(events, e["service"], t_detect, pd.Timestamp(e["time"]))
        rows.append({
            "fault": fault["fault"],
            "true_service": fault["service"],
            "chosen_service": e["service"],
            "correct_target": e["service"] == fault["service"],
            "detect_delay_s": (t_detect - fault["start"]).total_seconds(),
            "recovered": recovered,
            "fix_time_s": (t_fixed - fault["start"]).total_seconds() if t_fixed is not None else None,
            "recovery_time_s": (t_rec - fault["start"]).total_seconds() if recovered else None,
            "unassisted_s": (fault["end"] - fault["start"]).total_seconds(),
        })
    return pd.DataFrame(rows)


def main():
    if not LOG.exists():
        raise SystemExit(f"No closed-loop log yet: {LOG}")
    faults = pd.read_csv(FAULTS, parse_dates=["start", "end"])
    results = build_results(load_events(LOG), faults)
    if results.empty:
        raise SystemExit("No completed heal attempts matched a fault window.")
    results.to_csv(OUT, index=False)
    print(results.to_string(index=False))
    n = len(results)
    print(f"\nattempts: {n}   correct target: {int(results['correct_target'].sum())}/{n}"
          f"   recovered: {int(results['recovered'].sum())}/{n}")
    ok = results[results["recovered"]]
    if len(ok):
        print(f"median detection delay: {results['detect_delay_s'].median():.0f}s   "
              f"unassisted baseline: {ok['unassisted_s'].median():.0f}s")
        fixed = ok["fix_time_s"].dropna()
        if len(fixed):
            print(f"median time to fix (fault gone): {fixed.median():.0f}s   "
                  f"median time to confirm recovery: {ok['recovery_time_s'].median():.0f}s")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()