from __future__ import annotations

from pathlib import Path

import yaml


def test_docker_compose_exposes_only_two_runtime_services() -> None:
    compose_path = Path("docker-compose.yml")
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    services = compose["services"]

    assert set(services.keys()) == {"ocr-api", "recommend-api"}
    assert services["ocr-api"]["container_name"] == "mulmumu-ocr-api"
    assert services["recommend-api"]["container_name"] == "mulmumu-recommend-api"
