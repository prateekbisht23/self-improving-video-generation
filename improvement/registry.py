"""Agent-version registry (FR-12): which configurations exist, which one is active.

- The default config (v0.2) is seeded as the first active version.
- Candidates are registered with status `candidate`; the baseline row is never modified by an
  experiment (only `status` ever changes, and only through `promote`).
- `promote` needs an approved experiment, retires the old active version, records a Promotion row
  and exports the promoted config to agent/configs/ so it is also visible in git history.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from agent.config import DEFAULT_CONFIG, AgentConfig
from db.models import AgentVersion, Experiment, Promotion

CONFIG_DIR = Path(__file__).resolve().parents[1] / "agent" / "configs"


class PromotionError(RuntimeError):
    pass


def ensure_seed(s) -> AgentVersion:
    active = s.scalar(select(AgentVersion).where(AgentVersion.status == "active"))
    if active:
        return active
    row = s.scalar(select(AgentVersion).where(AgentVersion.version == DEFAULT_CONFIG.version))
    if row is None:
        row = AgentVersion(version=DEFAULT_CONFIG.version, config=DEFAULT_CONFIG.model_dump(), status="active",
                           origin="seed", rationale="v0.2 baseline (Phase 4)")
        s.add(row)
    else:
        row.status = "active"
    s.flush()
    return row


def active(s) -> AgentConfig:
    return AgentConfig.model_validate(ensure_seed(s).config)


def get(s, version: str) -> AgentConfig:
    if version == DEFAULT_CONFIG.version:
        return DEFAULT_CONFIG
    row = s.scalar(select(AgentVersion).where(AgentVersion.version == version))
    if row is None:
        raise KeyError(f"unknown agent version {version}")
    cfg = AgentConfig.model_validate(row.config)
    if cfg.version != version:  # the stored config must still hash to its name
        raise ValueError(f"agent version {version} does not match its config ({cfg.version})")
    return cfg


def register(s, cfg: AgentConfig, *, parent: str | None, origin: str, rationale: str = "") -> AgentVersion:
    """Idempotent: the same config always maps to the same row."""
    row = s.scalar(select(AgentVersion).where(AgentVersion.version == cfg.version))
    if row is None:
        row = AgentVersion(version=cfg.version, parent_version=parent, config=cfg.model_dump(), status="candidate",
                           origin=origin, rationale=rationale)
        s.add(row)
        s.flush()
    return row


def promote(s, experiment: Experiment, approved_by: str, note: str = "") -> Promotion:
    if experiment.status != "approved":
        raise PromotionError(f"experiment {experiment.id} is '{experiment.status}', not 'approved'")
    if not (experiment.gates or {}).get("eligible"):
        raise PromotionError("experiment did not pass the regression gates")
    current = ensure_seed(s)
    if current.version != experiment.baseline_version:
        raise PromotionError(f"active version changed since the experiment ({current.version} != "
                             f"{experiment.baseline_version}); re-run it against the current baseline")
    new = s.scalar(select(AgentVersion).where(AgentVersion.version == experiment.candidate_version))
    current.status, new.status = "retired", "active"
    p = Promotion(experiment_id=experiment.id, from_version=current.version, to_version=new.version,
                  approved_by=approved_by, note=note)
    s.add(p)
    experiment.status = "promoted"
    s.flush()
    CONFIG_DIR.mkdir(exist_ok=True)
    (CONFIG_DIR / f"{new.version}.json").write_text(json.dumps(
        {"version": new.version, "parent": current.version, "promoted_at": datetime.now(UTC).isoformat(),
         "experiment_id": str(experiment.id), "approved_by": approved_by, "config": new.config}, indent=2) + "\n")
    return p
