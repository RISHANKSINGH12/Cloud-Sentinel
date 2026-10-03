from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxMetrics:
    cpu_percent: float
    memory_mb: float
    latency_ms: float

    @property
    def healthy(self):
        return (
            self.cpu_percent < 80
            and self.memory_mb < 512
            and self.latency_ms < 500
        )


@dataclass(frozen=True)
class RecoverySimulation:
    fault_kind: str
    target_service: str
    detected_signal: str
    action: str
    before: SandboxMetrics
    after: SandboxMetrics
    recovered: bool


_SCENARIOS = {
    "cpu_hog": (
        SandboxMetrics(cpu_percent=96, memory_mb=180, latency_ms=120),
        "CPU at 96% exceeded the sandbox limit of 80%.",
        "Stop the simulated CPU-intensive task",
        SandboxMetrics(cpu_percent=35, memory_mb=180, latency_ms=120),
    ),
    "mem_leak": (
        SandboxMetrics(cpu_percent=32, memory_mb=768, latency_ms=140),
        "Memory at 768 MB exceeded the sandbox limit of 512 MB.",
        "Restart the simulated worker",
        SandboxMetrics(cpu_percent=20, memory_mb=160, latency_ms=130),
    ),
    "net_delay": (
        SandboxMetrics(cpu_percent=32, memory_mb=180, latency_ms=1200),
        "Latency at 1,200 ms exceeded the sandbox limit of 500 ms.",
        "Clear the simulated network delay",
        SandboxMetrics(cpu_percent=30, memory_mb=180, latency_ms=120),
    ),
}


def simulate_recovery(fault_kind: str, target_service: str) -> RecoverySimulation:
    """Run one allowlisted recovery scenario using in-memory sandbox metrics only."""
    if not target_service.strip():
        raise ValueError("A target service is required for the recovery simulation.")
    try:
        before, signal, action, after = _SCENARIOS[fault_kind]
    except KeyError as error:
        raise ValueError(
            f"No sandbox recovery scenario is defined for {fault_kind!r}."
        ) from error

    if before.healthy:
        raise RuntimeError("The configured sandbox scenario did not trigger detection.")

    return RecoverySimulation(
        fault_kind=fault_kind,
        target_service=target_service,
        detected_signal=signal,
        action=action,
        before=before,
        after=after,
        recovered=after.healthy,
    )
