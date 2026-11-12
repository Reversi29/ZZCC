"""services/brain/neuro_registry.py — 通用输入/输出槽注册器

实现"新类型有新槽"的通用探索结构：

- InputRegistry: 新信号类型自动分配新的输入神经元（不挤占旧槽）
- OutputRegistry: 新决策动作自动分配新的输出神经元（动作空间可扩展）
- 探索连接: 新输入神经元通过弱随机连接接入隐藏层，靠 STDP/强化学习收敛

哲学（胚胎发育）:
    敏感期广泛探索（新类型新槽 + 弱随机连接）
    → 竞争收敛（STDP/强化学习决定哪些连接重要）
    → 稳定期（结构变更率下降，进入稳定）

设计原则:
    1. 新类型绝不挤占旧槽（区别于旧 hash % 11 兜底）
    2. 新输入神经元以弱权重随机连接到一批隐藏神经元（探索连接）
    3. 探索连接靠学习自然收敛（非手工接线）
    4. 注册表持久化，重启后新类型映射不丢失
"""
from __future__ import annotations

import json
import logging
import os
import random
from typing import Dict, List, Optional, Set

from services.brain.snn import SNN, NeuronType

logger = logging.getLogger("brain.neuro_registry")


# ── 固定槽边界（与 create_default 保持一致）─────────────────
# 输入神经元: 0-15（类型 0-10 + 紧急度 11 + 金额 12-14 + 详情 15）
# 输出神经元: 32-37（6 种固定决策）
# 隐藏层: 16-31，其中 16-27 兴奋、28-31 抑制
# v3 补丁标记神经元: 38-39

# 固定输入槽上限（0-15 为固定特征槽，新类型从 40 开始分配）
_DEFAULT_TYPE_SLOTS = 11          # 0-10: 原始类型槽
_DEFAULT_FEATURE_SLOTS = 5        # 11-15: urgency/amount/detail 特征槽
_DEFAULT_HIDDEN_START = 16
_DEFAULT_HIDDEN_END = 31          # 16-31 隐藏层（含抑制）
_DEFAULT_OUTPUT_START = 32
_DEFAULT_OUTPUT_END = 37          # 32-37 输出
_PATCH_MARKERS = (38, 39)         # v3 标记神经元（保留）

# 新槽分配起点（避开固定槽和补丁标记）
# 输入槽与输出槽必须分属不同 ID 空间：同一神经元不能既感知又输出
_NEW_INPUT_START = 40             # 新输入类型槽从 40 开始
_NEW_OUTPUT_START = 100           # 新输出动作槽从 100 开始（避开输入槽空间）

# 探索连接参数
_EXPLORE_HIDDEN_POOL = list(range(16, 28))   # 兴奋性隐藏神经元池（16-27）
_EXPLORE_INIT_WEIGHT_MIN = 0.3               # 探索连接初始权重下限
_EXPLORE_INIT_WEIGHT_MAX = 0.6               # 探索连接初始权重上限
_EXPLORE_CONNECT_COUNT = 3                   # 每个新输入连接到隐藏层数量
_EXPLORE_CONNECT_PROB = 0.7                  # 连接概率

# 输入/输出槽空间上限（防无限增长）
# 输入槽从 40 起（≤96），输出槽从 100 起（≤196）
_MAX_INPUT_SLOTS = 96
_MAX_OUTPUT_SLOTS = 196

# 概念槽（开放集感知维度）：概念 → 概念输入神经元
# 概念槽与类型/动作槽分属不同 ID 区：概念是连续感知维度（如 apple/danger/banana），
# 经独立概念中继子网接入，避免污染档位槽 AND 门。
_CONCEPT_START = 220          # 概念输入神经元起点
_CONCEPT_RELAY_START = 230    # 概念中继神经元起点
_MAX_CONCEPT_SLOTS = 320      # 概念槽上限


