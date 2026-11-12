"""services.yaml must stay in sync with the service schema and strings.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from ruckus_wips.services import SERVICE_SCHEMA

DOMAIN_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "ruckus_wips"
SERVICES = yaml.safe_load((DOMAIN_DIR / "services.yaml").read_text(encoding="utf-8"))
STRINGS = json.loads((DOMAIN_DIR / "strings.json").read_text(encoding="utf-8"))
SCHEMA_KEYS = {str(key) for key in SERVICE_SCHEMA.schema}


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_no_target_device_filter(service: str) -> None:
    # hassfest rejects device filters on `target`, and HA merges target into
    # service data as a list, which SERVICE_SCHEMA's string device_id rejects.
    assert "target" not in SERVICES[service]


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_fields_match_schema(service: str) -> None:
    assert set(SERVICES[service]["fields"]) == SCHEMA_KEYS


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_device_id_uses_device_selector(service: str) -> None:
    selector = SERVICES[service]["fields"]["device_id"]["selector"]
    assert selector == {"device": {"integration": "ruckus_wips"}}


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_every_field_has_strings(service: str) -> None:
    assert set(SERVICES[service]["fields"]) == set(STRINGS["services"][service]["fields"])
