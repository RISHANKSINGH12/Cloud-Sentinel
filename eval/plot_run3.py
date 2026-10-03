import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/data_run3.csv", parse_dates=["time"])
fault = pd.read_csv("eval/faults.csv", parse_dates=["start", "end"]).iloc[-1]
svc = fault["service"]

mine = df[df["service"] == svc]
others = df[df["service"] != svc]

fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

for ax, col, title in [(axes[0], "cpu_cores", "CPU (cores)"),
                       (axes[1], "memory_mb", "Memory (MB)")]:
    for name, g in others.groupby("service"):
        ax.plot(g["time"], g[col], color="lightgray", linewidth=1)
    ax.plot(mine["time"], mine[col], color="red", linewidth=2, label=svc)
    ax.axvspan(fault["start"], fault["end"], color="orange", alpha=0.2, label="fault window")
    ax.set_title(title)
    ax.legend(loc="upper left")

plt.tight_layout()
plt.savefig("eval/run3_mem_leak.png", dpi=120)
print("saved eval/run3_mem_leak.png")

# average CPU for the faulty service: before / during / after the fault
before = mine[mine["time"] < fault["start"]]["cpu_cores"].mean()
during = mine[(mine["time"] >= fault["start"]) & (mine["time"] <= fault["end"])]["cpu_cores"].mean()
after = mine[mine["time"] > fault["end"]]["cpu_cores"].mean()
print(f"{svc} average CPU  before: {before:.4f}  during: {during:.4f}  after: {after:.4f}")
