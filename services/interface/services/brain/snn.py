"""
SNN 基底模块 — 带延迟的结构可塑脉冲神经网络。

核心设计：
- 步进式时间（整数计数器，非真实时间）
- 稀疏连接矩阵（只存非零边）
- Hebbian 学习（同步放电加强，不同步减弱）
- 结构可塑（增删神经元/连接）

时间模型：
    t=0:   neuron_A 激活
    t=3:   信号到达 neuron_B（延迟3步）
    t=4:   neuron_B 激活（如果阈值满足）
    ...

每个 step() 推进一个时间步，不需要 sleep 或真实等待。
"""

from __future__ import annotations
import random
from collections import defaultdict
import heapq
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── 神经元类型 ───────────────────────────────────────────────
class NeuronType(Enum):
    INPUT = "input"        # 输入端：被动接收外部信号
    EXCITATORY = "exc"    # 兴奋性计算：汇总入边，达到阈值后 fire
    INHIBITORY = "inh"    # 抑制性计算：fire 时抑制下游
    MODULATORY = "mod"    # 调节型：改变其他神经元的阈值/学习率
    OUTPUT = "output"     # 输出端：将结果输出到外部


@dataclass
class Neuron:
    """单个神经元状态"""
    id: int
    neuron_type: NeuronType = NeuronType.EXCITATORY
    threshold: float = 1.0           # 激活阈值
    membrane: float = 0.0            # 膜电位（累积输入）
    decay: float = 0.95              # 膜电位衰减率
    refractory: int = 3              # 不应期步数
    refractory_until: int = -1       # 不应期截止时间
    last_fire_time: int = -999       # 上次激活时间
    bias: float = 0.0                # 偏置
    is_firing: bool = False          # 当前步是否激活
    fire_count: int = 0              # 总激活次数

    def reset_state(self):
        self.membrane = 0.0
        self.is_firing = False
        self.refractory_until = -1
        self.last_fire_time = -1

    def add_input(self, weight: float):
        """接收一个输入信号（累加膜电位）"""
        if self.refractory_until > 0:
            return  # 不应期内不接收
        self.membrane += weight

    def step(self, t: int):
        """推进一个时间步"""
        self.membrane *= self.decay  # 衰减

    def update_firing(self, t: int, inhibitory_input: float = 0.0):
        """更新激活状态，返回是否激活"""
        self.is_firing = False
        if self.refractory_until > t:
            return False
        # 兴奋性输入 vs 抑制性输入
        effective = self.membrane - inhibitory_input
        if effective >= self.threshold:
            self.is_firing = True
            self.refractory_until = t + self.refractory
            self.last_fire_time = t
            self.fire_count += 1
            self.membrane = 0.0  # fire 后重置
            return True
        return False


# ─── 连接 ────────────────────────────────────────────────────
@dataclass
class Connection:
    """神经元之间的有向连接"""
    source: int      # 源神经元
    target: int      # 目标神经元
    weight: float = 1.0   # 权重（正=兴奋，负=抑制）
    delay: int = 1        # 延迟步数

    def to_dict(self) -> dict:
        return {
            "source": self.source, "target": self.target,
            "weight": self.weight, "delay": self.delay,
        }


