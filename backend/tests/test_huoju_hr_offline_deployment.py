from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_offline_data_builder_uses_huoju_api_sync_instead_of_excel_rebuild() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker" / "docker-compose.hr-boss.offline.yaml").read_text(encoding="utf-8"))
    data_builder = compose["services"]["hr-data-builder"]

    assert data_builder["command"] == "python /app/deployment/hr-boss/sync_huoju_hr_data.py --force"
    assert "${HUOJU_APIFOX_DIR:?set HUOJU_APIFOX_DIR}:/data/hr/apifox:ro" in data_builder["volumes"]
    assert "HR_EXCEL_PATH" not in data_builder["environment"]
    assert "HR_IMPORT_SCRIPT" not in data_builder["environment"]
    assert data_builder["environment"]["HUOJU_HR_APIFOX_PATH"] == "/data/hr/apifox/${HUOJU_HR_APIFOX_FILE:-火炬hr.Apifox.json}"
    assert data_builder["environment"]["HUOJU_TOKEN_APIFOX_PATH"] == "/data/hr/apifox/${HUOJU_TOKEN_APIFOX_FILE:-火炬token.Apifox.json}"
    assert data_builder["environment"]["HUOJU_API_BASE_URL"] == "${HUOJU_API_BASE_URL:-http://192.168.180.51:31606}"
    assert data_builder["environment"]["HUOJU_MYSQL_DATABASE"] == "${MYSQL_DATABASE:-huoju_hr}"


def test_offline_env_defaults_to_huoju_mysql_and_apifox_source() -> None:
    env_example = (REPO_ROOT / "deployment" / "hr-boss" / "offline.env.example").read_text(encoding="utf-8")

    assert "MYSQL_DATABASE=huoju_hr" in env_example
    assert "HUOJU_MYSQL_DATABASE=huoju_hr" in env_example
    assert "HUOJU_API_BASE_URL=http://192.168.180.51:31606" in env_example
    assert "HUOJU_APIFOX_DIR=/data/hr/apifox" in env_example
    assert "HUOJU_HR_APIFOX_FILE=火炬hr.Apifox.json" in env_example
    assert "HUOJU_TOKEN_APIFOX_FILE=火炬token.Apifox.json" in env_example
    assert "HR_KG_SOURCE_DIR" not in env_example
    assert "HR_EXCEL_FILE" not in env_example
    assert "HR_IMPORT_SCRIPT_FILE" not in env_example


def test_offline_bundle_includes_huoju_sync_script_and_no_excel_rebuild_entrypoint() -> None:
    script = (REPO_ROOT / "deployment" / "hr-boss" / "build-offline-bundle.ps1").read_text(encoding="utf-8")

    assert "sync_huoju_hr_data.py" in script
    assert "import_huoju_hr_mysql.py" in script
    assert "clean_huoju_hr_mysql.py" in script
    assert "rebuild_hr_kg.py" not in script
