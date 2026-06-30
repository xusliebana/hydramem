# Telemetry and Metrics

HydraMem records per-call telemetry in a local SQLite database under the home
directory. The metrics capture tokens injected versus a naive RAG baseline,
yielding an auditable token-savings dashboard. Nothing leaves the machine unless
the user explicitly opts in to share anonymous aggregate metrics.
