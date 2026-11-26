"""services/brain/development.py — 发育式 SNN 结构形成（增殖→探索→分化）

用户 2026-11-26 洞察：
- 人脑神经元先增殖再分化，突触由无到有探索
- 当前 SNN 增值分化的骨架未形成（生产网络 40-199 区 160 神经元 0 内部边）
- 单网络自发分簇成脑区，加弱引导信号避免完全乱分化

本模块实现四阶段发育（详见 DEVELOPMENT.md）：

Stage 1  增殖期  : 大量生成未分化神经元（动态区扩容），不接线
Stage 2  突触探索: 突触从无到有，弱随机连接互相试探，STDP/强化收敛
Stage 3  分化期  : 自发分簇成功能脑区（感知/语义/决策）+ 弱引导

设计原则：
1. **不破坏现有 12/12**：发育只作用于动态区（40-199）与预留区，
   固定核心（0-39）完全不动（plasticity_core_freeze 已保护）
2. **弱引导**：标签/概念先验 + 共同激活 + 化学亲和梯度 + 侧向抑制，
   防完全乱分化（非纯随机）
3. **可观测**：阶段/分簇/边数/聚类统计可查（/brain/dev/status）
4. **渐进**：发育速率可调，默认保守（不突然改变网络行为）

用法：
    dev = DevelopmentDriver(snn)
    dev.proliferate(n=50)            # 增殖
    dev.explore_synapses()           # 突触探索
    dev.differentiate()              # 分化
    dev.status()                     # 发育状态
"""
from __future__ import annotations

import logging
import math
import random
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from services.brain.snn import NeuronType

logger = logging.getLogger("brain.development")

# 发育区边界：动态区 40-199（输入槽 40-99 / 输出槽 100-199）
# 概念区 220+ 由 concept_registry 管理，不在发育驱动范围内
_DEV_START = 40
_DEV_INPUT_END = 99
_DEV_OUTPUT_START = 100
_DEV_OUTPUT_END = 199
_DEV_END = 199

# 发育参数（默认保守，不突然改变行为）
_DEFAULT_PARAMS = {
    "proliferate_size": 20,        # 每轮增殖神经元数
    "max_proliferate": 200,        # 增殖上限（动态区容量）
    "explore_prob": 0.08,          # 突触探索连接概率（每对神经元）
    "explore_weight_min": 0.15,    # 探索连接初始权重下限
    "explore_weight_max": 0.40,    # 探索连接初始权重上限
    "explore_step": 1,             # 探索连接步长
    "keep_weight": 0.20,           # 突触保留阈值（STDP 后 < 此值剪除）
    "cluster_hop": 3,              # 分簇 BFS 跳数
    "weak_guide": 0.3,             # 弱引导强度（0=纯随机, 1=强先验引导）
    "lateral_inhibition": 0.15,    # 侧向抑制强度
    "synapse_prune_every": 50,     # 突触修剪间隔（时间步）
    "min_cluster_size": 4,         # 最小功能簇大小
    "max_dev_edges": 120,          # 发育区最大内部边（防过度生长，667 边前科）
    "prune_ratio": 0.35,           # 每轮修剪最弱边的比例（收敛）
}


