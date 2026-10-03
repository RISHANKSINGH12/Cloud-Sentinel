import sys

import pandas as pd

d = pd.read_csv(sys.argv[1], parse_dates=["time"])
faults = pd.read_csv("eval/faults.csv", parse_dates=["start", "end"])

# find the fault row that falls inside this recording
inside = faults[(faults["start"] >= d["time"].min()) & (faults["end"] <= d["time"].max())]
if inside.empty:
    sys.exit("No fault row in faults.csv falls inside this recording.")
f = inside.iloc[-1]
svc = f["service"]
print(f"fault: {f['fault']} on {svc}  ({f['start']} to {f['end']})")


def phases(df, col):
    before = df[df["time"] < f["start"]][col].median()
    during = df[(df["time"] >= f["start"]) & (df["time"] <= f["end"])][col].median()
    after = df[df["time"] > f["end"]][col].median()
    return before, during, after


mine = d[d["service"] == svc]
print(f"rows for {svc}: {len(mine)}")
for col in ["cpu_cores", "memory_mb"]:
    b, u, a = phases(mine, col)
    print(f"{svc} {col:10s} before {b:.4f}  during {u:.4f}  after {a:.4f}")

if "latency_s" in d.columns:
    b, u, a = phases(d[d["service"] == "frontend"], "latency_s")
    print(f"shop latency_s        before {b:.4f}  during {u:.4f}  after {a:.4f}")
