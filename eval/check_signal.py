import pandas as pd

faults = pd.read_csv("eval/faults.csv", parse_dates=["start", "end"])

runs = [
    ("cpu_hog", "productcatalogservice", "data_run1"),
    ("mem_leak", "currencyservice", "data_run3"),
    ("net_delay", "productcatalogservice", "data_run5"),
    ("cpu_hog", "cartservice", "data_cpu_hog_cartservice_1"),
    ("cpu_hog", "currencyservice", "data_cpu_hog_currencyservice_1"),
    ("cpu_hog", "recommendationservice", "data_cpu_hog_recommendationservice_1"),
    ("cpu_hog", "frontend", "data_cpu_hog_frontend_1"),
    ("cpu_hog", "checkoutservice", "data_cpu_hog_checkoutservice_1"),
    ("mem_leak", "cartservice", "data_mem_leak_cartservice_1"),
    ("mem_leak", "recommendationservice", "data_mem_leak_recommendationservice_1"),
    ("mem_leak", "checkoutservice", "data_mem_leak_checkoutservice_2"),
    ("mem_leak", "paymentservice", "data_mem_leak_paymentservice_1"),
    ("net_delay", "cartservice", "data_net_delay_cartservice_1"),
    ("net_delay", "paymentservice", "data_net_delay_paymentservice_1"),
]

for fault, svc, name in runs:
    df = pd.read_csv(f"data/{name}.csv", parse_dates=["time"])
    row = faults[(faults["fault"] == fault) & (faults["service"] == svc)
                 & (faults["start"] >= df["time"].min()) & (faults["end"] <= df["time"].max())].iloc[0]
    mine = df[df["service"] == svc]
    b = mine[mine["time"] < row["start"]]
    d = mine[(mine["time"] >= row["start"]) & (mine["time"] <= row["end"])]
    a = mine[mine["time"] > row["end"]]
    print(f"\n{fault} on {svc}  ({name})")
    for col in ["cpu_cores", "memory_mb"]:
        print(f"  {col:10s} before {b[col].mean():8.4f}  during {d[col].mean():8.4f}  max {d[col].max():8.4f}  after {a[col].mean():8.4f}")
    print(f"  restarts   before {b['restarts'].max():4.0f}  during {d['restarts'].max():4.0f}  after {a['restarts'].max():4.0f}")