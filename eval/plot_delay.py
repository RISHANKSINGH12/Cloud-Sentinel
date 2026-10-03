import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/data_run5.csv", parse_dates=["time"])
fault = pd.read_csv("eval/faults.csv", parse_dates=["start", "end"]).iloc[-1]
svc = fault["service"]

mine = df[df["service"] == svc]
others = df[df["service"] != svc]
shop = df[df["service"] == "frontend"]

fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

axes[0].plot(shop["time"], shop["latency_s"], color="red", linewidth=2, label="shop answer time")
axes[0].set_title("Shop answer time (seconds)")

for ax, col, title in [(axes[1], "cpu_cores", "CPU (cores)"),
                       (axes[2], "memory_mb", "Memory (MB)")]:
    for name, g in others.groupby("service"):
        ax.plot(g["time"], g[col], color="lightgray", linewidth=1)
    ax.plot(mine["time"], mine[col], color="red", linewidth=2, label=svc)
    ax.set_title(title)

for ax in axes:
    ax.axvspan(fault["start"], fault["end"], color="orange", alpha=0.2, label="fault window")
    ax.legend(loc="upper left")

plt.tight_layout()
plt.savefig("eval/run5_net_delay.png", dpi=120)
print("saved eval/run5_net_delay.png")

before = shop[shop["time"] < fault["start"]]["latency_s"].mean()
during = shop[(shop["time"] >= fault["start"]) & (shop["time"] <= fault["end"])]["latency_s"].mean()
after = shop[shop["time"] > fault["end"]]["latency_s"].mean()
print(f"shop answer time  before: {before:.3f}  during: {during:.3f}  after: {after:.3f}")