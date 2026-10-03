"""Replay recorded held-out runs through the streaming detector.

Checks, without a cluster, that the online detector used by the closed loop
(detector/online.py) finds the faults, picks the right service when it has to
choose blind, and stays quiet outside the fault window.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from detector.online import OnlineDetector  # noqa: E402


def replay(path, fault):
    df = pd.read_csv(path, parse_dates=["time"]).sort_values("time")
    detector = OnlineDetector()
    first = None
    outside = 0
    for t, group in df.groupby("time"):
        flagged = []
        for row in group.itertuples():
            reading = detector.update(t.to_pydatetime(), row.service,
                                      row.memory_mb, row.cpu_cores)
            if reading and reading.flag:
                flagged.append((reading.z, row.service))
        in_win = fault["start"] <= t <= fault["end"]
        if flagged and in_win and first is None:
            first = (t, max(flagged)[1])
        if flagged and not in_win and t > fault["end"] + pd.Timedelta(seconds=15):
            outside += 1
    return first, outside


def main():
    manifest = pd.read_csv(ROOT / "eval" / "manifest.csv")
    faults = pd.read_csv(ROOT / "eval" / "faults.csv", parse_dates=["start", "end"])
    tests = manifest[manifest["role"] == "test"]
    hits = correct = 0
    print(f"{'recording':45} {'detected':9} {'delay_s':8} {'chosen':22} outside")
    for _, m in tests.iterrows():
        path = ROOT / "data" / m["file"]
        frame = pd.read_csv(path, parse_dates=["time"])
        t0, t1 = frame["time"].min(), frame["time"].max()
        match = faults[(faults["fault"] == m["fault"]) & (faults["service"] == m["service"])
                       & (faults["start"] >= t0) & (faults["end"] <= t1)]
        fault = match.iloc[0]
        first, outside = replay(path, fault)
        if first:
            hits += 1
            correct += first[1] == m["service"]
        delay = (first[0] - fault["start"]).total_seconds() if first else None
        print(f"{m['file']:45} {str(bool(first)):9} {str(delay):8} "
              f"{(first[1] if first else '-'):22} {outside}")
    print(f"\ndetected {hits}/{len(tests)}, correct blind target {correct}/{hits or 1}")


if __name__ == "__main__":
    main()
