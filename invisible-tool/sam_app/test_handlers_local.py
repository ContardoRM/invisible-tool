"""
Prueba de humo LOCAL de los handlers Lambda, sin desplegar nada y sin
`sam local invoke` (que requeriría emular Lambda+Docker además de
DynamoDB). Importa los módulos directamente y los corre contra
DynamoDB Local, igual que la integración ya validada en
invisible-tool/integration_test.py, pero ejercitando el código real de
sam_app/demo_runner/app.py y sam_app/report_reader/app.py.

Requiere DynamoDB Local corriendo en 127.0.0.1:8000 (o el puerto que se
pase en DDB_PORT) y fastmcp==3.4.10 + boto3 instalados en el entorno
que ejecuta este script (usar uv run --with fastmcp==3.4.10 --with
boto3).

Verifica:
  1. demo_runner.app.handler produce un informe con los 4 casos, en el
     orden restricted:tools_list, restricted:tools_call,
     authorized:tools_list, authorized:tools_call (restringida
     primero, autorizada como control después).
  2. Los veredictos coinciden con la matriz de aceptación de 3.4.10
     (idéntica a la ya validada con DynamoDB Local y AWS Emulator en
     invisible-tool/integration_test.py).
  3. report_reader.app.handler recupera ese mismo run_id con 200 y el
     informe íntegro.
  4. report_reader.app.handler devuelve 404 para un run_id inexistente
     y 400 si falta run_id en la ruta.

Ejecutar con:
    docker run -d --name ddb-sam-test -p 127.0.0.1:8000:8000 \
      amazon/dynamodb-local:latest -jar DynamoDBLocal.jar -sharedDb -inMemory
    cd sam_app
    uv run --with fastmcp==3.4.10 --with boto3 -- python3 test_handlers_local.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "demo_runner"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "report_reader"))

TABLE_NAME = "test-handlers-local"
DDB_ENDPOINT = f"http://127.0.0.1:{os.environ.get('DDB_PORT', '8000')}"

os.environ["REPORTS_TABLE_NAME"] = TABLE_NAME
os.environ["REPORTS_LOCAL_TEST_ENDPOINT"] = DDB_ENDPOINT

EXPECTED_VERDICTS_3410 = {
    "restricted:tools_list": "BLOQUEO_ESPERADO",
    "restricted:tools_call": "BLOQUEO_ESPERADO",
    "authorized:tools_list": "ACCESO_LEGITIMO",
    "authorized:tools_call": "ACCESO_LEGITIMO",
}
EXPECTED_CASE_ORDER = [
    "restricted:tools_list",
    "restricted:tools_call",
    "authorized:tools_list",
    "authorized:tools_call",
]


def _ensure_table() -> None:
    import boto3

    client = boto3.client(
        "dynamodb",
        endpoint_url=DDB_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="fakeMyKeyId",
        aws_secret_access_key="fakeSecretAccessKey",
    )
    try:
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "report_id", "KeyType": "HASH"},
                {"AttributeName": "target_version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "report_id", "AttributeType": "S"},
                {"AttributeName": "target_version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
    except Exception as exc:  # noqa: BLE001
        if "ResourceInUseException" not in str(type(exc)) and "ResourceInUseException" not in str(exc):
            raise


def test_demo_runner_produces_live_report() -> dict:
    from demo_runner import app as runner_app

    result = runner_app.handler({}, None)
    assert result["statusCode"] == 200, result
    body = json.loads(result["body"])
    run_id = body["run_id"]
    report = body["report"]

    assert report["target_version"] == "3.4.10"
    assert report["source"] == "3.4.10 · comprobación en vivo"

    cases_by_name = {c["case"]: c for c in report["cases"]}
    actual_order = [c["case"] for c in report["cases"]]
    assert actual_order == EXPECTED_CASE_ORDER, f"orden inesperado: {actual_order}"

    for case, expected_verdict in EXPECTED_VERDICTS_3410.items():
        actual = cases_by_name[case]["verdict"]
        assert actual == expected_verdict, f"{case}: {actual} != {expected_verdict}"

    print(f"PASS  test_demo_runner_produces_live_report (run_id={run_id})")
    return {"run_id": run_id, "report": report}


def _report_event(run_id: str) -> dict:
    # event["path"] refleja el resourcePath de API Gateway SIN el
    # prefijo del stage (confirmado contra la documentación oficial de
    # Lambda proxy integration: el stage vive en requestContext, no en
    # "path"). El recurso real es /demo/report/{run_id}.
    return {"path": f"/demo/report/{run_id}", "pathParameters": {"run_id": run_id}}


def test_report_reader_recovers_same_report(run_id: str, original_report: dict) -> None:
    from report_reader import app as reader_app

    result = reader_app.handler(_report_event(run_id), None)
    assert result["statusCode"] == 200, result
    body = json.loads(result["body"])
    assert body["run_id"] == run_id
    assert len(body["reports"]) == 1
    assert body["reports"][0] == original_report

    print(f"PASS  test_report_reader_recovers_same_report (run_id={run_id})")


def test_report_reader_404_for_unknown_run_id() -> None:
    from report_reader import app as reader_app

    result = reader_app.handler(_report_event("does-not-exist"), None)
    assert result["statusCode"] == 404, result
    print("PASS  test_report_reader_404_for_unknown_run_id")


def test_report_reader_400_without_run_id() -> None:
    from report_reader import app as reader_app

    # Ruta /demo/report/ reconocida como prefijo pero sin pathParameters.
    result = reader_app.handler({"path": "/demo/report/", "pathParameters": {}}, None)
    assert result["statusCode"] == 400, result
    print("PASS  test_report_reader_400_without_run_id")


def test_report_reader_serves_ui_page() -> None:
    from report_reader import app as reader_app

    result = reader_app.handler({"path": "/"}, None)
    assert result["statusCode"] == 200, result
    assert result["headers"]["Content-Type"] == "text/html"
    assert "Invisible Tool" in result["body"]
    assert 'data-i18n="title"' in result["body"]
    print("PASS  test_report_reader_serves_ui_page")


def test_report_reader_serves_ui_assets() -> None:
    from report_reader import app as reader_app

    for asset_path, expect_substring in (
        ("/ui/app.js", "runLiveCheck"),
        ("/ui/translations.js", "const TRANSLATIONS"),
    ):
        result = reader_app.handler({"path": asset_path}, None)
        assert result["statusCode"] == 200, (asset_path, result)
        assert "javascript" in result["headers"]["Content-Type"], (asset_path, result["headers"])
        assert expect_substring in result["body"], asset_path
    print("PASS  test_report_reader_serves_ui_assets")


def test_report_reader_404_for_unknown_route() -> None:
    from report_reader import app as reader_app

    result = reader_app.handler({"path": "/nonexistent"}, None)
    assert result["statusCode"] == 404, result
    print("PASS  test_report_reader_404_for_unknown_route")


if __name__ == "__main__":
    _ensure_table()

    demo_result = test_demo_runner_produces_live_report()
    test_report_reader_recovers_same_report(demo_result["run_id"], demo_result["report"])
    test_report_reader_404_for_unknown_run_id()
    test_report_reader_400_without_run_id()
    test_report_reader_serves_ui_page()
    test_report_reader_serves_ui_assets()
    test_report_reader_404_for_unknown_route()

    print("\nTodas las pruebas de humo locales pasaron.")
