import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
faults = pd.read_csv(ROOT / "eval" / "faults.csv", parse_dates=["start", "end"])
faults = faults[faults["fault"] == "net_delay"]

PAGES = ["latency_s", "latency_product_s", "latency_cart_s"]
NAMES = {"latency_s": "home", "latency_product_s": "product", "latency_cart_s": "cart"}

for path in sorted((ROOT / "data").glob("data_net_delay_*.csv")):
    df = pd.read_csv(path, parse_dates=["time"])
    if "latency_product_s" not in df.columns:
        continue  # older run, only has the home page probe
    lat = df.drop_duplicates("time").set_index("time")[PAGES]
    hit = faults[(faults["start"] >= lat.index.min()) & (faults["end"] <= lat.index.max())]
    if hit.empty:
        print(path.name, "-> no matching row in faults.csv")
        continue
    f = hit.iloc[-1]
    before = lat[lat.index < f["start"]]
    during = lat[(lat.index >= f["start"]) & (lat.index <= f["end"])]
    print(f"\n{path.name}  (delayed service: {f['service']})")
    for col in PAGES:
        timeouts = int((lat[col] >= 5.0).sum())
        print(f"  {NAMES[col]:8s} median before {before[col].median():.3f}  "
              f"during {during[col].median():.3f}  max during {during[col].max():.3f}"
              f"  timeouts {timeouts}")