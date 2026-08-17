"""test/test_stock.py — P2.11 库存行政模块测试"""
import pytest, json

pytestmark = pytest.mark.asyncio


def test_warehouse_crud(client, auth_headers):
    """Warehouse CRUD"""
    r = client.post("/api/resource/Warehouse", json={"warehouse_name": "测试仓", "warehouse_type": "Physical"}, headers=auth_headers)
    assert r.status_code == 200
    name = r.json()["data"]["name"]

    r = client.get("/api/resource/Warehouse", headers=auth_headers)
    assert r.status_code == 200
    assert any(w["warehouse_name"] == "测试仓" for w in r.json()["data"]["data"])

    r = client.put(f"/api/resource/Warehouse/{name}", json={"address": "深圳南山区"}, headers=auth_headers)
    assert r.status_code == 200

    r = client.delete(f"/api/resource/Warehouse/{name}", headers=auth_headers)
    assert r.status_code == 200


def test_item_with_reorder(client, auth_headers):
    """Item 带 reorder_level"""
    r = client.post("/api/resource/Item", json={
        "item_code": "TEST-001", "item_name": "测试物料",
        "val_rate": 50.0, "opening_stock": 10.0, "reorder_level": 5.0
    }, headers=auth_headers)
    assert r.status_code == 200
    name = r.json()["data"]["name"]

    r = client.get(f"/api/resource/Item/{name}", headers=auth_headers)
    assert r.status_code == 200
    assert float(r.json()["data"]["reorder_level"]) == 5.0


def test_stock_entry_workflow(client, auth_headers):
    """Stock Entry 提交→审批→台账写入"""
    # Warehouse
    r = client.post("/api/resource/Warehouse", json={"warehouse_name": "E2E仓"}, headers=auth_headers)
    assert r.status_code == 200
    wh_name = r.json()["data"]["name"]

    # Item
    r = client.post("/api/resource/Item", json={
        "item_code": "E2E-001", "item_name": "E2E测试物料",
        "val_rate": 200.0, "opening_stock": 0.0, "reorder_level": 10.0
    }, headers=auth_headers)
    assert r.status_code == 200

    # Stock Entry
    r = client.post("/api/resource/Stock%20Entry", json={
        "stock_entry_type": "Material Receipt",
        "to_warehouse": wh_name,
        "items": [{"item_code": "E2E-001", "qty": 100, "rate": 200}],
    }, headers=auth_headers)
    assert r.status_code == 200
    se_name = r.json()["data"]["name"]

    # Submit
    r = client.post("/api/workflow/action", json={"name": se_name, "action": "submit"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["from"] == "Draft" and r.json()["to"] == "Submitted"

    # Approve (triggers _post_stock_ledger)
    r = client.post("/api/workflow/action", json={"name": se_name, "action": "approve"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["to"] == "Approved"

    # StockBalance
    r = client.get("/api/resource/stock_summary", headers=auth_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["item_code"] == "E2E-001" and i["actual_qty"] == 100.0 for i in items)

    # StockLedger
    r = client.get("/api/resource/stock_ledger", headers=auth_headers)
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["item_code"] == "E2E-001" and e["incoming_qty"] == 100.0 for e in entries)


def test_stock_entry_reject_no_ledger(client, auth_headers):
    """Stock Entry 拒绝不写台账"""
    r = client.post("/api/resource/Warehouse", json={"warehouse_name": "Reject仓"}, headers=auth_headers)
    wh_name = r.json()["data"]["name"]

    r = client.post("/api/resource/Item", json={
        "item_code": "REJ-001", "item_name": "拒绝测试",
        "val_rate": 10.0, "opening_stock": 0.0,
    }, headers=auth_headers)

    r = client.post("/api/resource/Stock%20Entry", json={
        "stock_entry_type": "Material Receipt",
        "to_warehouse": wh_name,
        "items": [{"item_code": "REJ-001", "qty": 5, "rate": 10}],
    }, headers=auth_headers)
    se_name = r.json()["data"]["name"]

    client.post("/api/workflow/action", json={"name": se_name, "action": "submit"}, headers=auth_headers)
    r = client.post("/api/workflow/action", json={"name": se_name, "action": "reject"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["to"] == "Rejected"

    # Rejected SE should NOT appear in StockBalance
    r = client.get("/api/resource/stock_summary", headers=auth_headers)
    items = r.json()["items"]
    assert not any(i["item_code"] == "REJ-001" for i in items)
