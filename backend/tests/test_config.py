import pytest

from app.config import AppSettings, StoragePolicy


def test_config_loads(monkeypatch):
    # It should successfully load if valid YAML exists
    from app.config import load_config
    app_cfg, storage_cfg = load_config()
    assert isinstance(app_cfg, AppSettings)
    assert isinstance(storage_cfg, StoragePolicy)

def test_config_rejects_unknown_key(monkeypatch, tmp_path):
    import yaml

    from app.config import AppSettings
    
    # Create fake yaml files
    app_data = {"unknown_key": "val", "app": {}}
    app_file = tmp_path / "app.yaml"
    with open(app_file, "w") as f:
        yaml.dump(app_data, f)
        
    storage_data = {"continuous": {}}
    storage_file = tmp_path / "storage.yaml"
    with open(storage_file, "w") as f:
        yaml.dump(storage_data, f)
        
    def fake_load():
        with open(app_file) as f:
            ad = yaml.safe_load(f)
        with open(storage_file) as f:
            sd = yaml.safe_load(f)
        return ad, sd

    # pydantic Extra.forbid will raise a ValidationError
    from pydantic import ValidationError
    ad, _sd = fake_load()
    with pytest.raises(ValidationError):
        AppSettings(**ad)
