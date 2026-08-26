"""test/test_procurement.py — 采购（Supplier + Purchase Order）测试"""
import pytest

API_KEY_HEADERS = {"X-API-Key": "zzcc_oadev_key_2024"}


class TestSupplier:
    def test_list_suppliers(self, client, db):
        r = client.get("/api/resource/Supplier", headers=API_KEY_HEADERS)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_create_supplier(self, client, db):
        r = client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                        json={"name": "SUP-TEST-001", "supplier_name": "测试供应商"})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "SUP-TEST-001"
        # GET 返回完整数据
        r2 = client.get("/api/resource/Supplier/SUP-TEST-001", headers=API_KEY_HEADERS)
        assert r2.json()["data"]["supplier_name"] == "测试供应商"

    def test_create_supplier_auto_seq(self, client, db):
        r = client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                        json={"supplier_name": "自动序列供应商"})
        assert r.status_code == 200
        assert r.json()["data"]["name"].startswith("SUP")

    def test_get_supplier_not_found(self, client, db):
        r = client.get("/api/resource/Supplier/NOTEXIST", headers=API_KEY_HEADERS)
        assert r.status_code == 404

    def test_update_supplier(self, client, db):
        client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                    json={"name": "SUP-UPD-001", "supplier_name": "待改"})
        r2 = client.put("/api/resource/Supplier/SUP-UPD-001", headers=API_KEY_HEADERS,
                        json={"supplier_name": "已改", "country": "CN"})
        assert r2.status_code == 200
        r3 = client.get("/api/resource/Supplier/SUP-UPD-001", headers=API_KEY_HEADERS)
        assert r3.json()["data"]["supplier_name"] == "已改"
        assert r3.json()["data"]["country"] == "CN"

    def test_delete_supplier(self, client, db):
        client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                    json={"name": "SUP-DEL-001", "supplier_name": "待删"})
        r2 = client.delete("/api/resource/Supplier/SUP-DEL-001", headers=API_KEY_HEADERS)
        assert r2.status_code == 200


class TestPurchaseOrder:
    def test_create_purchase_order(self, client, db):
        client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                    json={"name": "SUP-PO-001", "supplier_name": "PO供应商"})
        r = client.post("/api/resource/Purchase%20Order", headers=API_KEY_HEADERS,
                        json={"name": "PO-TEST-001", "supplier": "SUP-PO-001", "items": [{"qty": 5, "rate": 3000}]})
        assert r.status_code == 200
        r2 = client.get("/api/resource/Purchase%20Order/PO-TEST-001", headers=API_KEY_HEADERS)
        assert r2.json()["data"]["supplier"] == "SUP-PO-001"
        assert r2.json()["data"]["total"] == 15000.0

    def test_create_purchase_order_auto_seq(self, client, db):
        client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                    json={"name": "SUP-PO-AUTO", "supplier_name": "自动PO"})
        r = client.post("/api/resource/Purchase%20Order", headers=API_KEY_HEADERS,
                        json={"supplier": "SUP-PO-AUTO", "items": [{"qty": 1, "rate": 100}]})
        assert r.status_code == 200
        assert r.json()["data"]["name"].startswith("PO")

    def test_list_purchase_orders(self, client, db):
        r = client.get("/api/resource/Purchase%20Order", headers=API_KEY_HEADERS)
        assert r.status_code == 200

    def test_get_purchase_order_not_found(self, client, db):
        r = client.get("/api/resource/Purchase%20Order/NOTEXIST", headers=API_KEY_HEADERS)
        assert r.status_code == 404

    def test_update_purchase_order(self, client, db):
        client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                    json={"name": "SUP-PO-UPD", "supplier_name": "upd"})
        client.post("/api/resource/Purchase%20Order", headers=API_KEY_HEADERS,
                    json={"name": "PO-UPD-001", "supplier": "SUP-PO-UPD", "items": [{"qty": 1, "rate": 100}]})
        r2 = client.put("/api/resource/Purchase%20Order/PO-UPD-001", headers=API_KEY_HEADERS,
                        json={"total": 200.0, "status": "Approved"})
        assert r2.status_code == 200
        r3 = client.get("/api/resource/Purchase%20Order/PO-UPD-001", headers=API_KEY_HEADERS)
        assert r3.json()["data"]["total"] == 200.0
        assert r3.json()["data"]["status"] == "Approved"

    def test_delete_purchase_order(self, client, db):
        client.post("/api/resource/Supplier", headers=API_KEY_HEADERS,
                    json={"name": "SUP-PO-DEL", "supplier_name": "del"})
        client.post("/api/resource/Purchase%20Order", headers=API_KEY_HEADERS,
                    json={"name": "PO-DEL-001", "supplier": "SUP-PO-DEL", "items": [{"qty": 1, "rate": 100}]})
        r2 = client.delete("/api/resource/Purchase%20Order/PO-DEL-001", headers=API_KEY_HEADERS)
        assert r2.status_code == 200


class TestProcurementRequiresAuth:
    def test_no_auth(self, client, db):
        r = client.get("/api/resource/Supplier")
        assert r.status_code == 401