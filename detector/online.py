"""Streaming resource detector for the closed loop.

This is the online version of the logic in detect_v2.py: the same robust
baseline (median + MAD), the same threshold (6.0 "typical wiggles"), the same
3-readings-in-a-row rule, and the same restart warm-up. The difference is that
it works one reading at a time and never reads eval/faults.csv, so it can run
against a live cluster without knowing when a fault was injected.
"""
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from statistics import median

BASELINE_S = 50      # seconds used to learn "normal"
THRESH = 6.0         # typical wiggles away that count as abnormal
CONSEC = 3           # readings in a row before flagging
WARMUP_S = 120       # no flags for a restarted service for this long
DROP_RATIO = 0.5     # memory falling below 50% of previous reading = restart
FLOORS = {"cpu_cores": 0.01, "memory_mb": 1.0}
LAT_FLOOR = 0.05     # minimum latency wiggle (seconds)
TIMEOUT_S = 5.0      # collector writes 5.0 when a page request times out


def learn(samples):
    """Return {column: (median, wiggle)} learned from a list of reading dicts."""
    params = {}
    for col, floor in FLOORS.items():
        values = [s[col] for s in samples]
        med = median(values)
        mad = median(abs(v - med) for v in values) * 1.4826
        params[col] = (med, max(mad, floor, 0.1 * abs(med)))
    return params


def latency_cutoff(values):
    """Latency above this (successful requests only) counts as abnormal."""
    ok = [v for v in values if v < TIMEOUT_S]
    if not ok:
        return None
    med = median(ok)
    mad = median(abs(v - med) for v in ok) * 1.4826
    return med + THRESH * max(mad, LAT_FLOOR, 0.1 * med)


@dataclass(frozen=True)
class Reading:
    flag: bool      # True once CONSEC abnormal readings happened in a row
    z: float        # distance from normal, in typical wiggles
    metric: str     # which metric is furthest from normal


class _ServiceState:
    def __init__(self, t0):
        self.t0 = t0
        self.baseline = []          # readings used to learn the first baseline
        self.params = None
        self.warm_until = None      # while set, no flags
        self.relearn_from = None
        self.relearn = []
        self.prev_mem = None
        self.raw = deque(maxlen=CONSEC)


class OnlineDetector:
    def __init__(self):
        self._state = {}

    def params(self, service):
        st = self._state.get(service)
        return dict(st.params) if st and st.params else None

    def reset_service(self, service, t):
        """Call after a service was restarted: warm up, then learn a new baseline."""
        st = self._state.get(service)
        if st is None:
            return
        st.warm_until = t + timedelta(seconds=WARMUP_S)
        st.relearn_from = st.warm_until
        st.relearn = []
        st.raw.clear()
        st.prev_mem = None

    def update(self, t, service, memory_mb, cpu_cores):
        """Feed one reading. Returns a Reading, or None while still learning."""
        st = self._state.setdefault(service, _ServiceState(t))
        sample = {"memory_mb": memory_mb, "cpu_cores": cpu_cores}

        # 1) restart detection (memory suddenly drops)
        if (st.prev_mem is not None and st.prev_mem > 5
                and memory_mb < DROP_RATIO * st.prev_mem):
            st.warm_until = t + timedelta(seconds=WARMUP_S)
            st.relearn_from = st.warm_until
            st.relearn = []
            st.raw.clear()
        st.prev_mem = memory_mb

        # 2) first baseline
        if st.params is None:
            st.baseline.append(sample)
            if (t - st.t0).total_seconds() >= BASELINE_S and len(st.baseline) >= 3:
                st.params = learn(st.baseline)
            return None

        # 3) re-learn after a warm-up
        if st.relearn_from is not None:
            if t >= st.relearn_from:
                st.relearn.append(sample)
            window_end = st.relearn_from + timedelta(seconds=BASELINE_S)
            if t >= window_end and len(st.relearn) >= 3:
                st.params = learn(st.relearn)
                st.relearn_from = None
                st.warm_until = None
                st.relearn = []

        # 4) suppress flags while warming up
        if st.warm_until is not None:
            return None

        z, metric = max(
            (abs(sample[c] - st.params[c][0]) / st.params[c][1], c) for c in FLOORS
        )
        st.raw.append(z > THRESH)
        flag = len(st.raw) == CONSEC and all(st.raw)
        return Reading(flag=flag, z=z, metric=metric)
