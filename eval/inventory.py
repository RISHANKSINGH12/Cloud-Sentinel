import glob
import pandas as pd

faults = pd.read_csv("eval/faults.csv", parse_dates=["start", "end"])

for path in sorted(glob.glob("data/data_*.csv")):
    df = pd.read_csv(path, parse_dates=["time"])
    t0, t1 = df["time"].min(), df["time"].max()
    hits = faults[(faults["start"] >= t0) & (faults["end"] <= t1)]
    cut = faults[(faults["start"] <= t1) & (faults["end"] >= t0)
                 & ~faults.index.isin(hits.index)]
    desc = ", ".join(f"{r.fault}/{r.service}" for r in hits.itertuples()) or "none"
    print(f"{path[5:]:45s} {t0:%H:%M:%S}-{t1:%H:%M:%S} "
          f"{(t1 - t0).seconds:4d}s  full faults: {desc}"
          + (f"  PARTIAL: {len(cut)}" if len(cut) else ""))