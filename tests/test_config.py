from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from sqlforge.config import load_config

FIXTURE = Path(__file__).parent / "fixtures" / "sample_config.yaml"


class DemoConfig(BaseModel):
    name: str
    seed: int
    max_examples: int


def test_loads_yaml_into_model():
    cfg = load_config(FIXTURE, DemoConfig)
    assert cfg.name == "smoke"
    assert cfg.seed == 42
    assert cfg.max_examples == 20


def test_env_override_wins_and_is_coerced(monkeypatch):
    monkeypatch.setenv("SQLFORGE_MAX_EXAMPLES", "7")
    cfg = load_config(FIXTURE, DemoConfig)
    assert cfg.max_examples == 7


def test_invalid_env_override_fails_validation(monkeypatch):
    monkeypatch.setenv("SQLFORGE_SEED", "not-a-number")
    with pytest.raises(ValidationError):
        load_config(FIXTURE, DemoConfig)


def test_non_mapping_config_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(bad, DemoConfig)