class DevelopmentDriver:
    """发育式结构形成驱动器。

    包装 SNN，提供增殖/突触探索/分化/修剪的发育操作。
    不替换现有推理，只在结构层生长。
    """

    def __init__(self, snn, params: Optional[Dict] = None):
        self.snn = snn
        self.p = dict(_DEFAULT_PARAMS)
        if params:
            self.p.update(params)
        self.stage = "embryo"        # embryo / proliferating / exploring / differentiated
        self.stage_history: List[str] = []
        self._stats = {
            "proliferated": 0,
            "explored_edges": 0,
            "pruned_edges": 0,
            "clusters": [],
            "guide_signals": 0,
        }
        self._last_proliferate_time = 0

    # ── Stage 1: 增殖期 ──────────────────────────────────
    def proliferate(self, n: Optional[int] = None, time: int = 0) -> int:
        """增殖未分化神经元（动态区扩容）。

        只创建神经元，不接线（增殖后进入探索期）。
        """
        n = n or self.p["proliferate_size"]
        created = 0
        # 找动态区空闲槽（40-199 未占用）
        used = {i for i in range(_DEV_START, _DEV_END + 1)
                if i < len(self.snn.neurons)
                and self.snn.neurons[i].neuron_type.value != "unused"}
        candidates = [i for i in range(_DEV_START, _DEV_END + 1) if i not in used]
        # 随机取 n 个（不按顺序，避免 ID 聚类偏置）
        random.shuffle(candidates)
        for nid in candidates[:n]:
            # 未分化神经元：默认 EXCITATORY，高阈值（不轻易放电）
            if nid >= self.snn.num_neurons:
                self.snn.add_neuron(nid, NeuronType.EXCITATORY, threshold=1.2)
            else:
                self.snn.neurons[nid].neuron_type = NeuronType.EXCITATORY
                self.snn.neurons[nid].threshold = 1.2
            created += 1
        if created:
            self._stats["proliferated"] += created
            self._set_stage("proliferating")
            self._last_proliferate_time = time
            logger.info(f"development: proliferated {created} neurons (total {self._stats['proliferated']})")
        return created

    # ── Stage 2: 突触探索 ────────────────────────────────
    def explore_synapses(self, time: int = 0, max_new: Optional[int] = None) -> int:
        """突触从无到有探索：弱随机连接 + 弱引导。

        在动态区神经元之间建立探索连接：
        - 纯随机部分：explore_prob 概率
        - 弱引导部分：共同激活/概念先验倾向连接（weak_guide）

        连接权重低（explore_weight_min~max），靠 STDP/强化收敛；
        弱相关连接会被修剪（keep_weight 阈值）。
        """
        max_new = max_new or 50
        created = 0
        # 边数上限：防过度生长（667 边暴涨前科）
        # 达到 max_dev_edges 后不再新增探索边，转为修剪收敛。
        current_dev_edges = sum(
            1 for s in self.snn.out_edges
            for t in self.snn.out_edges[s]
            if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END
        )
        if current_dev_edges >= self.p["max_dev_edges"]:
            return 0
        max_new = min(max_new, self.p["max_dev_edges"] - current_dev_edges)
        # 动态区已增殖的神经元
        dev_neurons = [
            i for i in range(_DEV_START, _DEV_END + 1)
            if i < len(self.snn.neurons)
            and self.snn.neurons[i].neuron_type.value != "unused"
        ]
        if len(dev_neurons) < 2:
            return 0

        # 概念先验映射：概念区（220+）与动态区的已知语义关联
        # 弱引导：某些动态神经元带先验标签（如感知 vs 语义），倾向同类连接
        guide = self._build_guide_map(dev_neurons)

        attempts = 0
        for src in dev_neurons:
            for tgt in dev_neurons:
                if src == tgt:
                    continue
                if tgt in self.snn.out_edges.get(src, {}):
                    continue  # 已有连接
                attempts += 1
                if attempts > max_new * 20:
                    break
                # 基础概率 + 弱引导加成
                prob = self.p["explore_prob"]
                if guide.get(src) == guide.get(tgt) and guide.get(src) is not None:
                    prob += self.p["weak_guide"] * 0.5  # 同先验群 → 倾向连接
                if random.random() > prob:
                    continue
                # 弱权重连接
                w = random.uniform(self.p["explore_weight_min"], self.p["explore_weight_max"])
                if self.snn.connect(src, tgt, weight=w, step=self.p["explore_step"]):
                    created += 1
                    self._stats["explored_edges"] += 1
                if created >= max_new:
                    break
            if created >= max_new:
                break

        if created:
            logger.info(f"development: explored {created} synapses (total {self._stats['explored_edges']})")
        return created

    def _build_guide_map(self, dev_neurons: List[int]) -> Dict[int, Optional[str]]:
        """构建弱引导映射：神经元 → 先验群标签。

        用 ID 区间做粗引导（输入槽 40-99 → "percept"，输出槽 100-199 → "action"），
        这是弱引导（非硬编码），只倾向同群连接，不强制。
        """
        guide: Dict[int, Optional[str]] = {}
        for nid in dev_neurons:
            if _DEV_INPUT_END >= nid >= _DEV_START:
                guide[nid] = "percept"
            elif _DEV_OUTPUT_END >= nid >= _DEV_OUTPUT_START:
                guide[nid] = "action"
            else:
                guide[nid] = None
        return guide

    # ── Stage 3: 分化期 ──────────────────────────────────
    def differentiate(self, time: int = 0) -> Dict:
        """自发分簇成功能脑区（感知/语义/决策）。

        用拓扑 BFS + 活跃度聚类，加弱引导。
        返回分簇结果（每簇神经元列表）。
        """
        dev_neurons = [
            i for i in range(_DEV_START, _DEV_END + 1)
            if i < len(self.snn.neurons)
            and self.snn.neurons[i].neuron_type.value != "unused"
        ]
        clusters = self._cluster_by_activity(dev_neurons)
        self._stats["clusters"] = [list(c) for c in clusters]
        self._set_stage("differentiated")
        return {"clusters": [list(c) for c in clusters], "count": len(clusters)}

    def _cluster_by_activity(self, dev_neurons: List[int]) -> List[List[int]]:
        """拓扑 BFS 分簇 + 活跃度加权。

        复用 SNN 的 _cluster_by_topology（若存在），否则 BFS 实现。
        """
        if not dev_neurons:
            return []
        # 优先用 SNN 现有聚类（拓扑距离）
        if hasattr(self.snn, "_cluster_by_topology"):
            try:
                clusters = self.snn._cluster_by_topology(dev_neurons)
                return [c for c in clusters if len(c) >= self.p["min_cluster_size"]]
            except Exception:
                pass
        # 回退：简单 BFS
        return self._bfs_clusters(dev_neurons)

    def _bfs_clusters(self, dev_neurons: List[int]) -> List[List[int]]:
        """BFS 跳数聚类（拓扑连通性）。"""
        region_set = set(dev_neurons)
        unvisited = set(dev_neurons)
        clusters = []
        while unvisited:
            seed = min(unvisited)
            queue = [(seed, 0)]
            cluster = set()
            visited = {seed}
            while queue:
                node, d = queue.pop(0)
                if d > self.p["cluster_hop"]:
                    continue
                if node in region_set:
                    cluster.add(node)
                if d == self.p["cluster_hop"]:
                    continue
                for nb in list(self.snn.out_edges.get(node, {}).keys()):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append((nb, d + 1))
                for nb in list(self.snn.in_edges.get(node, {}).keys()):
                    if nb not in visited:
                        visited.add(nb)
                        queue.append((nb, d + 1))
            clusters.append(sorted(cluster))
            unvisited -= cluster
        return [c for c in clusters if len(c) >= self.p["min_cluster_size"]]

    # ── 突触修剪（STDP 后收敛）──────────────────────────
    def prune_weak_synapses(self) -> int:
        """剪除弱突触（权重 < keep_weight），突触收敛。

        模拟突触修剪：探索期大量弱连接，STDP 后重要连接加强、
        冗余连接被剪除（人脑突触修剪）。
        """
        pruned = 0
        for src in list(self.snn.out_edges.keys()):
            for tgt in list(self.snn.out_edges[src].keys()):
                # 只剪发育区连接（不动核心区）
                if not (_DEV_START <= src <= _DEV_END and _DEV_START <= tgt <= _DEV_END):
                    continue
                conn = self.snn.out_edges[src][tgt]
                if conn.weight < self.p["keep_weight"]:
                    self.snn.disconnect(src, tgt)
                    pruned += 1
        if pruned:
            self._stats["pruned_edges"] += pruned
            logger.info(f"development: pruned {pruned} weak synapses (total {self._stats['pruned_edges']})")
        return pruned

    # ── 侧向抑制（分化期，防过度收敛）──────────────────
    def apply_lateral_inhibition(self, clusters: List[List[int]]) -> int:
        """同簇内加弱侧向抑制，防过度收敛成单簇。

        簇内神经元之间加弱抑制边（负权重），鼓励分化。
        """
        added = 0
        for cluster in clusters:
            for i, src in enumerate(cluster):
                for tgt in cluster[i + 1:]:
                    if tgt in self.snn.out_edges.get(src, {}):
                        continue
                    w = -self.p["lateral_inhibition"]
                    if self.snn.connect(src, tgt, weight=w, step=1):
                        added += 1
        if added:
            logger.info(f"development: lateral inhibition {added} edges")
        return added

    # ── 状态 ────────────────────────────────────────────
    def _set_stage(self, stage: str):
        if stage != self.stage:
            self.stage = stage
            self.stage_history.append(stage)

    def status(self) -> Dict:
        """发育状态（可观测 /brain/dev/status）。"""
        dev_neurons = [
            i for i in range(_DEV_START, _DEV_END + 1)
            if i < len(self.snn.neurons)
            and self.snn.neurons[i].neuron_type.value != "unused"
        ]
        dev_edges = [
            (src, tgt) for src in self.snn.out_edges
            for tgt in self.snn.out_edges[src]
            if _DEV_START <= src <= _DEV_END and _DEV_START <= tgt <= _DEV_END
        ]
        return {
            "stage": self.stage,
            "stage_history": self.stage_history,
            "dev_neurons": len(dev_neurons),
            "dev_edges": len(dev_edges),
            "dev_neuron_ids": dev_neurons[:50],
            "proliferated": self._stats["proliferated"],
            "explored_edges": self._stats["explored_edges"],
            "pruned_edges": self._stats["pruned_edges"],
            "clusters": self._stats["clusters"],
            "params": self.p,
        }

    def run_development_cycle(self, time: int = 0) -> Dict:
        """完整发育循环（增殖→探索→分化→修剪），幂等渐进。

        供 Brain Core tick 或手动调用。
        收敛机制：达到 max_dev_edges 后转为修剪最弱边（防 667 边暴涨）。
        """
        # 增殖（若动态区未满）
        if self._stats["proliferated"] < self.p["max_proliferate"]:
            self.proliferate(time=time)
        # 突触探索（边数上限内）
        self.explore_synapses(time=time)
        # 分化（周期刷新）
        clusters = self.differentiate(time=time)
        # 突触修剪：收敛机制
        # - 每 prune_every 步剪弱边
        # - 达到 max_dev_edges 后剪 prune_ratio 最弱边（防过度生长）
        current_dev_edges = sum(
            1 for s in self.snn.out_edges
            for t in self.snn.out_edges[s]
            if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END
        )
        if current_dev_edges >= self.p["max_dev_edges"]:
            self._prune_weakest(self.p["prune_ratio"])
        elif time % self.p["synapse_prune_every"] == 0 and time > 0:
            self.prune_weak_synapses()
        return {"stage": self.stage, **self.status()}

    def _prune_weakest(self, ratio: float) -> int:
        """剪除发育区最弱的 ratio 比例边（收敛，防过度生长）。"""
        dev_edges = [
            (s, t, self.snn.out_edges[s][t].weight)
            for s in self.snn.out_edges
            for t in self.snn.out_edges[s]
            if _DEV_START <= s <= _DEV_END and _DEV_START <= t <= _DEV_END
        ]
        if not dev_edges:
            return 0
        # 按权重升序（最弱先剪）
        dev_edges.sort(key=lambda e: e[2])
        n_prune = max(1, int(len(dev_edges) * ratio))
        pruned = 0
        for s, t, _w in dev_edges[:n_prune]:
            self.snn.disconnect(s, t)
            pruned += 1
        if pruned:
            self._stats["pruned_edges"] += pruned
            logger.info(f"development: converged-pruned {pruned} edges (ratio {ratio})")
        return pruned
