import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
faults = pd.read_csv(ROOT / "eval" / "faults.csv", parse_dates=["start", "end"])
faults = faults[faults["fault"] == "net_delay"]

for path in sorted((ROOT / "data").glob("data_*net_delay*.csv")) + [ROOT / "data" / "data_run5.csv"]:
    df = pd.read_csv(path, parse_dates=["time"])
    if "latency_s" not in df.columns:
        print(path.name, "-> no latency_s column")
        continue
    # latency is shared by all services, so one row per timestamp is enough
    lat = df.drop_duplicates("time").set_index("time")["latency_s"]
    hit = faults[(faults["start"] >= lat.index.min()) & (faults["end"] <= lat.index.max())]
    if hit.empty:
        print(path.name, "-> no matching row in faults.csv")
        continue
    f = hit.iloc[-1]
    before = lat[lat.index < f["start"]]
    during = lat[(lat.index >= f["start"]) & (lat.index <= f["end"])]
    after = lat[lat.index > f["end"]]
    print(f"{path.name}  ({f['service']})")
    print(f"  latency median  before {before.median():.3f}  during {during.median():.3f}  "
          f"max {during.max():.3f}  after {after.median():.3f}")