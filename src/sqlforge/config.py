"""Typed YAML config loading with environment-variable overrides.

Every stage (data, training, eval, serving) defines a Pydantic model and loads its
YAML from configs/ through ``load_config``. An environment variable named
``SQLFORGE_<FIELD>`` (upper-cased field name) overrides the YAML value, so Colab
runs and Docker can tweak a single setting without editing files.
"""

import os
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

ENV_PREFIX = "SQLFORGE_"

T = TypeVar("T", bound=BaseModel)


def load_config(path: str | Path, model: type[T]) -> T:
    """Load a YAML file into ``model``, applying SQLFORGE_* env overrides.

    Only top-level fields can be overridden from the environment; the raw string
    is validated (and coerced) by Pydantic like any other value.
    """
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping, got {type(raw).__name__}: {path}")

    for field in model.model_fields:
        env_value = os.environ.get(ENV_PREFIX + field.upper())
        if env_value is not None:
            raw[field] = env_value

    return model.model_validate(raw)
