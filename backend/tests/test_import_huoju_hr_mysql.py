from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "backend" / "scripts" / "import_huoju_hr_mysql.py"

spec = importlib.util.spec_from_file_location("import_huoju_hr_mysql", SCRIPT_PATH)
assert spec is not None
assert spec.loader is not None
import_script = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = import_script
spec.loader.exec_module(import_script)


def test_extract_endpoints_from_apifox_export():
    apifox_doc = {
        "apiCollection": [
            {
                "name": "根目录",
                "items": [
                    {
                        "name": "hr",
                        "items": [
                            {
                                "name": "基本信息",
                                "api": {
                                    "method": "get",
                                    "path": "/bi-center/hr/api/baseinfo",
                                    "parameters": {"header": [{"name": "Authorization", "example": "Bearer token"}]},
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }

    endpoints = import_script.extract_endpoints(apifox_doc)

    assert endpoints == [
        import_script.Endpoint(
            name="根目录/hr/基本信息",
            method="GET",
            path="/bi-center/hr/api/baseinfo",
        )
    ]


def test_extract_endpoints_skips_empty_interviewnotes_api():
    apifox_doc = {
        "apiCollection": [
            {
                "name": "根目录",
                "items": [
                    {
                        "name": "hr",
                        "items": [
                            {
                                "name": "面谈记录",
                                "api": {
                                    "method": "get",
                                    "path": "/bi-center/hr/api/interviewnotes",
                                    "parameters": {"header": [{"name": "Authorization", "example": "Bearer token"}]},
                                },
                            },
                            {
                                "name": "基础信息",
                                "api": {
                                    "method": "get",
                                    "path": "/bi-center/hr/api/baseinfo",
                                    "parameters": {"header": [{"name": "Authorization", "example": "Bearer token"}]},
                                },
                            },
                        ],
                    }
                ],
            }
        ]
    }

    endpoints = import_script.extract_endpoints(apifox_doc)

    assert [endpoint.path for endpoint in endpoints] == ["/bi-center/hr/api/baseinfo"]


def test_endpoint_to_table_name_uses_api_leaf_with_prefix():
    endpoint = import_script.Endpoint(
        name="根目录/hr/员工变动记录",
        method="GET",
        path="/bi-center/hr/api/employeechangerecords",
    )

    assert import_script.endpoint_to_table_name(endpoint, table_prefix="hr_") == "hr_employeechangerecords"


def test_resolve_import_endpoints_adds_organizational_structure_when_missing_from_apifox():
    apifox_doc = {
        "apiCollection": [
            {
                "name": "root",
                "items": [
                    {
                        "name": "hr",
                        "items": [
                            {
                                "name": "baseinfo",
                                "api": {
                                    "method": "get",
                                    "path": "/bi-center/hr/api/baseinfo",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }

    endpoints = import_script.resolve_import_endpoints(apifox_doc)

    assert [endpoint.path for endpoint in endpoints] == [
        "/bi-center/hr/api/baseinfo",
        "/bi-center/hr/api/organizationalstructure",
    ]
    assert endpoints[-1].name == "部门信息"
    assert endpoints[-1].method == "GET"


def test_resolve_import_endpoints_does_not_duplicate_organizational_structure_from_apifox():
    apifox_doc = {
        "apiCollection": [
            {
                "name": "root",
                "items": [
                    {
                        "name": "hr",
                        "items": [
                            {
                                "name": "organizationalstructure",
                                "api": {
                                    "method": "get",
                                    "path": "/bi-center/hr/api/organizationalstructure",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }

    endpoints = import_script.resolve_import_endpoints(apifox_doc)

    assert [endpoint.path for endpoint in endpoints] == ["/bi-center/hr/api/organizationalstructure"]


def test_build_token_request_from_password_apifox_export():
    apifox_doc = {
        "apiCollection": [
            {
                "name": "root",
                "items": [
                    {
                        "name": "密码获取token",
                        "api": {
                            "method": "post",
                            "path": "http://auth.example.test/auth/oauth/token",
                            "parameters": {
                                "query": [
                                    {"name": "grant_type", "example": "password", "enable": True},
                                    {"name": "ignored", "example": "x", "enable": False},
                                ],
                                "header": [
                                    {"name": "TENANT-ID", "example": "1", "enable": True},
                                    {"name": "Authorization", "example": "Basic abc", "enable": True},
                                    {"name": "X-Disabled", "example": "no", "enable": False},
                                ],
                            },
                            "requestBody": {
                                "type": "application/x-www-form-urlencoded",
                                "parameters": [
                                    {"name": "username", "example": "hradmin", "enable": True},
                                    {"name": "password", "example": "secret", "enable": True},
                                    {"name": "scope", "example": "server", "enable": True},
                                ],
                            },
                        },
                    }
                ],
            }
        ]
    }

    request = import_script.build_token_request_from_apifox(apifox_doc)

    assert request.method == "POST"
    assert request.url == "http://auth.example.test/auth/oauth/token"
    assert request.headers == {"TENANT-ID": "1", "Authorization": "Basic abc"}
    assert request.params == {"grant_type": "password"}
    assert request.data == {"username": "hradmin", "password": "secret", "scope": "server"}


def test_fetch_api_token_posts_token_request_and_extracts_access_token():
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "access-123", "token_type": "bearer"}

    class FakeClient:
        def __init__(self):
            self.calls = []

        def request(self, method, url, *, headers=None, params=None, data=None):
            self.calls.append(
                {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "params": params,
                    "data": data,
                }
            )
            return FakeResponse()

    client = FakeClient()
    request = import_script.TokenRequest(
        method="POST",
        url="http://auth.example.test/auth/oauth/token",
        headers={"Authorization": "Basic abc"},
        params={"grant_type": "password"},
        data={"username": "hradmin", "password": "secret"},
    )

    token = import_script.fetch_api_token(client, request=request)

    assert token == "access-123"
    assert client.calls == [
        {
            "method": "POST",
            "url": "http://auth.example.test/auth/oauth/token",
            "headers": {"Authorization": "Basic abc"},
            "params": {"grant_type": "password"},
            "data": {"username": "hradmin", "password": "secret"},
        }
    ]


def test_skipped_table_names_include_interviewnotes_for_cleanup():
    assert import_script.skipped_table_names(table_prefix="hr_") == ["hr_interviewnotes"]


def test_build_drop_table_sql_quotes_table_name():
    assert import_script.build_drop_table_sql("hr_interviewnotes") == "DROP TABLE IF EXISTS `hr_interviewnotes`"


def test_extract_data_rows_requires_response_object_with_data_array():
    assert import_script.extract_data_rows({"code": 200, "data": [{"员工编号": "E001"}]}) == [{"员工编号": "E001"}]

    try:
        import_script.extract_data_rows({"code": 200, "data": {"员工编号": "E001"}})
    except ValueError as exc:
        assert "data must be a list" in str(exc)
    else:
        raise AssertionError("Expected non-list data to fail")


def test_infer_columns_uses_chinese_names_and_conservative_mysql_types():
    rows = [
        {
            "员工编号": "E001",
            "员工姓名": "张三",
            "年龄": 32,
            "司龄(年)": 3.5,
            "入司日期": "2020-01-02",
            "最高学历": 1,
            "奖惩单位": None,
            "扩展对象": {"level": "A"},
            "扩展列表": ["A", "B"],
        },
        {
            "员工编号": "E002",
            "员工姓名": "李四",
            "年龄": None,
            "司龄(年)": 4,
            "入司日期": None,
            "最高学历": 0,
            "奖惩单位": None,
            "扩展对象": None,
            "扩展列表": None,
        },
    ]

    columns = import_script.infer_columns(rows)

    assert columns == [
        import_script.ColumnSpec(name="员工编号", mysql_type="TEXT"),
        import_script.ColumnSpec(name="员工姓名", mysql_type="TEXT"),
        import_script.ColumnSpec(name="年龄", mysql_type="BIGINT"),
        import_script.ColumnSpec(name="司龄(年)", mysql_type="DECIMAL(18,4)"),
        import_script.ColumnSpec(name="入司日期", mysql_type="VARCHAR(32)"),
        import_script.ColumnSpec(name="最高学历", mysql_type="TINYINT"),
        import_script.ColumnSpec(name="奖惩单位", mysql_type="TEXT"),
        import_script.ColumnSpec(name="扩展对象", mysql_type="JSON"),
        import_script.ColumnSpec(name="扩展列表", mysql_type="JSON"),
    ]


def test_build_create_table_sql_quotes_chinese_columns_and_adds_technical_columns():
    endpoint = import_script.Endpoint(name="根目录/hr/基本信息", method="GET", path="/bi-center/hr/api/baseinfo")
    columns = [
        import_script.ColumnSpec(name="员工编号", mysql_type="TEXT"),
        import_script.ColumnSpec(name="年龄", mysql_type="BIGINT"),
    ]

    sql = import_script.build_create_table_sql("hr_baseinfo", columns, endpoint)

    assert "`hr_baseinfo`" in sql
    assert "`员工编号` TEXT NULL" in sql
    assert "`年龄` BIGINT NULL" in sql
    assert "`source_endpoint` VARCHAR(255) NOT NULL" in sql
    assert "`source_row_hash` CHAR(64) NOT NULL" in sql
    assert "`raw_payload` JSON NOT NULL" in sql
    assert "UNIQUE KEY `uk_hr_baseinfo_row_hash` (`source_row_hash`)" in sql


def test_build_insert_rows_maps_values_and_serializes_raw_payload():
    endpoint = import_script.Endpoint(name="根目录/hr/项目经历", method="GET", path="/bi-center/hr/api/projectexperience")
    columns = [
        import_script.ColumnSpec(name="员工编号", mysql_type="TEXT"),
        import_script.ColumnSpec(name="项目名称", mysql_type="TEXT"),
        import_script.ColumnSpec(name="扩展对象", mysql_type="JSON"),
    ]
    rows = [{"员工编号": "E001", "项目名称": "A项目", "扩展对象": {"role": "PM"}}]

    column_names, values = import_script.build_insert_rows(endpoint, columns, rows)

    assert column_names == ["source_endpoint", "source_row_hash", "fetched_at", "raw_payload", "员工编号", "项目名称", "扩展对象"]
    assert values[0][0] == "/bi-center/hr/api/projectexperience"
    assert len(values[0][1]) == 64
    assert values[0][3] == '{"员工编号":"E001","项目名称":"A项目","扩展对象":{"role":"PM"}}'
    assert values[0][-1] == '{"role":"PM"}'


def test_parse_args_disables_environment_proxy_by_default():
    args = import_script.parse_args(["--api-token", "token"])

    assert args.trust_env is False


def test_parse_args_defaults_to_new_desktop_apifox_exports(monkeypatch):
    monkeypatch.delenv("HUOJU_API_TOKEN", raising=False)

    args = import_script.parse_args([])

    assert args.apifox == Path("C:/Users/IT/Desktop/火炬hr.Apifox.json")
    assert args.token_apifox == Path("C:/Users/IT/Desktop/火炬token.Apifox.json")
    assert args.api_base_url == "http://192.168.180.51:31606"
    assert args.api_token is None


def test_parse_args_uses_token_apifox_by_default_even_when_env_token_exists(monkeypatch):
    monkeypatch.setenv("HUOJU_API_TOKEN", "stale-token")

    args = import_script.parse_args([])

    assert args.api_token is None


def test_parse_args_can_enable_environment_proxy_explicitly():
    args = import_script.parse_args(["--api-token", "token", "--trust-env"])

    assert args.trust_env is True