# ─── SNN 网络 ────────────────────────────────────────────────
class SNN:
    """脉冲神经网络

    用法：
        net = SNN(num_neurons=10)
        net.add_neuron(0, NeuronType.INPUT)
        net.add_neuron(9, NeuronType.OUTPUT, threshold=0.5)
        net.connect(0, 1, weight=1.0, delay=2)
        # 运行 100 个时间步
        for t in range(100):
            net.inject_input(0, 1.5)
            outputs = net.step()
    """

    TOPOLOGY_VERSION = 2  # v2: 输入层 0-15（信号类型+紧急度+金额分桶+详情）

    def __init__(self, num_neurons: int = 50):
        self.num_neurons = num_neurons
        self.neurons: list[Neuron] = [Neuron(id=i) for i in range(num_neurons)]

        # 出边: source -> {target: Connection}
        self.out_edges: dict[int, dict[int, Connection]] = defaultdict(dict)
        # 入边: target -> {source: Connection}
        self.in_edges: dict[int, dict[int, Connection]] = defaultdict(dict)

        # 待传播事件队列: (arrive_time, source, target, weight)
        self._pending_events: list = []  # heapq-based priority queue

        # 学习参数
        self.eta_plus: float = 0.2   # 同步放电增强率
        self.eta_minus: float = 0.05 # 不同步减弱率
        self.weight_decay: float = 0.0  # 全局权重衰减
        self.max_weight: float = 3.0

        # 输出历史（用于 Hebbian 回溯）
        self._fire_history: dict[int, list[int]] = defaultdict(list)
        self.history_window: int = 20  # 回溯窗口步数

        self.time: int = 0
        self._inhibitory_inputs: defaultdict[int, float] = defaultdict(float)

    # ── 结构操作 ─────────────────────────────────────────────

    def add_neuron(self, neuron_id: int, ntype: NeuronType = NeuronType.EXCITATORY,
                   threshold: float = 1.0, decay: float = 0.95) -> Neuron:
        """添加一个神经元（结构可塑：增加）"""
        if neuron_id >= self.num_neurons:
            self.num_neurons = neuron_id + 1
            while len(self.neurons) <= neuron_id:
                self.neurons.append(Neuron(id=len(self.neurons)))
        n = self.neurons[neuron_id]
        n.neuron_type = ntype
        n.threshold = threshold
        n.decay = decay
        return n

    def remove_neuron(self, neuron_id: int) -> bool:
        """移除神经元（结构可塑：减少）"""
        if neuron_id >= self.num_neurons or neuron_id < 0:
            return False
        n = self.neurons[neuron_id]
        n.is_firing = False
        n.membrane = 0.0
        n.threshold = 99999  # 使其永不激活
        return True

    def connect(self, source: int, target: int, weight: float = 1.0, delay: int = 1) -> bool:
        """添加或修改连接"""
        if source < 0 or source >= self.num_neurons:
            return False
        if target < 0 or target >= self.num_neurons:
            return False
        if source == target:
            return False
        conn = Connection(source=source, target=target, weight=weight, delay=delay)
        self.out_edges[source][target] = conn
        self.in_edges[target][source] = conn
        return True

    def disconnect(self, source: int, target: int) -> bool:
        """断开连接"""
        if source < 0 or source >= self.num_neurons:
            return False
        if target < 0 or target >= self.num_neurons:
            return False
        if target in self.out_edges[source]:
            del self.out_edges[source][target]
            if source in self.in_edges[target]:
                del self.in_edges[target][source]
            return True
        return False

    def set_delay(self, source: int, target: int, delay: int) -> bool:
        """修改连接延迟（路径长短调节）"""
        if source < 0 or source >= self.num_neurons:
            return False
        if target < 0 or target >= self.num_neurons:
            return False
        conn = self.out_edges.get(source, {}).get(target)
        if conn:
            conn.delay = max(1, delay)
            return True
        return False

    def set_weight(self, source: int, target: int, weight: float) -> bool:
        """修改连接权重"""
        if source < 0 or source >= self.num_neurons:
            return False
        if target < 0 or target >= self.num_neurons:
            return False
        conn = self.out_edges.get(source, {}).get(target)
        if conn:
            conn.weight = max(0, min(self.max_weight, weight))
            return True
        return False

    # ── 输入输出 ─────────────────────────────────────────────

    def reset(self):
        """重置所有神经元状态和待传播事件（用于训练后验证）"""
        for n in self.neurons:
            n.reset_state()
        self._pending_events.clear()
        self.time = 0
        self._inhibitory_inputs.clear()
        # 清空激活历史
        self._fire_history.clear()

    def inject_input(self, neuron_id: int, strength: float = 1.0):
        """注入外部输入到指定神经元"""
        if neuron_id < 0 or neuron_id >= self.num_neurons:
            return
        self.neurons[neuron_id].membrane += strength

    def inject_pattern(self, pattern: list[int], strength: float = 1.0):
        """注入一个模式到多个神经元"""
        for nid in pattern:
            self.inject_input(nid, strength)

    def get_outputs(self) -> dict[int, bool]:
        """获取当前步的输出状态"""
        return {
            n.id: n.is_firing
            for n in self.neurons
            if n.neuron_type == NeuronType.OUTPUT
        }

    def get_active_neurons(self) -> list[int]:
        """获取当前步所有激活的神经元"""
        return [n.id for n in self.neurons if n.is_firing]

    def get_state_dict(self) -> dict:
        """获取完整状态快照"""
        return {
            "time": self.time,
            "num_neurons": self.num_neurons,
            "fire_counts": {n.id: n.fire_count for n in self.neurons},
            "neuron_types": {n.id: n.neuron_type.value for n in self.neurons},
            "active": self.get_active_neurons(),
            "outputs": self.get_outputs(),
        }

    # ── 核心计算循环 ─────────────────────────────────────────

    def step(self) -> dict[int, bool]:
        """推进一个时间步。

        流程：
        1. 处理到达的事件（新信号累加到膜电位）
        2. 检查激活（阈值判断）
        3. 传播新激活信号到出边
        4. Hebbian 学习更新权重
        5. 膜电位衰减（为下一步准备）
        6. 记录历史

        关键顺序：事件先于衰减，确保新注入的信号以完整强度参与激活判断。
        衰减在最后执行，削弱旧信号但不影响本步刚到达的信号。

        返回：当前步的输出状态 {neuron_id: is_firing}
        """
        self.time += 1
        t = self.time

        # 1. 处理到达的事件（新信号累加）
        arrived = []
        while self._pending_events and self._pending_events[0][0] <= t:
            arrived.append(heapq.heappop(self._pending_events))

        # 清除上一步的抑制输入
        self._inhibitory_inputs.clear()

        for _, src, tgt, weight in arrived:
            src_neuron = self.neurons[src]
            tgt_neuron = self.neurons[tgt]

            if src_neuron.neuron_type == NeuronType.INHIBITORY:
                self._inhibitory_inputs[tgt] += abs(weight)
            else:
                tgt_neuron.add_input(weight)

        # 2. 检查激活
        fired_this_step: set[int] = set()
        for n in self.neurons:
            inh = self._inhibitory_inputs.get(n.id, 0.0)
            if n.update_firing(t, inhibitory_input=inh):
                fired_this_step.add(n.id)

        # 3. 传播新激活信号
        for n_id in fired_this_step:
            n = self.neurons[n_id]
            for tgt, conn in self.out_edges.get(n_id, {}).items():
                arrive_time = t + conn.delay
                heapq.heappush(self._pending_events, (arrive_time, n_id, tgt, conn.weight))

        # 4. Hebbian 学习
        self._hebbian_update(t, fired_this_step)

        # 5. 膜电位衰减（本步结束后，旧信号消退）
        for n in self.neurons:
            n.step(t)

        # 6. 记录历史
        for n_id in fired_this_step:
            self._fire_history[n_id].append(t)
            if len(self._fire_history[n_id]) > self.history_window:
                self._fire_history[n_id].pop(0)

        return self.get_outputs()

    # ── 学习 ─────────────────────────────────────────────────

    def _hebbian_update(self, t: int, fired_now: set[int]):
        """STDP (Spike-Timing-Dependent Plasticity) 学习

        在目标神经元激活时检查：源神经元是否在延迟窗口内先激活过？

        规则：
        - 目标激活，且源在 delay+2 窗口内先激活 → LTP（加强）
        - 目标激活，但源太久没激活 → LTD（减弱）
        - 全局 weight decay 防止权重爆炸
        """
        for target_id in fired_now:
            tgt_neuron = self.neurons[target_id]
            tgt_fire_t = tgt_neuron.last_fire_time

            for src_id, conn in self.in_edges.get(target_id, {}).items():
                src_neuron = self.neurons[src_id]
                src_fire_t = src_neuron.last_fire_time

                if src_fire_t >= 0 and tgt_fire_t > src_fire_t:
                    gap = tgt_fire_t - src_fire_t
                    if gap <= conn.delay + 2:
                        # STDP LTP：源先激活，目标在窗口内跟随
                        conn.weight = min(
                            self.max_weight,
                            conn.weight + self.eta_plus,
                        )
                    else:
                        # 源太久没激活，目标自行激活 → 减弱
                        conn.weight = max(0, conn.weight - self.eta_minus)
                elif src_fire_t >= 0:
                    # 源激活过但目标先激活（异常）→ 减弱
                    conn.weight = max(0, conn.weight - self.eta_minus)

        # 全局权重衰减（防止权重爆炸）
        if self.weight_decay > 0:
            for src in list(self.out_edges.keys()):
                for tgt, conn in list(self.out_edges[src].items()):
                    conn.weight = max(0, conn.weight - self.weight_decay)

    # ── 高级接口 ─────────────────────────────────────────────

    def run(self, steps: int = 100, input_fn=None) -> list[dict[int, bool]]:
        """运行多个时间步，返回每步的输出。

        input_fn: callable(t, snn) -> None，每步开始前调用以注入输入
        """
        outputs_history = []
        for t in range(steps):
            if input_fn:
                input_fn(t, self)
            outputs_history.append(self.step())
        return outputs_history

    def train_hebbian(self, pattern: list[int], steps: int = 50, strength: float = 1.0):
        """用 Hebbian 方式训练一个输入模式到输出。

        反复注入 pattern，让神经元之间建立同步放电模式。
        """
        for t in range(steps):
            self.inject_pattern(pattern, strength)
            self.step()

    def train_by_association(self, input_pattern: list[int],
                            output_neuron: int, steps: int = 50):
        """奖励调制 Hebbian 训练：建立输入模式 -> 输出关联。

        两阶段时序：
        1. 注入输入模式 → 输入神经元激活（t 步）
        2. 注入奖励信号 → 输出神经元激活（t+1 步）
        3. 奖励调制 STDP：回溯先激活的源，加强/创建到目标的连接

        时序分离是关键——STDP 需要源先于目标激活才能识别因果关系。
        效果：训练后输入模式无需奖励即可激活输出。
        """
        for _ in range(steps):
            # 阶段1：注入输入模式，激活输入神经元
            self.inject_pattern(input_pattern, 1.5)
            self.step()

            # 阶段2：注入奖励信号，激活输出神经元
            self.inject_input(output_neuron, 2.0)
            outputs = self.step()

            # 阶段3：奖励调制——加强所有先激活的源到目标的连接
            if outputs.get(output_neuron, False):
                self._reward_modulated_strengthen(
                    output_neuron, eta=0.05,
                    auto_create=True, auto_create_weight=0.15,
                )

    def _reward_modulated_strengthen(self, target_id: int, eta: float = 0.02,
                                     auto_create: bool = False,
                                     auto_create_weight: float = 0.1):
        """奖励调制加强：回溯所有先激活的神经元，加强到目标的连接。

        类比：动物大脑中多巴胺奖励机制——当结果被奖励时，
        所有先于结果发生的活动都得到加强。

        Args:
            target_id: 被奖励的目标神经元 ID
            eta: 每次加强的权重增量
            auto_create: 是否允许创建新的连接（突触发生）
            auto_create_weight: 新连接的初始权重
        """
        tgt_neuron = self.neurons[target_id]
        tgt_fire_t = tgt_neuron.last_fire_time
        if tgt_fire_t < 0:
            return

        strengthened = 0
        for n in self.neurons:
            if n.id == target_id:
                continue
            if n.last_fire_time >= 0 and n.last_fire_time < tgt_fire_t:
                # 源先激活，目标后被奖励 → 因果关系成立
                conn = self.out_edges.get(n.id, {}).get(target_id)
                if conn:
                    old_w = conn.weight
                    conn.weight = min(self.max_weight, conn.weight + eta)
                    strengthened += 1
                elif auto_create:
                    # 突触发生：创建新的直接连接
                    self.connect(n.id, target_id, weight=auto_create_weight, delay=1)
                    strengthened += 1

                # LTD 实验结论：竞争性 LTD 在当前架构下反效果。
                # auto_create 的 input→output 直连是非选择性通道，
                # LTD 削弱 hidden→output 后只剩非选择性直连，准确率暴减。
                # 解决方案待定：需 winner-take-all 隐藏层或竞争性学习机制。

        return strengthened

    # ── 调试 / 可视化 ────────────────────────────────────────

    # ── 持续学习循环 ──────────────────────────────────────

    # EWC (Elastic Weight Consolidation) 参数
    EWC_ALPHA = 100.0       # 重要性权重系数
    EWC_IMPORTANCE_DECAY = 0.99  # 重要性衰减（防止全部饱和）

    # 探索参数（混乱权利）
    EXPLORATION_BASE_RATE = 0.1   # 基础探索率 10%
    EXPLORATION_DECAY = 0.95      # 稳定性衰减（连续正确决策后探索率降低）
    EXPLORATION_BOOST = 0.3       # 边界探测增强率（决策翻转时提升探索率）

    def __init__(self, num_neurons: int = 50):
        self.num_neurons = num_neurons
        self.neurons: list[Neuron] = [Neuron(id=i) for i in range(num_neurons)]

        # 出边: source -> {target: Connection}
        self.out_edges: dict[int, dict[int, Connection]] = defaultdict(dict)
        # 入边: target -> {source: Connection}
        self.in_edges: dict[int, dict[int, Connection]] = defaultdict(dict)

        # 待传播事件队列: (arrive_time, source, target, weight)
        self._pending_events: list = []  # heapq-based priority queue

        # 学习参数
        self.eta_plus: float = 0.2   # 同步放电增强率
        self.eta_minus: float = 0.05 # 不同步减弱率
        self.weight_decay: float = 0.0  # 全局权重衰减
        self.max_weight: float = 3.0

        # 输出历史（用于 Hebbian 回溯）
        self._fire_history: dict[int, list[int]] = defaultdict(list)
        self.history_window: int = 20  # 回溯窗口步数

        self.time: int = 0
        self._inhibitory_inputs: defaultdict[int, float] = defaultdict(float)

        # ── 持续学习状态 ──
        self._ewc_importance: dict[tuple[int, int], float] = defaultdict(float)
        self._exploration_rate: float = self.EXPLORATION_BASE_RATE
        self._consecutive_correct: int = 0
        self._total_decisions: int = 0
        self._recent_decisions: list[bool] = []  # True=正确, False=错误

    def reset(self):
        """重置所有神经元状态和待传播事件（用于训练后验证）"""
        for n in self.neurons:
            n.reset_state()
        self._pending_events.clear()
        self.time = 0
        self._inhibitory_inputs.clear()
        # 清空激活历史
        self._fire_history.clear()

    def reset_learning_state(self):
        """重置学习状态（不重置网络权重）。用于推理前清理。

        与 reset() 不同：保留权重和 EWC 重要性，只清理事件队列和神经元状态。
        这样学习历史可以跨推理保留，实现真正的持续学习。
        """
        for n in self.neurons:
            n.reset_state()
        self._pending_events.clear()
        self._inhibitory_inputs.clear()
        self._fire_history.clear()
        # 不清空 time，让学习计数器继续累积

    # ── EWC (Elastic Weight Consolidation) ────────────────────

    def _update_ewc_importance(self, fired_neurons: set[int]):
        """更新权重重要性（EWC 核心）。

        重要权重：被频繁激活的神经元参与的连接
        重要性高的权重在后续学习中更新率降低，防止灾难性遗忘
        """
        for n_id in fired_neurons:
            # 出边重要性（该神经元的输出连接）
            for tgt, conn in self.out_edges.get(n_id, {}).items():
                key = (n_id, tgt)
                self._ewc_importance[key] = min(
                    10.0,  # 最大重要性
                    self._ewc_importance[key] + 0.01
                )

    def _get_ewc_multiplier(self, src: int, tgt: int) -> float:
        """获取 EWC 学习率乘数。

        重要性越高，乘数越小（学习越慢）
        重要性 0 → 乘数 1.0（正常学习）
        重要性 10 → 乘数 0.1（强烈保护）
        """
        importance = self._ewc_importance.get((src, tgt), 0.0)
        return 1.0 / (1.0 + self.EWC_ALPHA * importance)

    # ── 探索机制（混乱权利）────────────────────────────────

    def _adjust_exploration_rate(self, decision_was_correct: bool):
        """自动调节探索率。

        决策正确 → 稳定性提升 → 探索率衰减
        决策错误/翻转 → 探索率提升（边界探测增强）
        """
        if decision_was_correct:
            self._consecutive_correct += 1
            # 连续正确后探索率指数衰减
            self._exploration_rate *= self.EXPLORATION_DECAY
        else:
            self._consecutive_correct = 0
            # 错误时探索率回升
            self._exploration_rate = min(
                0.5,  # 最大探索率 50%
                self._exploration_rate + self.EXPLORATION_BOOST
            )

        # 底线保护：探索率不低于 2%
        self._exploration_rate = max(0.02, self._exploration_rate)

    def _explore(self, active_neurons: list[int]) -> bool:
        """执行一次探索：随机扰动一条边，看决策是否翻转。

        返回 True 表示探索成功（发现了边界模式）

        探索方式：
        1. 随机选择一个已激活的隐藏神经元
        2. 随机抑制或增强其一条出边
        3. 重新前向传播，观察输出是否变化
        4. 如果输出翻转 → 边界模式，增强该连接的权重
        """
        if random.random() >= self._exploration_rate:
            return False

        # 选择活跃的隐藏层神经元（16-31）
        hidden_active = [n for n in active_neurons if 16 <= n < 32]
        if not hidden_active:
            return False

        probe_neuron = random.choice(hidden_active)

        # 选择该神经元的一条出边
        out_conns = list(self.out_edges.get(probe_neuron, {}).items())
        if not out_conns:
            return False

        tgt, conn = random.choice(out_conns)
        original_weight = conn.weight

        # 随机扰动：抑制或增强
        if random.random() < 0.5:
            conn.weight *= 0.3  # 抑制
        else:
            conn.weight = min(self.max_weight, conn.weight * 2.0)  # 增强

        # 重新前向传播（简化版：只看输出层）
        # 注：完整重放成本高，这里用启发式：检查扰动后的有效输入
        effective_input = sum(
            c.weight for c in self.out_edges.get(probe_neuron, {}).values()
        )

        # 恢复原始权重
        conn.weight = original_weight

        # 如果有效输入接近输出阈值 → 边界模式，增强连接
        output_neuron = self.neurons[tgt]
        if abs(effective_input - output_neuron.threshold) < 0.5:
            # 边界模式：增强这条边的权重
            conn.weight = min(self.max_weight, conn.weight + 0.1)
            return True

        return False

    # ── 持续学习核心方法 ──────────────────────────────────────

    def step_with_learning(
        self,
        input_neurons: list[int],
        strength: float = 1.5,
        expected_decision: Optional[int] = None,
    ) -> tuple[dict[int, bool], bool]:
        """融合推理+微学习的单步计算。

        与 step() 的区别：
        - 自动注入输入
        - 每步微学习（不是批量训练）
        - 探索机制（混乱权利）
        - EWC 防遗忘
        - 返回输出 + 是否检测到边界模式

        Args:
            input_neurons: 输入神经元 ID 列表
            strength: 注入强度
            expected_decision: 期望的输出神经元 ID（用于反馈学习，可选）

        Returns:
            (outputs, boundary_detected)
            - outputs: {neuron_id: is_firing}
            - boundary_detected: 是否检测到边界模式（探索成功）
        """
        # 重置推理状态（保留学习历史）
        self.reset_learning_state()

        # 注入输入
        self.inject_pattern(input_neurons, strength)

        outputs: dict[int, bool] = {}
        boundary_detected = False

        # 运行多个时间步（信号需要传播）
        for step in range(10):
            outputs = self.step()
            active = self.get_active_neurons()

            # 探索机制
            if active and self._explore(active):
                boundary_detected = True

            # 如果输出已稳定，提前退出
            fired_outputs = [nid for nid, v in outputs.items() if v]
            if fired_outputs and step >= 3:
                break

        # ── 微学习 ──
        # 1. 更新 EWC 重要性
        active = self.get_active_neurons()
        self._update_ewc_importance(set(active))

        # 2. 如果有反馈，进行强化学习
        if expected_decision is not None:
            actual_output = [nid for nid, v in outputs.items() if v]
            is_correct = expected_decision in actual_output

            # 调节探索率
            self._adjust_exploration_rate(is_correct)

            # 记录决策历史
            self._total_decisions += 1
            self._recent_decisions.append(is_correct)
            if len(self._recent_decisions) > 100:
                self._recent_decisions.pop(0)

            # 微学习：加强正确路径，削弱错误路径
            self._micro_learn(expected_decision, actual_output, is_correct, active)

        return outputs, boundary_detected

    def _micro_learn(
        self,
        target_output: int,
        actual_outputs: list[int],
        is_correct: bool,
        active_neurons: list[int],
    ):
        """微学习：根据推理结果微调权重。

        与 _reward_modulated_strengthen 的区别：
        - 步长更小（η=0.001 vs 0.05）
        - 不创建新连接（避免破坏拓扑）
        - EWC 保护重要权重
        """
        micro_eta = 0.001  # 微学习步长

        if is_correct:
            # 正确：加强目标输出的入边
            for src_id in active_neurons:
                conn = self.out_edges.get(src_id, {}).get(target_output)
                if conn and conn.weight > 0:
                    # EWC 保护：重要权重学习更慢
                    ewc_mult = self._get_ewc_multiplier(src_id, target_output)
                    conn.weight = min(
                        self.max_weight,
                        conn.weight + micro_eta * ewc_mult
                    )
        else:
            # 错误：削弱实际输出（非目标）的入边
            for wrong_out in actual_outputs:
                if wrong_out == target_output:
                    continue
                for src_id in active_neurons:
                    conn = self.out_edges.get(src_id, {}).get(wrong_out)
                    if conn and conn.weight > 0:
                        # EWC 保护
                        ewc_mult = self._get_ewc_multiplier(src_id, wrong_out)
                        conn.weight = max(
                            0.0,
                            conn.weight - micro_eta * ewc_mult
                        )

            # 同时轻微加强目标输出（即使错误，也要尝试靠近正确方向）
            for src_id in active_neurons:
                conn = self.out_edges.get(src_id, {}).get(target_output)
                if conn:
                    ewc_mult = self._get_ewc_multiplier(src_id, target_output)
                    conn.weight = min(
                        self.max_weight,
                        conn.weight + micro_eta * 0.5 * ewc_mult
                    )

    # ── 持久化 ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """序列化为 JSON 可存储字典。"""
        neurons = []
        for n in self.neurons:
            neurons.append({
                "id": n.id,
                "type": n.neuron_type.value,
                "threshold": n.threshold,
                "decay": n.decay,
                "refractory": n.refractory,
                "fire_count": n.fire_count,
                "last_fire_time": n.last_fire_time,
            })
        edges = []
        for src in self.out_edges:
            for tgt, conn in self.out_edges[src].items():
                edges.append({
                    "source": src, "target": tgt,
                    "weight": conn.weight, "delay": conn.delay,
                })
        return {
            "topology_version": self.TOPOLOGY_VERSION,
            "num_neurons": self.num_neurons,
            "time": self.time,
            "eta_plus": self.eta_plus,
            "eta_minus": self.eta_minus,
            "weight_decay": self.weight_decay,
            "max_weight": self.max_weight,
            "history_window": self.history_window,
            "neurons": neurons,
            "edges": edges,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SNN":
        """从字典恢复网络。"""
        if data.get("topology_version", 1) != cls.TOPOLOGY_VERSION:
            raise ValueError("topology version mismatch")
        net = cls(num_neurons=data.get("num_neurons", 50))
        net.time = data.get("time", 0)
        net.eta_plus = data.get("eta_plus", 0.01)
        net.eta_minus = data.get("eta_minus", 0.005)
        net.weight_decay = data.get("weight_decay", 0.0)
        net.max_weight = data.get("max_weight", 5.0)
        net.history_window = data.get("history_window", 20)

        for nd in data.get("neurons", []):
            nid = nd["id"]
            if nid < len(net.neurons):
                n = net.neurons[nid]
                n.neuron_type = NeuronType(nd.get("type", "exc"))
                n.threshold = nd.get("threshold", 1.0)
                n.decay = nd.get("decay", 0.95)
                n.refractory = nd.get("refractory", 3)
                n.fire_count = nd.get("fire_count", 0)
                n.last_fire_time = nd.get("last_fire_time", -999)
            else:
                n = Neuron(id=nid)
                n.neuron_type = NeuronType(nd.get("type", "exc"))
                n.threshold = nd.get("threshold", 1.0)
                n.decay = nd.get("decay", 0.95)
                n.refractory = nd.get("refractory", 3)
                n.fire_count = nd.get("fire_count", 0)
                n.last_fire_time = nd.get("last_fire_time", -999)
                net.neurons.append(n)

        for ed in data.get("edges", []):
            net.connect(ed["source"], ed["target"],
                       weight=ed["weight"], delay=ed["delay"])
        return net

    def save(self, path: str) -> bool:
        """保存到 JSON 文件。"""
        import json
        try:
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    @classmethod
    def load(cls, path: str) -> Optional["SNN"]:
        """从 JSON 文件加载。"""
        import json
        import os
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print("snn: load failed (%s), creating default" % e)
            return None

    # ── 默认拓扑 ────────────────────────────────────────────

    @classmethod
    def create_default(cls, seed: int = 7) -> "SNN":
        random.seed(seed)
        """创建 Brain AI 默认拓扑（v2）。

        三层结构：
        - 输入层 (0-15): 信号类型 0-10 + 紧急度高 11 + 金额分桶 12-14 + 有详情 15
        - 隐藏层 (16-31): 计算模式 16-27 + 抑制调节 28-31
        - 输出层 (32-37): 6 种决策类型（ID 保持不变，兼容既有映射）

        设计原则：
        - 信号类型与 payload 特征（金额/详情）共同编码输入，
          使同类型信号可按 payload 区分
          （如 approval_pending 小额 -> flag / 大额 -> escalate）
        - 隐藏层做交叉关联；抑制层抑制误触发的决策输出
        """
        net = cls(num_neurons=40)

        input_types = [
            ("expense", 0),             # 0
            ("approval_pending", 1),    # 1
            ("threshold_breach", 2),   # 2
            ("user_request", 3),        # 3
            ("cron_alert", 4),          # 4
            ("external_event", 5),      # 5 (含 plugin_event)
            ("error", 6),               # 6
            ("query", 7),               # 7
            ("chitchat", 8),            # 8
            ("system", 9),              # 9
            ("noise", 10),              # 10
            ("urgency_high", 11),       # 紧急度 >= 70
            ("amount_low", 12),         # 金额 <= 1000
            ("amount_medium", 13),      # 1000 < 金额 <= 100000
            ("amount_high", 14),        # 金额 > 100000
            ("has_detail", 15),         # payload 含描述/标题/文本等详情字段
            ("ap_low_marker", 38),      # approval_pending + 低紧急度(<40)
            ("user_action_marker", 39), # user_request + 动作关键词
        ]
        for name, nid in input_types:
            net.add_neuron(nid, NeuronType.INPUT, threshold=0.5)

        # 隐藏层：计算(16-27) + 抑制(28-31)
        # 多输入隐藏神经元用高阈值(1.5)实现 AND 逻辑，单输入用低阈值(0.8)
        multi_input_threshold = 1.5  # 需要至少2个输入(0.9+0.9=1.8)才触发
        single_input_threshold = 0.8  # 单个输入(0.9)即可触发
        multi_input_ids = {16, 17, 18, 19, 20, 21, 26, 27}  # 有2+ structured inputs
        single_input_ids = {22, 23, 24, 25}  # 只有1 structured input
        for nid in range(16, 28):
            th = multi_input_threshold if nid in multi_input_ids else single_input_threshold
            net.add_neuron(nid, NeuronType.EXCITATORY, threshold=th)
        for nid in range(28, 32):
            net.add_neuron(nid, NeuronType.INHIBITORY, threshold=1.0)

        # 输出层：决策类型
        output_types = [
            ("auto_approve", 32),
            ("reject", 33),
            ("escalate", 34),
            ("flag", 35),
            ("no_action", 36),
            ("chat", 37),
        ]
        for name, nid in output_types:
            net.add_neuron(nid, NeuronType.OUTPUT, threshold=1.0)

        # 结构化隐藏层：每个神经元专检一个 (signal_type, amount_bucket) 组合
        # 这样只有匹配的隐藏神经元才放电，提供组合特征选择性
        # H16: expense + low    → 32 (auto_approve)
        # H17: expense + medium → 34 (escalate)
        # H18: expense + high   → 34 (escalate)
        # H19: ap + low         → 35 (flag)
        # H20: ap + medium      → 34 (escalate)
        # H21: ap + high        → 34 (escalate)
        # H22: user_request     → 37 (chat)
        # H23: error            → 35 (flag)
        # H24: query            → 36 (no_action)
        # H25: chitchat         → 37 (chat)
        # H26: threshold_breach + high → 34 (escalate)
        # H27: system           → 36 (no_action)
        # 注：noise 无专用计算神经元——NOISE intent 下 SNN 已禁用（compute_budget）
        structured = [
            # (hid_id, [input_ids], [output_ids], out_weight)
            # out_weight > output threshold (1.0) to ensure single hidden neuron can activate output
            (16, [0, 12], [32], 1.5),         # expense + low → auto_approve
            (17, [0, 13], [34], 2.0),         # expense + medium → escalate
            (18, [0, 14], [34], 1.5),         # expense + high → escalate
            (19, [1, 12], [35], 1.5),         # ap + low → flag
            (20, [1, 13], [34], 1.5),         # ap + medium → escalate
            (21, [1, 14], [34], 1.5),         # ap + high → escalate
            (22, [3], [37], 1.5),             # user_request → chat
            (23, [6], [35], 1.5),             # error → flag
            (24, [7], [36], 1.5),             # query → no_action
            (25, [8], [37], 1.5),             # chitchat → chat
            (26, [2, 14], [34], 1.5),         # threshold_breach + high → escalate
            (27, [9], [36], 1.5),             # system → no_action
        ]
        for hid_id, inputs, outputs, w in structured:
            for inp_id in inputs:
                net.connect(inp_id, hid_id, weight=0.9, delay=1)
            for out_id in outputs:
                net.connect(hid_id, out_id, weight=w, delay=1)

        # ── 补充缺失输入神经元出边 ────────────────────────────
        # 高紧急度(11)放大 escalate 路径（与信号类型 AND 组合，阈值仍保持选择性）
        _escalate_hidden = {17, 18, 20, 21, 26}
        for inp_id in (4, 5, 11):
            for hid_id in sorted(_escalate_hidden):
                net.connect(inp_id, hid_id, weight=0.9, delay=1)

        # ── v3 消歧标记路由 ───────────────────────────────────
        # 38 (ap_low_marker): ap+低紧急度 → auto_approve，抑制 flag 误触
        net.connect(38, 32, weight=1.5, delay=1)
        net.connect(38, 19, weight=-0.6, delay=1)
        # 39 (user_action_marker): user_request 带动作关键词 → escalate
        net.connect(39, 17, weight=0.9, delay=1)
        net.connect(3, 17, weight=0.9, delay=1)
        # H19 阈值提升到 1.8（需 1+12 双输入 1.8 才 flag，38 抑制时 1.8-0.6=1.2 不触发）
        net.neurons[19].threshold = 1.8
        # ap 低紧急度直连 auto_approve 辅助路径
        net.connect(1, 32, weight=0.6, delay=1)
        net.connect(12, 32, weight=0.6, delay=1)
        # threshold_breach + 低紧急度 → auto_approve
        net.connect(2, 32, weight=1.5, delay=1)

        # 无随机补充连接——避免非选择性激活

        # 抑制层 -> 输出层（抑制性）
        for inh_id in range(28, 32):
            for out_id in range(32, 38):
                if random.random() < 0.3:
                    net.connect(inh_id, out_id, weight=-0.3, delay=1)

        return net

    def print_structure(self):
        """打印网络结构"""
        print(f"SNN: {self.num_neurons} neurons, time={self.time}")
        print(f"Edges: {sum(len(v) for v in self.out_edges.values())}")
        for n in self.neurons:
            if n.is_firing:
                print(f"  [{n.id}] FIRING {n.neuron_type.value} "
                      f"mem={n.membrane:.3f} fires={n.fire_count}")
            elif n.membrane > 0.01:
                print(f"  [{n.id}] active {n.neuron_type.value} "
                      f"mem={n.membrane:.3f} fires={n.fire_count}")

    def print_connections(self):
        """打印所有连接"""
        print(f"Connections ({sum(len(v) for v in self.out_edges.values())} edges):")
        for src in sorted(self.out_edges.keys()):
            for tgt in sorted(self.out_edges[src].keys()):
                c = self.out_edges[src][tgt]
                print(f"  {src} -> {tgt}  w={c.weight:.3f}  delay={c.delay}")

    def stats(self) -> dict:
        """统计信息"""
        edge_count = sum(len(v) for v in self.out_edges.values())
        type_counts = {}
        for n in self.neurons:
            t = n.neuron_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        total_fires = sum(n.fire_count for n in self.neurons)
        active_edges = sum(
            1 for src in self.out_edges
            for c in self.out_edges[src].values()
            if c.weight > 0.1
        )
        return {
            "num_neurons": self.num_neurons,
            "num_edges": edge_count,
            "active_edges": active_edges,
            "total_fires": total_fires,
            "time": self.time,
            "neuron_types": type_counts,
            "eta_plus": self.eta_plus,
            "eta_minus": self.eta_minus,
            "weight_decay": self.weight_decay,
            "max_weight": self.max_weight,
        }