class InputRegistry:
    """输入槽注册器：新信号类型自动分配新的输入神经元。

    语义: 新类型有新槽，不挤占旧槽。
    映射持久化到 registry.json，重启后不丢失。
    """

    def __init__(self, registry_path: Optional[str] = None):
        config_dir = os.environ.get("BRAIN_CONFIG_DIR", "/app/config_data")
        self.registry_path = registry_path or os.path.join(config_dir, "neuro_registry.json")
        self._type_to_neuron: Dict[str, int] = {}
        self._neuron_to_type: Dict[int, str] = {}
        self._next_slot = _NEW_INPUT_START
        self._load()

    def _load(self):
        """从 registry.json 加载已有映射。"""
        try:
            if os.path.exists(self.registry_path):
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._type_to_neuron = data.get("input_types", {})
                self._neuron_to_type = {v: k for k, v in self._type_to_neuron.items()}
                self._next_slot = data.get("next_input_slot", _NEW_INPUT_START)
                # 确保 next_slot 不与已用槽冲突
                used = set(self._neuron_to_type.keys())
                while self._next_slot in used:
                    self._next_slot += 1
        except Exception as e:
            logger.warning(f"neuro_registry: load failed ({e}), fresh registry")

    def _save(self):
        """持久化映射。"""
        try:
            os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump({
                    "input_types": self._type_to_neuron,
                    "next_input_slot": self._next_slot,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"neuro_registry: save failed ({e})")

    def register(self, sig_type: str) -> int:
        """注册信号类型，返回其输入神经元 ID。

        若已存在返回原槽；否则分配下一个空闲输入神经元。
        """
        sig_type = (sig_type or "").lower()
        if sig_type in self._type_to_neuron:
            return self._type_to_neuron[sig_type]

        if self._next_slot >= _MAX_INPUT_SLOTS:
            logger.warning(f"neuro_registry: input slots exhausted ({_MAX_INPUT_SLOTS}), "
                           f"reusing hash slot for {sig_type}")
            return hash(sig_type) % _DEFAULT_TYPE_SLOTS

        nid = self._next_slot
        self._next_slot += 1
        self._type_to_neuron[sig_type] = nid
        self._neuron_to_type[nid] = sig_type
        self._save()
        logger.info(f"neuro_registry: new input slot {nid} for type '{sig_type}'")
        return nid

    def get(self, sig_type: str) -> Optional[int]:
        """查询类型对应的输入神经元（不注册）。"""
        return self._type_to_neuron.get((sig_type or "").lower())

    def get_type(self, neuron_id: int) -> Optional[str]:
        """输入神经元 → 类型名。"""
        return self._neuron_to_type.get(neuron_id)

    def all_types(self) -> Dict[str, int]:
        """全部已注册类型映射。"""
        return dict(self._type_to_neuron)

    def count(self) -> int:
        """已注册新类型数量。"""
        return len(self._type_to_neuron)


class OutputRegistry:
    """输出槽注册器：新决策动作自动分配新的输出神经元。

    动作空间可扩展（当前 6 种固定，后续可加 batch_approve 等）。
    """

    def __init__(self, registry_path: Optional[str] = None):
        config_dir = os.environ.get("BRAIN_CONFIG_DIR", "/app/config_data")
        self.registry_path = registry_path or os.path.join(config_dir, "neuro_registry.json")
        self._action_to_neuron: Dict[str, int] = {}
        self._neuron_to_action: Dict[int, str] = {}
        self._next_slot = _NEW_OUTPUT_START
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.registry_path):
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._action_to_neuron = data.get("output_actions", {})
                self._neuron_to_action = {v: k for k, v in self._action_to_neuron.items()}
                self._next_slot = data.get("next_output_slot", _NEW_OUTPUT_START)
                # 保护：输出槽必须从 _NEW_OUTPUT_START 起，避免与输入槽冲突
                if self._next_slot < _NEW_OUTPUT_START:
                    self._next_slot = _NEW_OUTPUT_START
                used = set(self._neuron_to_action.keys())
                while self._next_slot in used:
                    self._next_slot += 1
        except Exception as e:
            logger.warning(f"neuro_registry: output load failed ({e})")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump({
                    "output_actions": self._action_to_neuron,
                    "next_output_slot": self._next_slot,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"neuro_registry: output save failed ({e})")

    def register(self, action: str) -> int:
        """注册决策动作，返回其输出神经元 ID。"""
        action = (action or "").lower()
        if action in self._action_to_neuron:
            return self._action_to_neuron[action]

        if self._next_slot >= _MAX_OUTPUT_SLOTS:
            logger.warning(f"neuro_registry: output slots exhausted ({_MAX_OUTPUT_SLOTS})")
            # 回退到固定输出槽 hash（罕见，保底）
            return 32 + (hash(action) % 6)

        nid = self._next_slot
        self._next_slot += 1
        self._action_to_neuron[action] = nid
        self._neuron_to_action[nid] = action
        self._save()
        logger.info(f"neuro_registry: new output slot {nid} for action '{action}'")
        return nid

    def get(self, action: str) -> Optional[int]:
        return self._action_to_neuron.get((action or "").lower())

    def get_action(self, neuron_id: int) -> Optional[str]:
        return self._neuron_to_action.get(neuron_id)

    def all_actions(self) -> Dict[str, int]:
        return dict(self._action_to_neuron)


class NeuroRegistry:
    """组合注册器：输入槽 + 输出槽 + 探索连接管理。

    统一管理"新类型有新槽"的完整生命周期：
    1. 新类型注册 → 新输入神经元 + 探索连接到隐藏层
    2. 新动作注册 → 新输出神经元 + 从隐藏层探索连接
    3. 连接探索由 STDP/强化学习自然收敛（不做手工接线）
    """

    def __init__(self, snn: SNN, registry_path: Optional[str] = None):
        self.snn = snn
        self.inputs = InputRegistry(registry_path)
        self.outputs = OutputRegistry(registry_path)

    # ── 输入槽管理 ──────────────────────────────────────────
    def ensure_input(self, sig_type: str) -> int:
        """确保信号类型有输入槽；新建时添加神经元 + 探索连接。"""
        nid = self.inputs.get(sig_type)
        if nid is not None:
            return nid
        nid = self.inputs.register(sig_type)
        self._ensure_neuron_exists(nid)
        self._connect_exploration(nid)
        return nid

    # ── 输出槽管理 ──────────────────────────────────────────
    def ensure_output(self, action: str) -> int:
        """确保动作有输出槽；新建时添加神经元 + 探索连接。"""
        nid = self.outputs.get(action)
        if nid is not None:
            return nid
        nid = self.outputs.register(action)
        self._ensure_neuron_exists(nid)
        self._connect_output_exploration(nid)
        return nid

    # ── 内部：确保神经元存在 ───────────────────────────────
    def _ensure_neuron_exists(self, nid: int):
        """确保神经元存在且类型正确（add_neuron 自动扩展 num_neurons）。"""
        if nid >= self.snn.num_neurons:
            self.snn.add_neuron(nid, NeuronType.INPUT, threshold=0.5)
        else:
            # 已存在但可能是旧槽，确保类型正确
            n = self.snn.neurons[nid]
            if n.neuron_type != NeuronType.INPUT:
                n.neuron_type = NeuronType.INPUT
                n.threshold = 0.5

    # ── 内部：探索连接（敏感期广泛连接）────────────────────
    def _connect_exploration(self, input_nid: int):
        """新输入神经元 → 广泛连接到兴奋性隐藏神经元（探索连接）。

        敏感期广泛探索：连接全部兴奋性隐藏层，权重与固定拓扑一致
        （0.90），确保新类型能参与推理；连接选择靠 STDP/强化收敛。
        """
        hidden_pool = [h for h in _EXPLORE_HIDDEN_POOL
                       if h < self.snn.num_neurons]
        if not hidden_pool:
            return
        for hid in hidden_pool:
            self.snn.connect(input_nid, hid, weight=0.90, delay=1)
        logger.info(f"neuro_registry: input {input_nid} exploration "
                    f"→ {hidden_pool} (w=0.90)")

    def _connect_output_exploration(self, output_nid: int):
        """新输出神经元 ← 从兴奋性隐藏神经元广泛探索连接（权重 0.90）。"""
        hidden_pool = [h for h in _EXPLORE_HIDDEN_POOL
                       if h < self.snn.num_neurons]
        if not hidden_pool:
            return
        for hid in hidden_pool:
            self.snn.connect(hid, output_nid, weight=0.90, delay=1)
        logger.info(f"neuro_registry: output {output_nid} exploration "
                    f"← {hidden_pool} (w=0.90)")


def build_registry(snn: SNN) -> NeuroRegistry:
    """构建组合注册器（便捷工厂）。"""
    return NeuroRegistry(snn)


class ConceptRegistry:
    """概念槽注册器：开放集概念自动分配概念输入神经元。

    概念（如 apple/danger/banana/任何新概念）是连续感知维度，
    每个概念有自己的输入神经元 + 概念中继子网，经 STDP/反馈学习
    学会"概念→决策"连接。概念槽走独立 ID 区（220+），
    不与类型槽（40+）/动作槽（100+）/连续通道（200/201）冲突。

    哲学：概念空间开放，网络自己长出感知槽，靠学习收敛语义。
    """

    def __init__(self, registry_path: Optional[str] = None):
        config_dir = os.environ.get("BRAIN_CONFIG_DIR", "/app/config_data")
        self.registry_path = registry_path or os.path.join(config_dir, "neuro_registry.json")
        self._concept_to_neuron: Dict[str, int] = {}
        self._neuron_to_concept: Dict[int, str] = {}
        self._next_slot = _CONCEPT_START
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.registry_path):
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._concept_to_neuron = data.get("concept_slots", {})
                self._neuron_to_concept = {v: k for k, v in self._concept_to_neuron.items()}
                self._next_slot = data.get("next_concept_slot", _CONCEPT_START)
                if self._next_slot < _CONCEPT_START:
                    self._next_slot = _CONCEPT_START
                used = set(self._neuron_to_concept.keys())
                while self._next_slot in used:
                    self._next_slot += 1
        except Exception as e:
            logger.warning(f"neuro_registry: concept load failed ({e})")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump({
                    "concept_slots": self._concept_to_neuron,
                    "next_concept_slot": self._next_slot,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"neuro_registry: concept save failed ({e})")

    def register(self, concept: str) -> int:
        """注册概念，返回其概念输入神经元 ID。

        若已存在返回原槽；否则分配下一个空闲概念神经元。
        """
        concept = (concept or "").lower()
        if concept in self._concept_to_neuron:
            return self._concept_to_neuron[concept]

        if self._next_slot >= _MAX_CONCEPT_SLOTS:
            logger.warning(f"neuro_registry: concept slots exhausted ({_MAX_CONCEPT_SLOTS})")
            return self._next_slot - 1

        nid = self._next_slot
        self._next_slot += 1
        self._concept_to_neuron[concept] = nid
        self._neuron_to_concept[nid] = concept
        self._save()
        logger.info(f"neuro_registry: new concept slot {nid} for '{concept}'")
        return nid

    def get(self, concept: str) -> Optional[int]:
        return self._concept_to_neuron.get((concept or "").lower())

    def get_concept(self, neuron_id: int) -> Optional[str]:
        return self._neuron_to_concept.get(neuron_id)

    def all_concepts(self) -> Dict[str, int]:
        return dict(self._concept_to_neuron)

    def count(self) -> int:
        return len(self._concept_to_neuron)
