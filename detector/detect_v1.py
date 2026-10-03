from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BASELINE_S = 50    # first seconds of every run are healthy: used to learn "normal"
THRESH = 6.0       # how many typical wiggles away counts as abnormal
CONSEC = 3         # readings in a row needed before flagging
GRACE_S = 30       # after a fault ends, ignore flags for this long (pod restart noise)
FLOORS = {"cpu_cores": 0.01, "memory_mb": 1.0}

faults = pd.read_csv(ROOT / "eval" / "faults.csv", parse_dates=["start", "end"])


def learn_normal(base):
    """per service and metric: (median, wiggle)"""
    params = {}
    for svc, g in base.groupby("service"):
        for col, floor in FLOORS.items():
            med = g[col].median()
            mad = (g[col] - med).abs().median() * 1.4826
            params[(svc, col)] = (med, max(mad, floor, 0.1 * abs(med)))
    return params


def score(df, params):
    z = pd.Series(0.0, index=df.index)
    for col in FLOORS:
        med = df.apply(lambda r: params.get((r["service"], col), (0, 1))[0], axis=1)
        wig = df.apply(lambda r: params.get((r["service"], col), (0, 1))[1], axis=1)
        z = pd.concat([z, (df[col] - med).abs() / wig], axis=1).max(axis=1)
    return z


results = []
diag = []   # when did the false alarms happen?

for path in sorted(DATA.glob("data_*_1.csv")):
    df = pd.read_csv(path, parse_dates=["time"]).sort_values("time").reset_index(drop=True)
    name = df["label"].iloc[0]                       # e.g. cpu_hog_currencyservice_1
    key = name.rsplit("_", 1)[0]                     # cpu_hog_currencyservice
    t0 = df["time"].min()

    f = None
    for _, row in faults.iterrows():
        if f"{row['fault']}_{row['service']}" == key and t0 <= row["start"] <= df["time"].max():
            f = row
    if f is None:
        print("no matching fault row for", path.name)
        continue

    base = df[df["time"] < t0 + pd.Timedelta(seconds=BASELINE_S)]
    params = learn_normal(base)

    df["z"] = score(df, params)
    df["raw"] = (df["z"] > THRESH).astype(int)
    df["flag"] = df.groupby("service")["raw"].transform(
        lambda s: s.rolling(CONSEC).sum() == CONSEC)

    in_win = (df["time"] >= f["start"]) & (df["time"] <= f["end"])
    faulty = df["service"] == f["service"]

    hit = df[df["flag"] & faulty & in_win]
    detected = len(hit) > 0
    delay = (hit["time"].min() - f["start"]).total_seconds() if detected else None

    first_in_win = df[df["flag"] & in_win].sort_values("time")
    first_svc = first_in_win["service"].iloc[0] if len(first_in_win) else "-"

    grace = (df["time"] > f["end"]) & (df["time"] <= f["end"] + pd.Timedelta(seconds=GRACE_S))
    after_base = df["time"] >= t0 + pd.Timedelta(seconds=BASELINE_S)
    false_rows = df[df["flag"] & ~in_win & ~grace & after_base]

    if len(false_rows):
        diag.append({
            "experiment": key,
            "fault_start": f["start"].strftime("%H:%M:%S"),
            "fault_end": f["end"].strftime("%H:%M:%S"),
            "first_false": false_rows["time"].min().strftime("%H:%M:%S"),
            "last_false": false_rows["time"].max().strftime("%H:%M:%S"),
            "before_fault": int((false_rows["time"] < f["start"]).sum()),
            "after_grace": int((false_rows["time"] > f["end"]).sum()),
        })

    results.append({
        "experiment": key,
        "detected": detected,
        "delay_s": delay,
        "first_flagged": first_svc,
        "correct_first": first_svc == f["service"],
        "false_alarm_rows": len(false_rows),
        "false_services": ",".join(sorted(false_rows["service"].unique())) or "-",
    })

out = pd.DataFrame(results)
print(out.to_string(index=False))
print()
print(f"detected {out['detected'].sum()} of {len(out)} faults")
print(f"mean detection delay: {out['delay_s'].mean():.0f} s")
print(f"first flagged service was the true culprit: {out['correct_first'].sum()} of {len(out)}")

print()
print("when the false alarms happened:")
if diag:
    print(pd.DataFrame(diag).to_string(index=False))
else:
    print("none")