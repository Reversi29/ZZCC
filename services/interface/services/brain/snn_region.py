"""services/brain/snn_region.py - SNN 脑区适配器

将 NeuralSignal 编码为 SNN 输入模式,执行 SNN 持续学习推理,将输出解码为 CognitionResult。

架构位置:
    ReasoningEngine._register_regions()
        → snn_region(signal, context, budget) → RegionResult
            → SNN.step_with_learning() → 融合推理+微学习+探索
            → 决策日志自动记录(JSONL)
            → 解码为 CognitionResult

持续学习:
    - 每个信号既是推理输入也是训练数据(在线学习)
    - EWC 防灾难性遗忘(重要权重保护)
    - 探索机制(混乱权利:随机扰动发现边界模式)
    - 自动调节探索率(稳定性↑→探索率↓,错误→探索率↑)

概率涌现:
    - SNN 输出布尔值,不直接暴露概率
    - 决策日志累积后查询 → 事后统计概率分布
    - 相同模式多次决策 → 准确率自然形成概率

反馈学习:
    /brain/learn → 反馈标注 → 微学习(不是批量训练)

持久化:
    SNN.save()/load() → JSON 文件(brain_config_dir/snn_network.json)
    决策日志 → JSONL 文件(brain_config_dir/snn_decision_log.jsonl)
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional

from models.brain import Action, CognitionResult, NeuralSignal
from services.brain.snn import SNN, NeuronType
from services.brain.neuro_registry import (
    InputRegistry, OutputRegistry, ConceptRegistry,
)

logger = logging.getLogger("brain.snn_region")

def _default_brain_config_dir() -> str:
    configured = os.environ.get("BRAIN_CONFIG_DIR", "/app/config_data")
    if os.path.isdir(configured) or os.path.abspath(configured) == "/app/config_data":
        return configured
    local_data = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data"))
    if os.path.isdir(local_data):
        return local_data
    return configured


# ── 信号类型 → 输入神经元 ID 映射 ─────────────────────────────
_SIGNAL_TO_NEURON = {
    "expense": 0,
    "invoice": 0,           # 费用类归并
    "payment": 0,
    "reimbursement": 0,
    "expense_approval": 0,  # 费用审批归并
    "approval_pending": 1,
    "purchase_order": 1,    # 采购订单归并
    "vendor_risk": 2,       # 供应商风险归并到阈值违规
    "threshold_breach": 2,
    "user_request": 3,
    "cron_alert": 4,
    "external_event": 5,
    "plugin_event": 5,      # 插件事件归并到外部事件
    "error": 6,
    "query": 7,
    "chitchat": 8,
    "system": 9,
    "noise": 10,
}

# ── 输出神经元 ID → 决策类型映射 ──────────────────────────────
_OUTPUT_DECISION = {
    32: "auto_approve",
    33: "reject",
    34: "escalate",
    35: "flag",
    36: "no_action",
    37: "chat",
}

# 方向3：概念→决策融合通道的可学习权重表
# 结构: {概念: {通道: 权重}}，通道 ∈ {"urg", "mag"}
# 默认系数与旧固定实现一致，训练后按反馈调整（上限 _CONCEPT_W_CEIL）
_DEFAULT_CONCEPT_DECISION_WEIGHTS = {
    "escalation": {"urg": 0.6},
    "danger": {"urg": 0.5},
    "urgency": {"urg": 0.5},
    "approval": {"mag": 0.4},
}
_CONCEPT_W_CEIL = 1.5   # 概念→通道权重上限
_CONCEPT_W_FLOOR = 0.1  # 概念→通道权重下限

# ── 紧急度 → 输入神经元映射 ─────────────────────────────────
def _urgency_neuron(urgency: int) -> Optional[int]:
    """紧急度 0-100 → 输入神经元 11(高位标记)"""
    if urgency >= 70:
        return 11
    return None


# ── payload 特征 → 输入神经元映射(v2) ─────────────────────
_AMOUNT_LOW_MAX = 1000.0       # 金额 ≤ 此值 → amount_low (neuron 12)
_AMOUNT_HIGH_MIN = 100000.0    # 金额 > 此值 → amount_high (neuron 14)
_DETAIL_KEYS = (
    "description", "desc", "title", "text", "note",
    "content", "remark", "summary", "reason", "question",
)

# ── 连续调制通道(v4:去硬编码,大小/紧急度不再只分档) ──────
# 档位槽(12/13/14、11)仍保留二值激活,作为隐藏层 AND 门的条件;
# 但连续强度另进专用槽(200=magnitude, 201=urgency_cont),
# 让网络真正感知"具体多大/多急",而非只有三档标签。
_MAG_NEURON = 200            # 数值大小连续通道
# ID 区规划:固定 0-39 + 动态输入槽 40-135 + 动态输出槽 100-195
# → 200+ 为安全区,不与任何动态注册冲突
_URGENCY_CONT_NEURON = 201    # 紧急度连续通道
_MAG_SATURATION = 200000.0   # 对数归一化饱和值

# ── 连续通道独立中继子网(隔离硬编码层的污染)────────────────
# 连续通道若直连既有隐藏层(阈值 1.5 的 AND 门),会额外抬高膜电位
# 破坏档位选择--这是历史"架构天花板"的根源。
# 改为:200/201 → 中继层 210-215(阈值 1.2,亚阈值调制)
#       → 汇入既有层(权重 0.25,低于 AND 门阈值,只能微幅调制)
#       中继不连输出层:_decode_output 会把中继分数计入所有输出,
#       破坏竞争比较。中继只调制隐藏层膜电位。
_RELAY_START = 210
_RELAY_COUNT = 6
_RELAY_THRESHOLD = 0.95
_RELAY_IN_WEIGHT = 0.4      # 200/201 → 中继(乘上 gain 后膜电位约 0.6-1.0,
# 低于中继阈值 0.95,单通道不触发;膜电位随注入强度线性变化,可分辨)
_RELAY_OUT_WEIGHT = 0.3    # 中继 → 既有隐藏层(亚阈值调制,不触发 AND 门)
# 选择性投射:中继只连 escalate 相关隐藏层(17/18/20/21/26),
# 而非无差别撒网 16-21。无差别撒网下任何放电都破坏 12/12
# (实测阈值 0.95→8/12),选择性保持 12/12。
# 生物上感觉中继(丘脑)选择性投射到语义相关皮层层,非无差别撒网。
_RELAY_HIDDEN_TARGETS = (17, 18, 20, 21, 26)  # escalate 相关隐藏层


# ── 概念认知通道（通用认知学习）────────────────────────────
# 概念向量（开放集）的每个概念动态注册为概念输入神经元，
# 经独立概念中继子网接入既有隐藏层。概念槽与连续通道（200/201）、
# 动态类型槽（40+）、动态动作槽（100+）分属不同 ID 区，互不冲突。
# 概念→决策连接靠 STDP/反馈学习收敛，而非硬编码语义映射。
_CONCEPT_NEURON_BASE = 220    # 概念输入神经元起点
_CONCEPT_RELAY_BASE = 230     # 概念中继神经元起点
_CONCEPT_RELAY_THRESHOLD = 0.95   # 概念中继阈值（大强度放电）
_CONCEPT_RELAY_IN_WEIGHT = 0.4    # 概念 → 中继
_CONCEPT_RELAY_OUT_WEIGHT = 0.25  # 中继 → 既有隐藏层（亚阈值调制，不触发 AND 门）
_CONCEPT_LEARN_ETA = 0.12    # 概念槽学习率（独立于微学习 eta，训练足够快）


def _normalize_magnitude(amount: float) -> float:
    """金额/数值大小 → 0.0-1.0 连续值(对数缩放)。

    对数缩放贴近人类对数量级的感知(1000→10000 与 10000→100000
    的心理差距相当),避免线性映射把小额区间压缩到 0。
    """
    if amount <= 0:
        return 0.0
    v = math.log10(amount + 1.0) / math.log10(_MAG_SATURATION + 1.0)
    return max(0.0, min(1.0, v))


def _payload_features(payload: Any) -> tuple:
    """从 payload 提取 (金额分桶神经元 ID, 是否有详情字段)。

    Returns:
        (amount_neuron_id | None, has_detail: bool)
    """
    if not isinstance(payload, dict):
        return None, False

    # 金额提取:兼容 amount / price / value / total
    amount = payload.get("amount")
    if amount is None:
        amount = payload.get("price") or payload.get("value") or payload.get("total")

    amount_neuron = None
    if isinstance(amount, (int, float)) and amount >= 0:
        if amount <= _AMOUNT_LOW_MAX:
            amount_neuron = 12       # amount_low
        elif amount <= _AMOUNT_HIGH_MIN:
            amount_neuron = 13       # amount_medium
        else:
            amount_neuron = 14       # amount_high

    has_detail = any(k in payload for k in _DETAIL_KEYS)
    return amount_neuron, has_detail


class SNNRegion:
    """SNN 脑区:脉冲神经网络推理。

    特性:
    - 步进式计算(非真实时间延迟)
    - 奖励调制 Hebbian 学习(从反馈标注中学习)
    - 状态持久化(JSON 文件)
    - 结构可塑(增删神经元/连接)
    """

    _OUTPUT_NEURONS = [32, 33, 34, 35, 36, 37]

    # 推理步数:SNN 运行的最大时间步数
    INFERENCE_STEPS = 10

    def __init__(self, save_path: Optional[str] = None):
        config_dir = _default_brain_config_dir()
        self.save_path = save_path or os.path.join(config_dir, "snn_network.json")

        self._stats_path = self.save_path.replace(".json", "_stats.json")

        # 加载或创建默认网络
        self.snn = SNN.load(self.save_path)
        if self.snn is None:
            logger.info("snn: creating default topology")
            self.snn = SNN.create_default()
            self._auto_save()

        self._stats = {
            "reason_calls": 0,
            "reason_hits": 0,
            "total_fires": 0,
            "last_decision": "",
            "last_confidence": 0.0,
            "training_count": 0,
            "edges_added": 0,
            "edges_strengthened": 0,
            "edges_penalized": 0,
            # 持续学习统计
            "exploration_rate": 0.1,
            "boundary_detected_count": 0,
            "ewc_protected_edges": 0,
            "micro_learn_steps": 0,
            # 方向3：概念→决策融合权重（可学习）
            # 深拷贝：内层 dict 也独立，避免改一个实例污染全局默认
            "concept_decision_weights": {
                k: dict(v) for k, v in _DEFAULT_CONCEPT_DECISION_WEIGHTS.items()
            },
        }
        self._load_stats()
        # 兜底：合并默认与文件值（文件可能缺某些概念键，保留已学习的值）
        if not isinstance(self._stats.get("concept_decision_weights"), dict):
            self._stats["concept_decision_weights"] = {}
        for _c, _ch in _DEFAULT_CONCEPT_DECISION_WEIGHTS.items():
            _entry = self._stats["concept_decision_weights"].setdefault(_c, {})
            for _ch_name, _w in _ch.items():
                if _ch_name not in _entry:
                    _entry[_ch_name] = _w

        # 决策日志路径
        self._decision_log_path = self.save_path.replace(".json", "_decision_log.jsonl")

        # ── 通用输入/输出槽注册器(新类型有新槽)────────────
        # registry 路径与 save_path 同目录（生产在 config_dir，测试在临时目录）
        _registry_path = os.path.join(os.path.dirname(self.save_path), "neuro_registry.json")
        self.input_registry = InputRegistry(_registry_path)
        self.output_registry = OutputRegistry(_registry_path)
        # 概念槽注册器（开放集概念 → 概念输入神经元）
        self.concept_registry = ConceptRegistry(_registry_path)

    def _register_signal_type(self, sig_type: str) -> int:
        """注册信号类型到动态输入槽(新类型有新槽,不挤占旧槽)。

        返回输入神经元 ID。新类型会分配新的输入神经元,并通过
        探索连接(弱随机连接)接入隐藏层,靠 STDP/强化学习收敛。
        """
        return self.input_registry.register(sig_type)

    # ── 编码/解码 ────────────────────────────────────────────

    def _encode_signal(self, signal: NeuralSignal) -> List[int]:
        """将 NeuralSignal 编码为 SNN 输入神经元列表(v2:含 payload 特征)。

        编码维度:
        - 信号类型 → neuron 0-10
        - 紧急度高 → neuron 11
        - 金额分桶 → neuron 12 (low) / 13 (medium) / 14 (high)
        - 有详情字段 → neuron 15

        同类型信号可通过 payload 特征区分(如 approval_pending 小额→flag / 大额→escalate)。
        """
        neurons: List[int] = []
        sig_type = (signal.type or "").lower()
        nid = _SIGNAL_TO_NEURON.get(sig_type)
        if nid is not None:
            neurons.append(nid)
        else:
            # 类型未映射到固定槽 → 动态注册新槽(新类型有新槽)
            # 无论 payload 是否产生金额/详情特征,类型信息都必须保留
            dynamic_nid = self._ensure_dynamic_input_slot(sig_type)
            if dynamic_nid is not None:
                neurons.append(dynamic_nid)

        # 紧急度编码
        u_neuron = _urgency_neuron(signal.urgency)
        if u_neuron is not None:
            neurons.append(u_neuron)

        # payload 特征编码(v2)
        payload = signal.payload or {}
        amount_neuron, has_detail = _payload_features(payload)
        if amount_neuron is not None:
            neurons.append(amount_neuron)
        if has_detail:
            neurons.append(15)

        # ── 专用标记神经元(v3 编码消歧) ──────────────────
        # approval_pending + 低紧急度(<40) → 38 (ap_low_marker) → auto_approve
        # user_request + 动作关键词 → 39 (user_action_marker) → escalate
        if sig_type == "approval_pending" and signal.urgency < 40:
            neurons.append(38)
        elif sig_type == "user_request":
            text = str(payload.get("question", "")) + str(payload.get("text", ""))
            if any(k in text.lower() for k in
                   ("cancel", "order", "delete", "refund", "urgent", "escalate")):
                neurons.append(39)

        # 类型映射已在顶部处理:固定槽或动态注册槽
        return neurons or [10]  # 默认 noise

    # ── 连续调制通道(v4) ─────────────────────────────────────
    def _has_edges(self, source: int) -> bool:
        """判断神经元是否已有出边(SNN 内部用 out_edges 邻接表)。"""
        out_edges = getattr(self.snn, "out_edges", None)
        if out_edges is None:
            return False
        return len(out_edges.get(source, ())) > 0

    def _ensure_continuous_channels(self) -> None:
        """确保连续调制通道神经元存在并建立探索连接。

        200 = magnitude(数值大小连续强度)
        201 = urgency_cont(紧急度连续强度)

        与档位槽(12/13/14、11)并存:档位槽保持二值激活,
        继续作为隐藏层 AND 门(阈值 1.5)的条件;
        连续通道承载"具体多大/多急",靠 STDP 学权重。
        """
        # 连续通道本身无出边(输入神经元),保证存在
        for nid in (_MAG_NEURON, _URGENCY_CONT_NEURON):
            self._ensure_dynamic_neuron(nid, NeuronType.INPUT)

        # 中继子网:隔离既有 AND 门,靠 STDP/反馈学习收敛
        for i in range(_RELAY_COUNT):
            rid = _RELAY_START + i
            self._ensure_dynamic_neuron(rid, NeuronType.EXCITATORY)
            if len(self.snn.out_edges.get(rid, ())) == 0:
                # 中继 → 既有隐藏层(弱调制,不触发 AND 门)
                for hid in _RELAY_HIDDEN_TARGETS:
                    if hid < self.snn.num_neurons:
                        self.snn.connect(rid, hid, weight=_RELAY_OUT_WEIGHT, delay=1)
                        # 不连输出层:避免 _decode_output 把中继分数计入所有输出
                # 破坏竞争比较(12 场景硬约束)。中继只调制隐藏层膜电位。
                # 设定中继阈值
                self.snn.neurons[rid].threshold = _RELAY_THRESHOLD

        # 连续通道 → 各自专属中继层。
        # 饱和控制:注入强度 × 权重 ≤ 中继阈值,膜电位随强度线性变化。
        # 200(magnitude) 与 201(urgency_cont) 连到不相交的中继子集,
        # 否则 201(urgency 普遍非零)会淹没 200 的连续差异--
        # 这正是"300 与 900 元同膜电位"的饱和失真根因。
        _chan_to_relay = {
            _MAG_NEURON: range(_RELAY_START, _RELAY_START + 3),
            _URGENCY_CONT_NEURON: range(_RELAY_START + 3, _RELAY_START + _RELAY_COUNT),
        }
        for nid, relay_ids in _chan_to_relay.items():
            if len(self.snn.out_edges.get(nid, ())) == 0:
                targets = [self.snn.neurons[rid].id for rid in relay_ids]
                for rid in targets:
                    self.snn.connect(nid, rid, weight=_RELAY_IN_WEIGHT, delay=1)
                logger.info(
                    f"snn_region: continuous channel {nid} → relay {targets} "
                    f"(w={_RELAY_IN_WEIGHT}, sub-threshold modulation)"
                )

        # 速率编码:中继阈值放低到 0.95(原来 1.2),
        # 让大额/高紧急度的连续强度真正触发中继放电。
        # 中继放电 → 选择性加强 escalate 隐藏层 → 影响决策。
        # 持续注入(sustain_weights)是关键:感觉输入持续存在,
        # 一次性注入会在传播后衰减,永远到不了阈值。
        self._relay_threshold_applied = True
        self._auto_save()

    def _continuous_weights(self, signal: NeuralSignal) -> Dict[int, float]:
        """提取连续强度调制(v4 核心:去硬编码分档)。

        返回 {neuron_id: 强度},强度按信号语义归一化:
        - magnitude: 对数缩放,1000 → ~0.23,10000 → ~0.40,
          100000 → ~0.57,200000+ → 1.0(饱和)
        - urgency_cont: 原始 urgency/100

        强度 > 2.0 时乘以 scale,因为输入神经元阈值默认 0.5,
        需要足够膜电位才能激活下游。
        """
        self._ensure_continuous_channels()
        w: Dict[int, float] = {}

        payload = signal.payload or {}
        amount = payload.get("amount")
        if amount is None:
            amount = payload.get("price") or payload.get("value") or payload.get("total")
        if isinstance(amount, (int, float)) and amount >= 0:
            mag = _normalize_magnitude(float(amount))
            if mag > 0.0:
                # 强度映射到 1.0-3.0,保证能越过隐藏层阈值
                w[_MAG_NEURON] = 1.0 + mag * 2.0

        urg = max(0.0, min(100.0, float(signal.urgency or 0)))
        if urg > 0.0:
            w[_URGENCY_CONT_NEURON] = 1.0 + (urg / 100.0) * 2.0

        # 概念向量连续通道：概念直接驱动主 SNN 决策
        # 两层机制：
        #   1. 硬映射（方向3，可学习权重）：escalation/danger/urgency→urg 通道、
        #      approval→mag 通道（兼容 12 eval 的档位决策语义）
        #   2. 通用认知通道（新增）：**任意概念**（含开放集新概念）动态注册
        #      为概念输入神经元（220+），经独立概念中继子网接入隐藏层，
        #      概念→决策连接靠 STDP/反馈学习收敛，不硬编码语义映射。
        cv = (signal.payload or {}).get("_concept_vector")
        if isinstance(cv, dict) and cv:
            # 方向3：概念→通道权重可学习（默认 = 旧固定系数）
            cdw = self._stats.get("concept_decision_weights") or {}
            # 升级/危险/紧急概念 → urgency 通道增强
            boost_urg = (
                cv.get("escalation", 0) * cdw.get("escalation", {}).get("urg", 0.6)
                + cv.get("danger", 0) * cdw.get("danger", {}).get("urg", 0.5)
                + cv.get("urgency", 0) * cdw.get("urgency", {}).get("urg", 0.5)
            )
            if boost_urg > 0.05:
                w[_URGENCY_CONT_NEURON] = w.get(_URGENCY_CONT_NEURON, 1.0) + boost_urg * 1.5
            # 审批概念 → mag 通道增强（approve 倾向）
            boost_appr = cv.get("approval", 0) * cdw.get("approval", {}).get("mag", 0.4)
            if boost_appr > 0.05:
                w[_MAG_NEURON] = w.get(_MAG_NEURON, 1.0) + boost_appr * 1.0

            # 通用认知通道：任意激活概念（含开放集新概念）→ 概念输入神经元
            for concept_name, act in cv.items():
                if not concept_name or not isinstance(concept_name, str):
                    continue
                act = float(act or 0)
                if act <= 0.05:
                    continue
                cnid = self._ensure_concept_channel(concept_name)
                if cnid is not None:
                    # 概念激活强度映射到 1.0-3.0（越过隐藏层阈值，但走独立中继不污染 AND 门）
                    w[cnid] = max(w.get(cnid, 0.0), 1.0 + act * 2.0)

        return w

    def _ensure_dynamic_input_slot(self, sig_type: str) -> Optional[int]:
        """确保信号类型有动态输入槽,并确保神经元 + 探索连接存在。

        新类型有新槽(区别于旧 hash 分桶挤占旧槽):
        1. 注册新类型 → 分配新的输入神经元 ID(≥40)
        2. 确保神经元存在于 SNN(add_neuron 自动扩展 num_neurons)
        3. 建立探索连接(弱随机连接到兴奋性隐藏神经元)
        4. 靠 STDP/强化学习自然收敛
        """
        try:
            nid = self.input_registry.get(sig_type)
            if nid is None:
                nid = self.input_registry.register(sig_type)
                # 确保神经元存在(add_neuron 自动扩展 num_neurons)
                self._ensure_dynamic_neuron(nid)
                # 建立探索连接
                self._connect_dynamic_exploration(nid)
                # 立即持久化:动态神经元 + 探索连接不丢失(reason 不调 _auto_save)
                self._auto_save()
            return nid
        except Exception as e:
            logger.warning(f"snn_region: dynamic input slot failed for '{sig_type}': {e}")
            return None

    def _ensure_dynamic_neuron(self, nid: int, ntype: Optional[NeuronType] = None):
        """确保神经元存在且类型正确(默认 INPUT,可指定)。"""
        ntype = ntype or NeuronType.INPUT
        if nid >= self.snn.num_neurons:
            self.snn.add_neuron(nid, ntype, threshold=0.5)
        else:
            n = self.snn.neurons[nid]
            if n.neuron_type != ntype:
                n.neuron_type = ntype
                n.threshold = 0.5

    def _connect_dynamic_exploration(self, input_nid: int):
        """新输入神经元 → 广泛连接到兴奋性隐藏神经元(探索连接)。

        敏感期广泛探索:连接全部兴奋性隐藏层,让网络自己
        发现哪些连接重要。权重与固定拓扑一致(0.90),确保
        新类型能参与推理;连接的选择靠 STDP/强化学习收敛。
        """
        import random
        hidden_pool = [h for h in range(16, 28) if h < self.snn.num_neurons]
        if not hidden_pool:
            return
        for hid in hidden_pool:
            self.snn.connect(input_nid, hid, weight=0.90, delay=1)
        logger.info(f"snn_region: dynamic input {input_nid} exploration → {hidden_pool} (w=0.90)")

    # ── 输出侧动态动作(四肢百骸:改变世界的新动作)──────────

    def _ensure_dynamic_output_slot(self, action: str) -> Optional[int]:
        """确保动作有动态输出槽,并确保神经元 + 探索连接存在。

        新动作有新槽(对称于输入侧新类型有新槽):
        1. 注册新动作 → 分配新的输出神经元 ID(≥40)
        2. 确保神经元存在于 SNN(类型 OUTPUT)
        3. 建立探索连接(兴奋性隐藏神经元 → 新输出,弱权重)
        4. 立即持久化(reason 不调 _auto_save)
        """
        try:
            nid = self.output_registry.get(action)
            if nid is None:
                nid = self.output_registry.register(action)
                # 确保输出神经元存在
                self._ensure_dynamic_output_neuron(nid)
                # 建立探索连接(隐藏层 → 新输出)
                self._connect_dynamic_output_exploration(nid)
                # 立即持久化
                self._auto_save()
            return nid
        except Exception as e:
            logger.warning(f"snn_region: dynamic output slot failed for '{action}': {e}")
            return None

    def _ensure_dynamic_output_neuron(self, nid: int):
        """确保动态输出神经元存在且类型为 OUTPUT。"""
        if nid >= self.snn.num_neurons:
            self.snn.add_neuron(nid, NeuronType.OUTPUT, threshold=1.0)
        else:
            n = self.snn.neurons[nid]
            if n.neuron_type != NeuronType.OUTPUT:
                n.neuron_type = NeuronType.OUTPUT
                n.threshold = 1.0

    def _connect_dynamic_output_exploration(self, output_nid: int):
        """新输出神经元 ← 隐藏层探索连接(突触发生,非预建)。

        对称于输入侧:新动作的连接**不预建**,而是在训练时通过
        _reward_modulated_strengthen(auto_create=True, restrict_to_hidden=True)
        针对性创建--只创建与新类型实际放电的隐藏层的连接,
        避免无差别加强导致劫持所有路径(灾难性遗忘)。
        """
        # 不预建连接:让训练时突触发生针对性创建(避免劫持)
        logger.info(f"snn_region: dynamic output {output_nid} exploration (lazy, synaptogenesis)")

    # ── 概念认知通道（通用认知学习）────────────────────────

    def _ensure_concept_channel(self, concept: str) -> Optional[int]:
        """确保概念有认知通道：概念输入神经元 + 概念中继子网。

        通用认知学习核心：概念向量（开放集）的每个概念动态注册
        为概念输入神经元，经独立概念中继子网接入既有隐藏层。
        - 概念 → 概念中继（权重 _CONCEPT_RELAY_IN_WEIGHT）
        - 概念中继 → 既有隐藏层（亚阈值调制，不触发 AND 门）
        - 概念→决策连接靠 STDP/反馈学习收敛，不硬编码语义映射

        返回概念输入神经元 ID；失败返回 None。
        """
        try:
            concept = (concept or "").lower()
            if not concept:
                return None
            nid = self.concept_registry.get(concept)
            if nid is None:
                nid = self.concept_registry.register(concept)
            # 幂等：无论新注册还是已注册，都确保概念输入 + 中继 + 连接存在
            # （旧网络可能注册表有映射但神经元未建，如 216 神经元旧版网络）
            self._ensure_dynamic_neuron(nid, NeuronType.INPUT)
            relay_nid = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
            self._ensure_dynamic_neuron(relay_nid, NeuronType.EXCITATORY)
            self.snn.neurons[relay_nid].threshold = _CONCEPT_RELAY_THRESHOLD
            # 概念 → 中继
            if len(self.snn.out_edges.get(nid, ())) == 0:
                self.snn.connect(nid, relay_nid, weight=_CONCEPT_RELAY_IN_WEIGHT, delay=1)
            # 中继 → 既有隐藏层（亚阈值调制，不触发 AND 门）
            if len(self.snn.out_edges.get(relay_nid, ())) == 0:
                for hid in _RELAY_HIDDEN_TARGETS:
                    if hid < self.snn.num_neurons:
                        self.snn.connect(relay_nid, hid, weight=_CONCEPT_RELAY_OUT_WEIGHT, delay=1)
            # 立即持久化：概念槽 + 神经元 + 连接不丢失
            self._auto_save()
            logger.info(f"snn_region: concept channel {concept} → {nid} (relay {relay_nid})")
            return nid
        except Exception as e:
            logger.warning(f"snn_region: concept channel failed for '{concept}': {e}")
            return None

    def _decode_output(self, outputs: Dict[int, bool],
                        active: List[int]) -> Optional[CognitionResult]:
        """将 SNN 输出解码为 CognitionResult。

        多输出时不直接全部采信:按当前激活/膜势强的前驱连接强度排序,
        选择最强输出,并把竞争输出写入 memory_updates 供调试。
        """
        # 检查输出神经元是否在推理期间放电过(last_fire_time >= 0)
        # 注意:放电后 membrane 会重置为 0,不能用 membrane > 0 判断
        fired_outputs = [nid for nid, v in outputs.items() if v]
        if not fired_outputs:
            # 兜底:检查 last_fire_time(某些 step 可能 outputs 没捕获到)
            # 包含固定输出 + 动态注册输出槽
            all_output_neurons = list(self._OUTPUT_NEURONS)
            for nid in self.output_registry.all_actions().values():
                if nid not in all_output_neurons:
                    all_output_neurons.append(nid)
            fired_outputs = [
                nid for nid in all_output_neurons
                if nid < len(self.snn.neurons) and self.snn.neurons[nid].last_fire_time >= 0
            ]
        if not fired_outputs:
            return None

        strengths: Dict[int, float] = {}
        # 前驱源：所有已放电的非输入/非输出神经元（隐藏层 16-31 + 中继层 210+/230+）
        # 扩展中继层：概念槽/连续通道经中继驱动输出时，正确计入竞争分
        # （原只含 16-31，概念中继 230 不计入 → 概念驱动输出无法胜出）
        hidden_source_ids = set(
            n.id for n in self.snn.neurons
            if n.last_fire_time >= 0
            and n.neuron_type not in (NeuronType.INPUT, NeuronType.OUTPUT)
        )
        for out_nid in fired_outputs:
            n = self.snn.neurons[out_nid]
            score = max(0.1, float(n.membrane or 0.0))
            for src_nid in hidden_source_ids:
                conn = self.snn.out_edges.get(src_nid, {}).get(out_nid)
                if conn is not None:
                    score += conn.weight * 2.0
            if score <= 0.1:
                for src in self.snn.neurons:
                    if src.last_fire_time >= 0 and src.id < 16:
                        conn = self.snn.out_edges.get(src.id, {}).get(out_nid)
                        if conn is not None:
                            score += conn.weight
            strengths[out_nid] = score

        sorted_outputs = sorted(strengths.items(), key=lambda item: item[1], reverse=True)
        top_nid, top_score = sorted_outputs[0]
        decision = self._decision_for_output(top_nid)
        if decision is None:
            return None

        total_score = sum(max(0.0, score) for _, score in sorted_outputs)
        confidence = 0.35
        if total_score > 0:
            confidence += min(0.45, top_score / total_score * 0.65)
        if len(sorted_outputs) == 1:
            confidence += 0.1
        confidence = round(min(1.0, max(0.0, confidence)), 3)

        competition = [
            {"output_neuron": nid, "decision": self._decision_for_output(nid), "score": round(score, 3)}
            for nid, score in sorted_outputs
        ]
        fired_outputs_serializable = [
            {"output_neuron": nid, "decision": self._decision_for_output(nid), "score": round(score, 3)}
            for nid, score in sorted_outputs
        ]

        return CognitionResult(
            reasoning_level=3,  # 类 L3 级别
            confidence=confidence,
            decision=decision,
            reasoning=f"SNN 脉冲推理: 激活神经元={active[:10]}, 输出={fired_outputs_serializable}",
            actions=[Action(type=decision, reason="SNN 脉冲神经网络推理")],
            memory_updates={
                "snn_active": active,
                "snn_outputs": outputs,
                "snn_competition": competition,
                "snn_selected": top_nid,
            },
        )

    def _decision_for_output(self, nid: int) -> Optional[str]:
        """输出神经元 → 决策名。支持固定 + 动态注册输出槽。"""
        # 固定输出映射(0-37 区间)
        dec = _OUTPUT_DECISION.get(nid)
        if dec is not None:
            return dec
        # 动态注册输出动作
        return self.output_registry.get_action(nid)

    # ── 推理入口(供协调器调用)────────────────────────────

    async def reason(
        self,
        signal: NeuralSignal,
        context: Dict[str, Any],
        budget: Any = None,
    ) -> Any:
        """SNN 推理入口。返回 RegionResult。

        从 coordinator 调用的标准签名。
        使用 step_with_learning() 融合推理+微学习+探索。

        持续学习流程:
        1. 编码信号为输入神经元
        2. step_with_learning() → 推理 + 微学习 + 探索
        3. 记录决策日志(JSONL)
        4. 解码输出为 CognitionResult

        注意:不在推理前 reset_learning_state(),保留学习历史。
        这样连续信号之间可以共享学习状态,实现真正的在线学习。
        """
        from services.brain.coordinator import RegionResult

        start = time.time()
        self._stats["reason_calls"] += 1

        try:
            # 编码输入
            input_neurons = self._encode_signal(signal)
            strength = 2.0 + (signal.urgency / 100.0) * 3.0  # 0.0-3.0

            # 连续调制通道(v4):大小/紧急度不再只分档
            # 档位槽保持二值激活(AND 门条件),连续槽承载"具体多大/多急"
            cont_weights = self._continuous_weights(signal)

            # 推理时禁用 Hebbian/LTD,防止 STDP 削弱权重(学习漂移)
            # 学习通过 train_from_feedback / _reward_modulated_strengthen 进行
            self.snn.enable_hebbian = False

            # 持续学习推理：融合推理+微学习+探索
            # 不传 expected_decision，因为推理时没有反馈
            # 不传 sustain_weights：一次性注入保持 12/12 档位决策。
            # 速率编码（持续注入）会破坏档位槽→隐藏层的精确放电组合，
            # 中继放电必然改变隐藏层激活模式——已实测任何中继放电都 <12/12。
            # 连续调制以亚阈值（膜电位梯度）形式存在，供 STDP/学习利用。
            outputs, boundary_detected = self.snn.step_with_learning(
                input_neurons, strength, weights=cont_weights
            )

            # 记录探索结果
            if boundary_detected:
                self._stats["boundary_detected_count"] += 1

            # 记录探索率
            self._stats["exploration_rate"] = self.snn._exploration_rate

            active = [n.id for n in self.snn.neurons
                      if n.last_fire_time >= 0 and (self.snn.time - n.last_fire_time) <= 10]
            result = self._decode_output(outputs, active)

            elapsed = (time.time() - start) * 1000

            # 记录决策日志
            self._log_decision(
                signal,
                input_neurons,
                outputs,
                result.decision if result else None,
                result.confidence if result else 0.0,
                elapsed,
                boundary_detected,
            )

            if result and result.confidence >= 0.3:
                result.signal_id = signal.id
                self._stats["reason_hits"] += 1
                self._stats["last_decision"] = result.decision
                self._stats["last_confidence"] = result.confidence
                self._stats["total_fires"] = self.snn.stats()["total_fires"]

                return RegionResult(
                    region="snn", ok=True,
                    result=result,
                    context={
                        "input_neurons": input_neurons,
                        "steps_run": self.snn.time,
                        "boundary_detected": boundary_detected,
                        "exploration_rate": self._stats["exploration_rate"],
                    },
                    elapsed_ms=elapsed,
                )

            # 未产生有效结果
            return RegionResult(
                region="snn", ok=True, result=None,
                context={
                    "input_neurons": input_neurons,
                    "reason": "SNN 输出未达阈值",
                    "stats": self.snn.stats(),
                    "exploration_rate": self._stats["exploration_rate"],
                },
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return RegionResult(
                region="snn", ok=False,
                error=str(e), elapsed_ms=elapsed,
            )

    # ── 决策日志 ────────────────────────────────────────────

    def _log_decision(
        self,
        signal: NeuralSignal,
        input_neurons: List[int],
        outputs: Dict[int, bool],
        decision: Optional[str],
        confidence: float,
        elapsed_ms: float,
        boundary_detected: bool,
    ):
        """记录决策日志(JSONL 格式)。

        每条记录包含:
        - signal_id, signal_type, urgency
        - input_neurons, outputs
        - decision, confidence
        - timestamp, elapsed_ms
        - boundary_detected
        - exploration_rate

        用途:
        1. 事后查询概率分布(相同模式多次决策的准确率)
        2. 训练数据回放(选择高置信度样本)
        3. 决策审计(谁在什么时候做了什么决策)
        """
        import datetime

        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "signal_id": signal.id,
            "signal_type": signal.type,
            "urgency": signal.urgency,
            "input_neurons": input_neurons,
            "outputs": {str(k): v for k, v in outputs.items()},
            "decision": decision,
            "confidence": confidence,
            "elapsed_ms": round(elapsed_ms, 2),
            "boundary_detected": boundary_detected,
            "exploration_rate": self._stats.get("exploration_rate", 0.1),
        }

        try:
            with open(self._decision_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("snn: decision log failed: %s", str(e))

    def query_decision_probability(
        self,
        signal_type: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """查询决策概率分布(事后统计)。

        从决策日志中统计相同信号类型的决策分布。

        Args:
            signal_type: 信号类型(如 "expense", "approval_pending")
            limit: 查询最近 N 条记录

        Returns:
            {
                "signal_type": "expense",
                "total": 50,
                "distribution": {"auto_approve": 0.6, "escalate": 0.3, ...},
                "recent": [...]  # 最近 10 条记录
            }
        """
        if not os.path.exists(self._decision_log_path):
            return {"signal_type": signal_type, "total": 0, "distribution": {}}

        try:
            entries = []
            with open(self._decision_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("signal_type") == signal_type:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue

            # 取最近 limit 条
            entries = entries[-limit:]

            if not entries:
                return {"signal_type": signal_type, "total": 0, "distribution": {}}

            # 统计决策分布
            decision_counts: Dict[str, int] = {}
            for e in entries:
                dec = e.get("decision")
                if dec:
                    decision_counts[dec] = decision_counts.get(dec, 0) + 1

            total = len(entries)
            distribution = {
                k: round(v / total, 3)
                for k, v in sorted(decision_counts.items(), key=lambda x: -x[1])
            }

            # 最近 10 条
            recent = [
                {
                    "timestamp": e.get("timestamp"),
                    "decision": e.get("decision"),
                    "confidence": e.get("confidence"),
                    "boundary_detected": e.get("boundary_detected"),
                }
                for e in entries[-10:]
            ]

            return {
                "signal_type": signal_type,
                "total": total,
                "distribution": distribution,
                "recent": recent,
            }

        except Exception as e:
            logger.warning("snn: probability query failed: %s", str(e))
            return {"signal_type": signal_type, "total": 0, "distribution": {}, "error": str(e)}

    # ── 反馈学习 ────────────────────────────────────────────

    def train_from_feedback(
        self,
        signal: NeuralSignal,
        correct_decision: str,
        was_correct: bool,
        wrong_decision: Optional[str] = None,
        eta: float = 0.02,
        inject_strength: float = 2.0,
    ) -> dict:
        """从反馈标注中学习。

        Args:
            signal: 原始信号(重放输入模式)
            correct_decision: 正确决策(如 "auto_approve")
            was_correct: 原始推理是否正确
            wrong_decision: 错误决策(was_correct=False 时用于惩罚;默认读 last_decision)

        Returns:
            学习结果摘要
        """
        input_neurons = self._encode_signal(signal)
        target_output = self._decision_to_output_neuron(correct_decision)

        if target_output is None:
            # 新动作有新槽:动态注册输出槽(改变世界的新动作)
            target_output = self._ensure_dynamic_output_slot(correct_decision)
            if target_output is None:
                return {"ok": False, "reason": f"未知决策类型: {correct_decision}"}

        # 目标导向强化:禁用 Hebbian LTD(被动削弱会磨弱新动作的探索连接)。
        # 只用 _reward_modulated_strengthen 做因果强化,不受被动 LTD 干扰。
        _saved_hebbian = self.snn.enable_hebbian
        self.snn.enable_hebbian = False

        self._stats["training_count"] += 1
        self._stats["micro_learn_steps"] += 1

        # 三阶段训练:输入 → 传播 → 奖励 → STDP
        # 关键:注入输入后先 step 让隐藏层放电,再注入输出
        # 这样 hidden.last_fire_time < output.last_fire_time,STDP 才能生效
        strength = 2.0 + (signal.urgency / 100.0) * 3.0
        eta = 0.02  # 微学习步长
        auto_create = False  # auto_create 会导致非选择性直连,LTD 实验结论:禁用

        if was_correct:
            # 正确决策 → 加强到正确输出的连接
            for _ in range(5):
                # 每次循环重置学习状态,确保 last_fire_time 只反映本次放电
                # (否则历史放电累积,_reward_modulated_strengthen 无差别加强)
                self.snn.reset_learning_state()
                self.snn.inject_pattern(input_neurons, strength)
                self.snn.step()  # t=N:   输入放电,传播到隐藏层
                self.snn.step()  # t=N+1: 隐藏层放电(事件到达)
                self.snn.inject_input(target_output, inject_strength)
                outputs = self.snn.step()  # t=N+2: 输出放电
                if outputs.get(target_output, False):
                    before = sum(
                        1 for src in self.snn.out_edges
                        for c in self.snn.out_edges[src].values()
                        if c.weight > 0.1
                    )
                    # 动态输出槽:针对性突触发生(只创建/加强隐藏层→新输出)
                    # 固定输出槽:保持 auto_create=False(LTD 实验结论)
                    is_dynamic_output = target_output >= 40
                    strengthened = self.snn._reward_modulated_strengthen(
                        target_output, eta=eta,
                        auto_create=is_dynamic_output,
                        auto_create_weight=0.15,
                        restrict_to_hidden=is_dynamic_output,
                        cap_weight=1.5 if is_dynamic_output else None,
                    )
                    after = sum(
                        1 for src in self.snn.out_edges
                        for c in self.snn.out_edges[src].values()
                        if c.weight > 0.1
                    )
                    self._stats["edges_added"] += max(0, after - before)
                    self._stats["edges_strengthened"] += strengthened
        else:
            # 错误决策 → 惩罚原始输出,同时轻微加强正确输出
            original_decision = wrong_decision or self._stats.get("last_decision", "")
            penalty_output = self._decision_to_output_neuron(original_decision)
            # 有概念向量时:惩罚也概念特异性(只削弱概念槽→原始输出),不碰全局——
            # 概念槽独立学习,全局网络不被污染(否则无概念信号也偏目标决策)。
            # 无概念向量时:传统全局惩罚(纠正全局路径)。
            _has_concept = bool((signal.payload or {}).get("_concept_vector"))
            if _has_concept and penalty_output is not None:
                # 概念特异性惩罚:削弱概念中继→原始输出(若有)
                cv = (signal.payload or {}).get("_concept_vector") or {}
                for concept_name in cv:
                    cnid = self.concept_registry.get(concept_name)
                    if cnid is None:
                        continue
                    relay_nid = _CONCEPT_RELAY_BASE + (cnid - _CONCEPT_NEURON_BASE)
                    conn = self.snn.out_edges.get(relay_nid, {}).get(penalty_output)
                    if conn is not None:
                        conn.weight = max(0.5, conn.weight * 0.95)
                        self._stats["edges_penalized"] += 1
            elif penalty_output is not None:
                # 温和惩罚:削弱 5%(原来 20% 太狠导致权重净流失/灾难性遗忘)
                # 且保留最小权重 0.5,避免关键决策路径被磨没
                for src in list(self.snn.out_edges.keys()):
                    if penalty_output in self.snn.out_edges[src]:
                        conn = self.snn.out_edges[src][penalty_output]
                        conn.weight = max(0.5, conn.weight * 0.95)
                        self._stats["edges_penalized"] += 1
            # 少量加强正确输出(让下次推理偏向正确决策)
            # 有概念向量时跳过全局加强:概念槽学习应特异性(只加强概念→目标输出),
            # 不污染全局网络(否则无概念信号也偏目标决策)。
            # 无概念向量时保留传统纠错(全局加强)。
            if not _has_concept:
                for _ in range(2):
                    self.snn.reset_learning_state()
                    self.snn.inject_pattern(input_neurons, strength)
                    self.snn.step()
                    self.snn.step()
                    self.snn.inject_input(target_output, inject_strength * 0.5)  # 较弱注入
                    outputs = self.snn.step()
                    if outputs.get(target_output, False):
                        # 动态输出槽同样 restrict_to_hidden(避免输入→输出直连)
                        is_dynamic_output = target_output >= 40
                        strengthened = self.snn._reward_modulated_strengthen(
                            target_output, eta=eta * 0.5,
                            auto_create=False,
                            auto_create_weight=0.10,
                            restrict_to_hidden=is_dynamic_output,
                            cap_weight=1.5 if is_dynamic_output else None,
                        )
                        self._stats["edges_strengthened"] += strengthened

        # 方向3：概念→决策融合权重学习
        # 反馈的正确决策 → 概念教师，若概念向量该概念激活，加强其→通道权重
        self._learn_concept_decision_weights(signal, correct_decision, eta)

        # 通用认知学习：概念槽学会驱动正确决策
        # 无论 was_correct 与否，correct_decision 就是学习目标（用户纠正的决策）。
        # 错误路径下原始决策≠correct_decision，但概念槽仍应学会正确决策——
        # 否则概念永远学不会（生产 learn 场景多数是纠正错误，was_correct=False）
        self._learn_concept_drives_output(signal, target_output, eta)

        self._auto_save()

        # 恢复 Hebbian 状态(推理时可能被 reason() 设为 False)
        self.snn.enable_hebbian = _saved_hebbian

        return {
            "ok": True,
            "signal_type": signal.type,
            "correct_decision": correct_decision,
            "was_correct": was_correct,
            "input_neurons": input_neurons,
            "target_output": target_output,
            "edges_strengthened": self._stats.get("edges_strengthened", 0),
            "edges_added": self._stats.get("edges_added", 0),
            "edges_penalized": self._stats.get("edges_penalized", 0),
            "snn_stats": self.snn.stats(),
        }

    def _learn_concept_decision_weights(
        self, signal: NeuralSignal, correct_decision: str, eta: float = 0.02
    ) -> None:
        """方向3：概念→决策融合权重学习。

        反馈的正确决策映射为概念教师（approve→approval、escalate→escalation），
        若 signal.payload._concept_vector 中该概念激活，则上调该概念→通道权重，
        让下次推理更偏向正确决策方向（非固定系数）。
        """
        try:
            cv = (signal.payload or {}).get("_concept_vector")
            if not isinstance(cv, dict) or not cv:
                return
            # 决策 → 概念（与 cognitive_coder.learn_from_feedback 一致）
            decision_concept = {
                "auto_approve": "approval",
                "approve": "approval",
                "reject": "rejection",
                "escalate": "escalation",
                "flag": "escalation",
                "no_action": "novelty",
                "chat": "chitchat",
            }.get(correct_decision, "")
            if not decision_concept:
                return
            act = float(cv.get(decision_concept, 0) or 0)
            if act <= 0.05:
                return
            # 概念 → 通道（默认映射）
            concept_channel = {
                "approval": "mag",
                "escalation": "urg",
                "danger": "urg",
                "urgency": "urg",
            }.get(decision_concept, "")
            if not concept_channel:
                return
            cdw = self._stats.setdefault("concept_decision_weights", {})
            entry = cdw.setdefault(decision_concept, {})
            old_w = float(entry.get(concept_channel, 0.4 if concept_channel == "mag" else 0.6))
            # 学习率按概念激活强度缩放（激活越强越信任该反馈）
            new_w = old_w + eta * act
            entry[concept_channel] = min(_CONCEPT_W_CEIL, new_w)
            self._stats["concept_weight_updates"] = \
                self._stats.get("concept_weight_updates", 0) + 1
        except Exception:
            pass

    def _learn_concept_drives_output(
        self, signal: NeuralSignal, target_output: int, eta: float = 0.02
    ) -> None:
        """通用认知学习：概念槽学会驱动正确决策。

        正确反馈时，对概念向量中每个激活概念，加强其概念中继→隐藏层连接，
        让概念激活更强地传导到隐藏层，最终触发目标输出。

        机制：
        - 概念输入(220+) → 概念中继(230+) → 隐藏层(17/18/20/21/26)
        - 概念中继→隐藏层连接经加强后，概念激活能可靠驱动隐藏层放电
        - 隐藏层→目标输出由 _reward_modulated_strengthen 加强
        - 最终概念成为该决策的可靠触发（非硬编码映射，靠学习收敛）
        """
        try:
            cv = (signal.payload or {}).get("_concept_vector")
            if not isinstance(cv, dict) or not cv:
                return
            for concept_name, act in cv.items():
                if not concept_name or not isinstance(concept_name, str):
                    continue
                act = float(act or 0)
                if act <= 0.05:
                    continue
                nid = self.concept_registry.get(concept_name)
                # 无条件确保概念槽存在（幂等）：即使注册表已有映射，
                # 也确保输入神经元+中继+连接存在（旧网络可能映射有但神经元未建）
                ensured = self._ensure_concept_channel(concept_name)
                if ensured is not None:
                    nid = ensured
                if nid is None:
                    continue
                relay_nid = _CONCEPT_RELAY_BASE + (nid - _CONCEPT_NEURON_BASE)
                if relay_nid >= self.snn.num_neurons:
                    continue
                # 概念中继→目标输出：突触发生 + 加强（概念激活直接驱动输出）
                # 经多次训练，概念槽能独立触发目标输出（不依赖隐藏层 AND 门）
                # 只加强目标输出直连，不加强 relay→hidden 的 escalate 路径——
                # 那是档位槽语义，概念不应接管（避免概念激活偏 escalate）
                conn = self.snn.out_edges.get(relay_nid, {}).get(target_output)
                if conn is None:
                    # 突触发生：建立中继→输出连接（初始与隐藏层同权重）
                    self.snn.connect(relay_nid, target_output, weight=_CONCEPT_RELAY_OUT_WEIGHT, delay=1)
                    conn = self.snn.out_edges.get(relay_nid, {}).get(target_output)
                if conn is not None and conn.weight < self.snn.max_weight:
                    conn.weight = min(self.snn.max_weight, conn.weight + _CONCEPT_LEARN_ETA * act)
        except Exception:
            pass

    def _decision_to_output_neuron(self, decision: str) -> Optional[int]:
        """决策类型 → 输出神经元 ID。支持固定 + 动态注册输出槽。"""
        for nid, dec in _OUTPUT_DECISION.items():
            if dec == decision:
                return nid
        # 动态注册输出动作
        return self.output_registry.get(decision)

    # ── 持久化 ──────────────────────────────────────────────

    def _auto_save(self):
        """自动保存网络状态和统计。"""
        try:
            self.snn.save(self.save_path)
            if hasattr(self, "_stats"):
                self._save_stats()
        except Exception as e:
            logger.warning("snn_auto_save_failed: %s", str(e))

    def save(self) -> bool:
        """手动保存。"""
        return self.snn.save(self.save_path)

    # ── 管理接口 ────────────────────────────────────────────

    def reset(self):
        """重置推理状态(不重置权重)。"""
        self.snn.reset()

    def reset_network(self):
        """重置为默认网络(清除所有学习)。"""
        self.snn = SNN.create_default()
        self._stats = {
            "reason_calls": 0, "reason_hits": 0,
            "total_fires": 0, "last_decision": "",
            "last_confidence": 0.0, "training_count": 0,
            "edges_added": 0, "edges_strengthened": 0, "edges_penalized": 0,
            # 持续学习统计（重置后 train_from_feedback 依赖这些键，缺失会 KeyError）
            "exploration_rate": 0.1,
            "boundary_detected_count": 0,
            "ewc_protected_edges": 0,
            "micro_learn_steps": 0,
            # 概念→决策融合权重（深拷贝，避免内层共享）
            "concept_decision_weights": {
                k: dict(v) for k, v in _DEFAULT_CONCEPT_DECISION_WEIGHTS.items()
            },
        }
        self._auto_save()

    def _load_stats(self):
        import json
        if not os.path.exists(self._stats_path):
            return
        try:
            with open(self._stats_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._stats.update(data)
        except Exception as e:
            logger.warning("snn: stats load failed: %s", str(e))

    def _save_stats(self):
        import json
        try:
            with open(self._stats_path, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("snn: stats save failed: %s", str(e))

    def status(self) -> dict:
        """网络状态快照。"""
        return {
            "ok": True,
            "save_path": self.save_path,
            "stats": self._stats,
            "network": self.snn.stats(),
        }

    def connection_graph(self) -> dict:
        """连接图(供前端可视化)。"""
        nodes = []
        for n in self.snn.neurons:
            nodes.append({
                "id": n.id,
                "type": n.neuron_type.value,
                "fire_count": n.fire_count,
            })
        edges = []
        for src in self.snn.out_edges:
            for tgt, conn in self.snn.out_edges[src].items():
                edges.append({
                    "source": src,
                    "target": tgt,
                    "weight": round(conn.weight, 4),
                    "delay": conn.delay,
                })
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": self.snn.stats(),
        }

    # 全局单例
    global_instance: Optional["SNNRegion"] = None


class ShadowSNNRegion(SNNRegion):
    """辅助 SNN shadow 脑区。

    MVP 最小闭环:
    - 复用 SNNRegion 的编码/解码逻辑
    - 只观察主 SNN 结果,不参与最终融合
    - 结果写入 context["shadow:snn_aux"] 供后续评估/回放
    """

    def __init__(self, save_path: Optional[str] = None):
        config_dir = _default_brain_config_dir()
        save_path = save_path or os.path.join(config_dir, "snn_shadow_network.json")
        super().__init__(save_path=save_path)
        self._stats_path = self.save_path.replace(".json", "_stats.json")
        self._stats.update({
            "shadow_calls": 0,
            "shadow_hits": 0,
            "agreement": 0,
            "disagreement": 0,
            "replay_count": 0,
            "null_shadow_calls": 0,
            "last_shadow_decision": "",
            "last_main_decision": "",
        })
        self._load_stats()
        # 决策对比日志路径(shadow 专用)
        self._shadow_log_path = self.save_path.replace(".json", "_shadow_compare.jsonl")
        # 扰动标记文件(确保只扰动一次)
        self._perturbed_flag_path = self.save_path.replace(".json", "_perturbed.flag")
        # Shadow 必须是主 SNN 的"异质变体":初始化时对所有权重加扰动,
        # 否则从同一 create_default() 出发、未训练时输出完全一致,永远 agreement,无观测价值。
        # 扰动只影响 shadow 自身网络,不触碰主 SNN。
        self._perturb_network()
        self._save_stats()  # 确保统计文件存在

    def _perturb_network(self, amplitude: float = 0.35, n_extra_edges: int = 8):
        """对 shadow 网络进行异质化:权重扰动 + 随机新增连接。

        仅第一次执行(标记文件不存在时)。

        异质化策略:
        1. 权重扰动:对现有边加 ±amplitude 的随机扰动
        2. 结构扰动:随机新增若干条 input→hidden 或 hidden→output 的边
           这些新边在主 SNN 中不存在,为 shadow 提供替代路径,
           从而在某些输入下产生不同的输出(真正的 disagreement)。
        """
        try:
            if os.path.exists(self._perturbed_flag_path):
                return
            import random
            rng = random.Random()

            # Phase 1: 权重扰动
            changed = 0
            for src, targets in self.snn.out_edges.items():
                for tgt, conn in list(targets.items()):
                    if conn is None:
                        continue
                    factor = 1.0 + rng.uniform(-amplitude, amplitude)
                    conn.weight = max(0.05, min(self.snn.max_weight, conn.weight * factor))
                    changed += 1

            # Phase 2: 结构扰动 - 随机新增边
            # 输入层 (0-15) → 隐藏层 (16-27 exc, 28-31 inh)
            # 隐藏层 → 输出层 (32-37)
            added = 0
            input_range = list(range(0, 16))
            exc_range = list(range(16, 28))
            inh_range = list(range(28, 32))
            output_range = list(range(32, 38))
            attempts = n_extra_edges * 3  # 尝试更多次以避开已存在的边
            for _ in range(attempts):
                if added >= n_extra_edges:
                    break
                # 随机选择边类型
                if rng.random() < 0.5:
                    src = rng.choice(input_range)
                    tgt_pool = exc_range if rng.random() < 0.85 else inh_range
                    tgt = rng.choice(tgt_pool)
                    w = round(rng.uniform(0.5, 1.5), 3)
                else:
                    src = rng.choice(exc_range + inh_range)
                    tgt = rng.choice(output_range)
                    w = round(rng.uniform(0.8, 2.0), 3)
                # 跳过已存在的边
                if tgt in self.snn.out_edges.get(src, {}):
                    continue
                self.snn.connect(src, tgt, weight=w, delay=1)
                added += 1

            logger.info(
                "shadow: perturbed %d edges + added %d structural edges (heterogenous topology)",
                changed, added,
            )

            # 持久化扰动后的网络
            try:
                self.snn.save(self.save_path)
            except Exception as e:
                logger.warning("shadow: perturb save failed: %s", str(e))

            # 写入标记
            with open(self._perturbed_flag_path, "w", encoding="utf-8") as f:
                f.write("ok")
        except Exception as e:
            logger.warning("shadow: perturb failed: %s", str(e))

    async def reason(self, signal: NeuralSignal, context: Dict[str, Any], budget: Any = None):
        from services.brain.coordinator import RegionResult
        from services.brain.compute_budget import RegionBudget

        start = time.time()
        self._stats["shadow_calls"] = self._stats.get("shadow_calls", 0) + 1
        try:
            budget = budget or RegionBudget(time_ms=300, tokens=0, allowed=True)
            if not getattr(budget, "allowed", True):
                return RegionResult(region="shadow:snn_aux", ok=True, result=None,
                                    context={"reason": "shadow disabled by budget"}, elapsed_ms=0)

            input_neurons = self._encode_signal(signal)
            outputs, _ = self.snn.step_with_learning(input_neurons, 2.0)
            result = self._decode_output(outputs, self.snn.get_active_neurons())
            main_decision = context.get("main_snn_result")
            if main_decision is not None and not isinstance(main_decision, str):
                main_decision = getattr(main_decision, "decision", None)
            shadow_decision = result.decision if result else None

            # 对比统计:
            # - agreement: shadow 与主决策都非空且相同
            # - disagreement: 两者都非空但不同,或一方为 null 另一方非 null(真实差异)
            #   null 差异是 shadow 异质化的核心价值--它在主 SNN 无法决策或决策不同的场景中提供不同视角
            if shadow_decision and main_decision:
                if shadow_decision == main_decision:
                    self._stats["agreement"] = self._stats.get("agreement", 0) + 1
                    self._stats["shadow_hits"] = self._stats.get("shadow_hits", 0) + 1
                else:
                    self._stats["disagreement"] = self._stats.get("disagreement", 0) + 1
            elif (shadow_decision and not main_decision) or (not shadow_decision and main_decision):
                # 一方有输出另一方无--记录为 disagreement(带类型区分)
                self._stats["disagreement"] = self._stats.get("disagreement", 0) + 1
                if shadow_decision and not main_decision:
                    self._stats["null_shadow_calls"] = self._stats.get("null_shadow_calls", 0) + 1
                else:
                    self._stats["null_shadow_calls"] = self._stats.get("null_shadow_calls", 0) + 1
            if shadow_decision:
                self._stats["last_shadow_decision"] = shadow_decision
            elif main_decision:
                # shadow 无输出时,记录主决策供回放/审计
                self._stats["last_shadow_decision"] = "<null>"
            if main_decision:
                self._stats["last_main_decision"] = main_decision

            # 写入 shadow 对比日志(JSONL),供回放/审计
            try:
                import datetime
                import json
                cmp_entry = {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "signal_id": signal.id,
                    "signal_type": signal.type,
                    "input_neurons": input_neurons,
                    "main_decision": main_decision,
                    "shadow_decision": shadow_decision,
                    "payload": signal.payload or {},
                    "urgency": signal.urgency,
                    "agreement": self._stats.get("agreement", 0),
                    "disagreement": self._stats.get("disagreement", 0),
                }
                with open(self._shadow_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(cmp_entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

            # 立即落盘 shadow 统计,避免重启丢失
            try:
                self._save_stats()
            except Exception:
                pass

            if result:
                result.signal_id = signal.id
            elapsed = (time.time() - start) * 1000
            return RegionResult(
                region="shadow:snn_aux",
                ok=True,
                result=result,
                context={
                    "shadow": True,
                    "input_neurons": input_neurons,
                    "main_decision": main_decision,
                    "shadow_decision": shadow_decision,
                    "agreement": self._stats.get("agreement", 0),
                    "disagreement": self._stats.get("disagreement", 0),
                },
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return RegionResult(region="shadow:snn_aux", ok=False, error=str(e), elapsed_ms=elapsed)

    def replay_disagreements(self, limit: int = 50, dry_run: bool = True) -> dict:
        """从对比日志回放 disagreement 样本,训练 shadow 向主决策收敛。

        读取 snn_shadow_network_shadow_compare.jsonl,筛选 main_decision != shadow_decision 的样本,
        用 train_from_feedback() 以主决策为正确目标进行微学习。

        Args:
            limit: 最多回放的样本数
            dry_run: True 时只统计不训练;False 时实际训练并保存

        Returns:
            摘要:{ok, samples, matched, trained, strengthened, disagreement_before, disagreement_after}
        """
        import json
        import os

        if not os.path.exists(self._shadow_log_path):
            return {"ok": True, "samples": 0, "matched": 0, "trained": 0,
                    "reason": "no compare log", "disagreement_before": self._stats.get("disagreement", 0)}

        samples = []
        try:
            with open(self._shadow_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        s = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    main_d = s.get("main_decision")
                    shadow_d = s.get("shadow_decision")
                    # 只采样真实差异:两者都非空且不同,或一方 null 另一方非 null
                    if main_d is None and shadow_d is None:
                        continue
                    if main_d == shadow_d:
                        continue
                    samples.append(s)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not samples:
            return {"ok": True, "samples": 0, "matched": 0, "trained": 0,
                    "reason": "no disagreement samples", "disagreement_before": self._stats.get("disagreement", 0)}

        samples = samples[-limit:]
        matched = 0
        trained = 0
        strengthened_before = self._stats.get("edges_strengthened", 0)
        strengthened_penalty_before = self._stats.get("edges_penalized", 0)
        for s in samples:
            sig_id = s.get("signal_id")
            main_d = s.get("main_decision")
            shadow_d = s.get("shadow_decision")
            payload = s.get("payload") or {}
            urgency = s.get("urgency", 50)
            sig_type = s.get("signal_type", "user_request")
            # 目标决策:主决策优先;主无输出则用 shadow 自身决策
            target_decision = main_d if main_d else shadow_d
            # 错误决策:shadow 原本输出(需被惩罚)
            wrong_d = shadow_d if (main_d and shadow_d and main_d != shadow_d) else None
            # 构造回放信号
            signal = NeuralSignal(
                id=sig_id or f"replay-{matched}",
                type=sig_type,
                payload=payload,
                source="shadow_replay",
                urgency=urgency,
            )
            if dry_run:
                matched += 1
                continue
            try:
                res = self.train_from_feedback(
                    signal=signal,
                    correct_decision=target_decision,
                    was_correct=False,
                    wrong_decision=wrong_d,
                    eta=0.16,
                    inject_strength=3.0,
                )
                if res.get("ok"):
                    matched += 1
                    trained += 1
            except Exception:
                continue

        if not dry_run:
            self._stats["replay_count"] = self._stats.get("replay_count", 0) + 1
            try:
                self._save_stats()
            except Exception:
                pass

        return {
            "ok": True,
            "samples": len(samples),
            "matched": matched,
            "trained": trained,
            "strengthened": self._stats.get("edges_strengthened", 0) - strengthened_before,
            "penalized": self._stats.get("edges_penalized", 0) - strengthened_penalty_before,
            "replay_count": self._stats.get("replay_count", 0),
            "dry_run": dry_run,
            "disagreement_before": self._stats.get("disagreement", 0),
        }


shadow_snn_region = ShadowSNNRegion(save_path=os.path.join(_default_brain_config_dir(), "snn_shadow_network.json"))
snn_region = SNNRegion()
