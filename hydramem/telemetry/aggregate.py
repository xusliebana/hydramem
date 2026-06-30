"""Optional aggregate telemetry sender.

Sends only anonymised aggregate numbers to a remote endpoint
when the user has explicitly opted in.  No content, no queries, no code.
Disabled by default.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

CONFIG_PATH: Path = Path.home() / ".hydramem" / "config.json"
AGGREGATE_ENDPOINT = "https://telemetry.hydramem.io/v1/aggregate"  # placeholder


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def is_opted_in() -> bool:
    return bool(_load_config().get("telemetry_opt_in", False))


def set_opt_in(value: bool) -> None:
    cfg = _load_config()
    cfg["telemetry_opt_in"] = value
    _save_config(cfg)


def send_aggregate_if_opted_in(stats: dict) -> bool:
    """
    POST aggregated metrics if the user opted in.

    The payload contains ONLY:
      - version, date, total_tokens_saved, avg_vog_score, total_calls
    Nothing about content, queries, file names, or entity names.

    Returns True if sent successfully.
    """
    if not is_opted_in():
        return False

    try:
        import requests  # type: ignore  # noqa: PLC0415
        from hydramem import __version__ as ver  # type: ignore  # noqa: PLC0415
    except ImportError:
        ver = "0.1.0"

    payload = {
        "version": ver,
        "date": date.today().isoformat(),
        "total_tokens_saved": int(
            stats.get("total_baseline", 0) - stats.get("total_injected", 0)
        ),
        "avg_vog_score": round(float(stats.get("avg_vog", 0.0)), 4),
        "total_calls": int(stats.get("total_calls", 0)),
    }

    try:
        import requests  # type: ignore

        resp = requests.post(AGGREGATE_ENDPOINT, json=payload, timeout=5)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False
