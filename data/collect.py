import csv
import sys
import time
from datetime import datetime

import requests

URL = "http://localhost:9090/api/v1/query"
SHOP = "http://localhost:8080"

# page -> URL. Each page depends on a different set of services.
PAGES = {
    "latency_s": SHOP + "/",
    "latency_product_s": SHOP + "/product/OLJCESPC7Z",
    "latency_cart_s": SHOP + "/cart",
}

# metric name -> the PromQL question that measures it, per pod
QUERIES = {
    "memory_mb": 'sum by (pod) (container_memory_working_set_bytes{namespace="default", container!=""}) / 1024 / 1024',
    "cpu_cores": 'sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="default", container!=""}[1m]))',
    "restarts": 'sum by (pod) (kube_pod_container_status_restarts_total{namespace="default"})',
}

HEADER = ["time", "service", "memory_mb", "cpu_cores", "restarts",
          "latency_s", "latency_product_s", "latency_cart_s", "label"]


def service_name(pod):
    # "cartservice-574c7f4cdd-2dck8" -> "cartservice"
    return pod.rsplit("-", 2)[0]


def ask(query):
    r = requests.get(URL, params={"query": query}, timeout=10)
    r.raise_for_status()
    return r.json()["data"]["result"]


def measure(url):
    # seconds the page takes to answer; 5.0 means it did not answer in time
    start = time.time()
    try:
        requests.get(url, timeout=5)
    except requests.RequestException:
        return 5.0
    return round(time.time() - start, 4)


def collect_once(label):
    now = datetime.now().isoformat(timespec="seconds")
    lat = {name: measure(url) for name, url in PAGES.items()}
    rows = {}
    for metric, query in QUERIES.items():
        for item in ask(query):
            svc = service_name(item["metric"]["pod"])
            rows.setdefault(svc, {})[metric] = float(item["value"][1])
    return [
        [now, svc, vals.get("memory_mb", 0), vals.get("cpu_cores", 0), vals.get("restarts", 0),
         lat["latency_s"], lat["latency_product_s"], lat["latency_cart_s"], label]
        for svc, vals in rows.items()
    ]


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "healthy"
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    out = f"data_{label}.csv"

    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        end = time.time() + minutes * 60
        while time.time() < end:
            w.writerows(collect_once(label))
            f.flush()
            print(f"{datetime.now():%H:%M:%S} collected")
            time.sleep(5)
    print("saved", out)