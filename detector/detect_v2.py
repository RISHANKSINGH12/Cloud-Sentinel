from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BASELINE_S = 50      # seconds used to learn "normal"
THRESH = 6.0         # typical wiggles away that count as abnormal
CONSEC = 3           # readings in a row before flagging
WARMUP_S = 120       # no flags for a restarted service for this long
DROP_RATIO = 0.5     # memory falling below 50% of previous reading = restart
FLOORS = {"cpu_cores": 0.01, "memory_mb": 1.0}
LAT_FLOOR = 0.05     # minimum latency wiggle (seconds)
LAT_THRESH = 6.0

faults = pd.read_csv(ROOT / "eval" / "faults.csv", parse_dates=["start", "end"])


def learn(g, cols_floors):
    params = {}
    for col, floor in cols_floors.items():
        med = g[col].median()
        mad = (g[col] - med).abs().median() * 1.4826
        params[col] = (med, max(mad, floor, 0.1 * abs(med)))
    return params


def run_service(g, t0):
    """Flag one service's readings. Returns (flag series, list of warm-up windows)."""
    g = g.sort_values("time").reset_index(drop=True)
    params = learn(g[g["time"] < t0 + pd.Timedelta(seconds=BASELINE_S)], FLOORS)
    warm_until = None          # while set, no flags
    relearn_from = None
    warmups = []
    raw = []
    prev_mem = None

    for i, r in g.iterrows():
        t = r["time"]
        # 1) restart detection
        if prev_mem is not None and prev_mem > 5 and r["memory_mb"] < DROP_RATIO * prev_mem:
            warm_until = t + pd.Timedelta(seconds=WARMUP_S)
            relearn_from = warm_until
            warmups.append((t, warm_until))
        prev_mem = r["memory_mb"]

        # 3) re-learn after warm-up
        if relearn_from is not None and t >= relearn_from + pd.Timedelta(seconds=BASELINE_S):
            window = g[(g["time"] >= relearn_from) &
                       (g["time"] < relearn_from + pd.Timedelta(seconds=BASELINE_S))]
            params = learn(window, FLOORS)
            relearn_from = None
            warm_until = None

        # 2) suppress during warm-up and re-learning
        if warm_until is not None:
            raw.append(0)
            continue

        z = max(abs(r[c] - params[c][0]) / params[c][1] for c in FLOORS)
        raw.append(int(z > THRESH))

    g["raw"] = raw
    g["flag"] = g["raw"].rolling(CONSEC).sum() == CONSEC
    return g, warmups


results = []
for path in sorted(DATA.glob("data_*_1.csv")):
    df = pd.read_csv(path, parse_dates=["time"]).sort_values("time").reset_index(drop=True)
    key = df["label"].iloc[0].rsplit("_", 1)[0]
    t0 = df["time"].min()

    f = None
    for _, row in faults.iterrows():
        if f"{row['fault']}_{row['service']}" == key and t0 <= row["start"] <= df["time"].max():
            f = row
    if f is None:
        print("no matching fault row for", path.name)
        continue

    # ---- per-service detection (CPU + memory) ----
    parts, warm = [], {}
    for svc, g in df.groupby("service"):
        gg, w = run_service(g, t0)
        parts.append(gg)
        warm[svc] = w
    flags = pd.concat(parts)

    in_win = (flags["time"] >= f["start"]) & (flags["time"] <= f["end"])
    faulty = flags["service"] == f["service"]
    hit = flags[flags["flag"] & faulty & in_win]
    detected_res = len(hit) > 0
    delay_res = (hit["time"].min() - f["start"]).total_seconds() if detected_res else None

    first = flags[flags["flag"] & in_win].sort_values("time")
    first_svc = first["service"].iloc[0] if len(first) else "-"

    after_base = flags["time"] >= t0 + pd.Timedelta(seconds=BASELINE_S)
    tail = (flags["time"] > f["end"]) & (flags["time"] <= f["end"] + pd.Timedelta(seconds=15))
    false_rows = flags[flags["flag"] & ~in_win & ~tail & after_base]
    # the old pod's end-of-fault replacement is also a restart: it is inside warm[svc]
    # so flags there are already suppressed.

    # ---- shop-wide latency detection ----
    lat = df.drop_duplicates("time")[["time", "latency_s"]].sort_values("time").reset_index(drop=True)
    lb = lat[lat["time"] < t0 + pd.Timedelta(seconds=BASELINE_S)]["latency_s"]
    lmed = lb.median()
    lwig = max((lb - lmed).abs().median() * 1.4826, LAT_FLOOR, 0.1 * lmed)
    successful_latency = lat["latency_s"] < 5.0
    lat["raw"] = (
        successful_latency & ((lat["latency_s"] - lmed) / lwig > LAT_THRESH)
    ).astype(int)
    lat["flag"] = lat["raw"].rolling(CONSEC).sum() == CONSEC
    lat["alarm_start"] = lat["flag"] & ~lat["flag"].shift(fill_value=False)
    lat_in = (lat["time"] >= f["start"]) & (lat["time"] <= f["end"])
    lat_hit = lat[lat["flag"] & lat_in]
    lat_detected = len(lat_hit) > 0
    lat_delay = (lat_hit["time"].min() - f["start"]).total_seconds() if lat_detected else None
    after_base = lat["time"] >= t0 + pd.Timedelta(seconds=BASELINE_S)
    lat_false_rows = int((lat["flag"] & ~lat_in & after_base).sum())
    lat_false_episodes = int((lat["alarm_start"] & ~lat_in & after_base).sum())

    results.append({
        "experiment": key,
        "res_detected": detected_res,
        "res_delay_s": delay_res,
        "culprit_first": first_svc == f["service"],
        "res_false_rows": len(false_rows),
        "lat_detected": lat_detected,
        "lat_delay_s": lat_delay,
        "lat_false_rows": lat_false_rows,
        "lat_false_episodes": lat_false_episodes,
    })

out = pd.DataFrame(results)
print(out.to_string(index=False))
print()
n = len(out)
print(f"resource detector (CPU+memory): {out['res_detected'].sum()} of {n} detected, "
      f"culprit first {out['culprit_first'].sum()} of {n}, "
      f"false-alarm rows {out['res_false_rows'].sum()}")
print(f"latency detector: {out['lat_detected'].sum()} of {n} detected, "
      f"false-alarm episodes {out['lat_false_episodes'].sum()}, "
      f"flagged samples outside fault windows {out['lat_false_rows'].sum()}")
both = (out["res_detected"] | out["lat_detected"]).sum()
print(f"either detector: {both} of {n} faults")