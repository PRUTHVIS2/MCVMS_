from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, 'r') as f:
        return yaml.safe_load(f)

class AppSettings(BaseSettings):
    app: dict[str, Any]
    paths: dict[str, Any]
    media: dict[str, Any]
    analysis: dict[str, Any]
    models: dict[str, Any]
    heavy_categories: list[str]
    vehicles: dict[str, Any]
    attributes: dict[str, Any]
    plate: dict[str, Any]
    matching: dict[str, Any]
    identity: dict[str, Any]
    review: dict[str, Any]
    clips: dict[str, Any]
    id_check: dict[str, Any]
    rules: dict[str, Any]
    training: dict[str, Any]
    health: dict[str, Any]
    privacy: dict[str, Any]
    auth: dict[str, Any]
    api: dict[str, Any]
    
    model_config = SettingsConfigDict(extra="forbid")

class StoragePolicy(BaseSettings):
    continuous: dict[str, Any]
    clips: dict[str, Any]
    retention: dict[str, Any]
    disk: dict[str, Any]
    index: dict[str, Any]
    integrity: dict[str, Any]
    backup: dict[str, Any]
    privacy_placeholders: dict[str, Any]

    model_config = SettingsConfigDict(extra="forbid")

def load_config() -> tuple[AppSettings, StoragePolicy]:
    base_dir = Path(__file__).resolve().parent.parent.parent / "config"
    app_yaml = base_dir / "app.yaml"
    storage_yaml = base_dir / "storage_policy.yaml"
    
    app_data = load_yaml(str(app_yaml))
    storage_data = load_yaml(str(storage_yaml))
    
    return AppSettings(**app_data), StoragePolicy(**storage_data)

try:
    config, storage_policy = load_config()
except Exception as e:
    import sys
    print(f"Error loading configuration: {e}")
    sys.exit(1)
