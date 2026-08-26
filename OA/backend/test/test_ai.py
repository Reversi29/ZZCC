"""test/test_ai.py — AI 咨询 + 审批阈值测试"""
import pytest, json

API_KEY_HEADERS = {"X-API-Key": "zzcc_oadev_key_2024"}


class TestAIConsult:
    def test_consult_procurement(self, client, db):
        r = client.post("/api/ai/consult", headers=API_KEY_HEADERS,
                        json={"module": "procurement", "context": {"doctype": "Purchase Order", "amount": 50000}})
        assert r.status_code == 200

    def test_consult_quality(self, client, db):
        r = client.post("/api/ai/consult", headers=API_KEY_HEADERS,
                        json={"module": "quality", "context": {"inspection_result": "fail"}})
        assert r.status_code == 200

    def test_consult_empty_context(self, client, db):
        r = client.post("/api/ai/consult", headers=API_KEY_HEADERS,
                        json={"module": "procurement", "context": {}})
        assert r.status_code == 200


class TestAIApprovalThresholds:
    def test_list_thresholds(self, client, db):
        r = client.get("/api/ai/approval/thresholds", headers=API_KEY_HEADERS)
        assert r.status_code == 200

    def test_update_threshold(self, client, db):
        r = client.put("/api/ai/approval/threshold", headers=API_KEY_HEADERS,
                        json={"doctype": "Purchase Order", "auto_approve_amount": 5000.0,
                              "require_llm_review": True})
        assert r.status_code == 200

    def test_requires_auth(self, client, db):
        r = client.post("/api/ai/consult", json={"module": "procurement", "context": {}})
        assert r.status_code == 401
