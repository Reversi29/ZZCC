"""test_brain_concept_weight_learning.py — 方向3 概念→决策融合权重学习测试

验证：
- _continuous_weights 用可学习权重表（默认=旧固定系数）
- train_from_feedback 中 escalate 反馈加强 escalation→urg 权重
- train_from_feedback 中 approve 反馈加强 approval→mag 权重
- 权重有上下限（_CONCEPT_W_CEIL/_CONCEPT_W_FLOOR）
- 无概念向量时权重不变
- 持久化（stats 含 concept_decision_weights，重启保留）
"""
import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "interface"))

from services.brain.snn_region import (
    SNNRegion,
    NeuralSignal,
    _DEFAULT_CONCEPT_DECISION_WEIGHTS,
    _CONCEPT_W_CEIL,
)


def _mk_signal(type_="expense", urgency=50, amount=5000, cv=None):
    payload = {"amount": amount}
    if cv is not None:
        payload["_concept_vector"] = cv
    return NeuralSignal(
        type=type_, urgency=urgency, payload=payload,
        context={},
    )


class TestConceptWeightLearning:
    def _region(self):
        # 隔离 save_path，避免污染生产网络
        tmp = tempfile.mkdtemp()
        r = SNNRegion(
            save_path=os.path.join(tmp, "snn_test.json"),
        )
        # 清理可能从默认路径加载的旧 stats（深拷贝避免污染全局默认）
        r._stats["concept_decision_weights"] = {
            k: dict(v) for k, v in _DEFAULT_CONCEPT_DECISION_WEIGHTS.items()
        }
        return r

    def test_default_weights_match_fixed(self):
        """默认权重表与旧固定系数一致。"""
        r = self._region()
        cdw = r._stats["concept_decision_weights"]
        assert cdw["escalation"]["urg"] == 0.6
        assert cdw["danger"]["urg"] == 0.5
        assert cdw["urgency"]["urg"] == 0.5
        assert cdw["approval"]["mag"] == 0.4

    def test_continuous_uses_learnable_weights(self):
        """_continuous_weights 读可学习权重而非硬编码。"""
        r = self._region()
        # 把 escalation→urg 权重临时调大，验证 _continuous_weights 反映
        r._stats["concept_decision_weights"]["escalation"]["urg"] = 1.0
        # urgency=0 消除基线干扰，纯看概念 boost 差异
        sig = _mk_signal(urgency=0, cv={"escalation": 0.8, "danger": 0.2})
        w = r._continuous_weights(sig)
        r2 = self._region()
        sig2 = _mk_signal(urgency=0, cv={"escalation": 0.8, "danger": 0.2})
        w2 = r2._continuous_weights(sig2)
        # r 的 escalation 权重 1.0 > r2 的 0.6，boost 更强
        assert w.get(201, 0) > w2.get(201, 0)

    def test_escalate_feedback_strengthens_escalation(self):
        """escalate 正确反馈加强 escalation→urg 权重。"""
        r = self._region()
        before = r._stats["concept_decision_weights"]["escalation"]["urg"]
        sig = _mk_signal(cv={"escalation": 0.9})
        r.train_from_feedback(sig, correct_decision="escalate", was_correct=True)
        after = r._stats["concept_decision_weights"]["escalation"]["urg"]
        assert after > before
        assert r._stats.get("concept_weight_updates", 0) >= 1

    def test_approve_feedback_strengthens_approval(self):
        """approve 正确反馈加强 approval→mag 权重。"""
        r = self._region()
        before = r._stats["concept_decision_weights"]["approval"]["mag"]
        sig = _mk_signal(cv={"approval": 0.9})
        r.train_from_feedback(sig, correct_decision="auto_approve", was_correct=True)
        after = r._stats["concept_decision_weights"]["approval"]["mag"]
        assert after > before

    def test_weight_capped(self):
        """权重不超过上限。"""
        r = self._region()
        r._stats["concept_decision_weights"]["escalation"]["urg"] = _CONCEPT_W_CEIL
        sig = _mk_signal(cv={"escalation": 0.9})
        r.train_from_feedback(sig, correct_decision="escalate", was_correct=True)
        after = r._stats["concept_decision_weights"]["escalation"]["urg"]
        assert after <= _CONCEPT_W_CEIL

    def test_no_cv_no_change(self):
        """无概念向量时权重不变。"""
        r = self._region()
        before = json.loads(json.dumps(r._stats["concept_decision_weights"]))
        sig = _mk_signal(cv=None)
        r.train_from_feedback(sig, correct_decision="escalate", was_correct=True)
        after = r._stats["concept_decision_weights"]
        assert after == before

    def test_persist_restart(self):
        """权重随 stats 持久化，重启保留。"""
        r = self._region()
        # 先手动设一个低于上限的值，训练后确认提升且持久化
        r._stats["concept_decision_weights"]["escalation"]["urg"] = 0.6
        before = r._stats["concept_decision_weights"]["escalation"]["urg"]
        sig = _mk_signal(urgency=0, cv={"escalation": 0.9})
        r.train_from_feedback(sig, correct_decision="escalate", was_correct=True)
        trained = r._stats["concept_decision_weights"]["escalation"]["urg"]
        assert trained > before
        r._save_stats()
        # 模拟重启：加载 stats 文件
        r2 = SNNRegion(save_path=r.save_path)
        assert r2._stats["concept_decision_weights"]["escalation"]["urg"] == trained
