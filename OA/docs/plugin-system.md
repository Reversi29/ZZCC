# ZZCC OA 插件系统架构设计

## 1. 设计目标

让第三方（或内部开发者）在不修改主仓库代码的前提下，扩展 OA 系统的功能：
- **新增 API 端点**（挂载到 `/api/plugin/{plugin_id}/...`）
- **新增前端模块**（出现在侧边栏模块网格中）
- **订阅事件钩子**（如审批通过后触发外部通知）
- **复用已有基础设施**（认证、数据库、审计、前端骨架）

类似 VSCode 扩展模型：清单声明 → 沙箱加载 → 生命周期管理。

---

## 2. 核心概念

### 2.1 Plugin Manifest（plugin.json）

每个插件根目录必须包含 `plugin.json`：

```json
{
  "id": "inventory-tracker",
  "name": "库存追踪",
  "version": "1.0.0",
  "author": "zzcc",
  "description": "仓库库存实时追踪与预警",
  "permissions": ["database", "auth", "api:call", "event:publish"],
  "events": {
    "subscribe": ["approval.approved", "purchase_order.created"],
    "publish": ["inventory.low_stock"]
  },
  "routes": {
    "prefix": "/api/plugin/inventory-tracker",
    "router": "routes.py:router"
  },
  "frontend": {
    "module": {
      "id": "inventory",
      "name": "库存追踪",
      "emoji": "📦",
      "entry": "frontend/index.html"
    }
  },
  "config_schema": {
    "low_stock_threshold": {"type": "integer", "default": 10},
    "warehouse_count": {"type": "integer", "default": 1}
  }
}
```

### 2.2 权限模型

| 权限 | 说明 |
|------|------|
| `database` | 可读写 OA MariaDB（受限表或独立 schema） |
| `auth` | 可调用 `require_auth` / `require_admin` |
| `api:call` | 可内部调用已注册的 OA router 端点 |
| `event:publish` | 可发布事件到事件总线 |
| `event:subscribe` | 可订阅事件 |
| `http:external` | 可发起外部 HTTP 请求 |
| `file:write` | 可写文件（插件隔离目录） |

权限在 manifest 中声明，加载时校验，运行时强制。

### 2.3 事件总线

进程内 pub/sub，基于 asyncio：

```python
# 插件声明订阅
@plugin.on("approval.approved")
async def handle_approval(event: PluginEvent):
    # event.payload 含审批单据信息
    await notify_warehouse(event.payload)
```

**内置事件列表**（由核心 router 在关键操作后发布）：

| 事件名 | 触发点 | Payload |
|--------|--------|---------|
| `approval.submitted` | 提交审批单 | `{doctype, doc_id, applicant}` |
| `approval.approved` | 审批通过 | `{doctype, doc_id, approver}` |
| `approval.rejected` | 审批驳回 | `{doctype, doc_id, approver, reason}` |
| `purchase_order.created` | 创建采购单 | `{po_id, supplier, amount}` |
| `user.registered` | 新用户注册 | `{user_id, username}` |
| `user.login` | 用户登录 | `{user_id, username}` |
| `module.toggled` | 模块开关切换 | `{module_id, enabled}` |
| `flow.executed` | 流程实例执行 | `{flow_id, instance_id, status}` |

插件也可发布自定义事件，但仅限 manifest 中 `events.publish` 声明的事件。

---

## 3. 后端架构

### 3.1 Plugin Loader（加载器）

```
backend/plugins/
├── loader.py          # 插件加载器
├── registry.py        # 插件注册表（已加载插件元数据）
├── event_bus.py       # 事件总线
├── sandbox.py         # 沙箱执行环境
├── permissions.py    # 权限校验
└── plugin_api.py      # 插件可调用的内部 API
```

### 3.2 加载流程

```
1. 扫描 plugins/ 目录，找 plugin.json
2. 校验 manifest（schema、权限、依赖）
3. 注册到 PluginRegistry（id → metadata + 状态）
4. 加载路由模块 → app.include_router(plugin_router, prefix="/api/plugin/{id}")
5. 注册事件订阅 → event_bus.subscribe(event, handler)
6. 注册前端模块 → 写入 plugin_modules 表，前端启动时拉取
7. 执行插件 on_load() 钩子（如有）
```

### 3.3 路由隔离

插件路由统一挂载到 `/api/plugin/{plugin_id}/`，前缀自动注入：

```python
# loader.py
def load_plugin(app: FastAPI, plugin_dir: Path):
    manifest = json.loads((plugin_dir / "plugin.json").read_text())
    routes_mod = importlib.import_module(f"{manifest['id']}.{manifest['routes']['router'].split(':')[0]}")
    router = getattr(routes_mod, manifest['routes']['router'].split(':')[1])
    app.include_router(router, prefix=f"/api/plugin/{manifest['id']}")
```

插件路由自动继承 `require_auth` 中间件（强制认证），权限级别由 manifest 声明。

### 3.4 数据库访问

两种模式：

**模式 A — 共享表（只读）**：插件可读 OA 已有表，通过 `plugin_api.query_table("ExpenseClaim", filters=...)` 接口。只读，不可写。

**模式 B — 插件专属表**：插件自带 `models.py`，使用独立 SQLAlchemy 模型。表名前缀 `plugin_{id}_`，自动建表。DDL 在加载时执行 `CREATE TABLE IF NOT EXISTS`。

```python
# 插件 models.py
from plugins.sdk import PluginBase, Column, Integer, String, DateTime

class InventoryItem(PluginBase):
    __tablename__ = "plugin_inventory_items"
    id = Column(Integer, primary_key=True)
    sku = Column(String(64))
    quantity = Column(Integer, default=0)
    last_updated = Column(DateTime)
```

### 3.5 插件 SDK（plugins/sdk.py）

提供给插件开发者的最小 SDK：

```python
from plugins.sdk import Plugin, on_event, plugin_api

class MyPlugin(Plugin):
    plugin_id = "inventory-tracker"

    async def on_load(self):
        # 初始化逻辑
        pass

    async def on_unload(self):
        # 清理逻辑
        pass

    @on_event("purchase_order.created")
    async def check_stock(self, event):
        po = event.payload
        for item in po["items"]:
            stock = await plugin_api.query_table("Item", filters={"sku": item["sku"]})
            if stock and stock[0]["quantity"] < item["qty"]:
                await self.publish_event("inventory.low_stock", {"sku": item["sku"]})
```

---

## 4. 前端架构

### 4.1 模块注入

前端启动时调用 `GET /api/plugins/modules`，返回所有已启用插件的前端模块信息：

```json
{
  "modules": [
    {
      "plugin_id": "inventory-tracker",
      "module_id": "inventory",
      "name": "库存追踪",
      "emoji": "📦",
      "entry_url": "/api/plugin/inventory-tracker/frontend/index.html"
    }
  ]
}
```

前端 MODULES 数组动态合并这些模块到模块网格。

### 4.2 渲染方式

插件前端以 **iframe 沙箱** 方式嵌入 OA 主界面：

```javascript
function renderPluginModule(pluginModule) {
  const iframe = document.createElement('iframe');
  iframe.src = pluginModule.entry_url;
  iframe.sandbox = 'allow-same-origin allow-scripts allow-forms';
  iframe.style.cssText = 'width:100%;height:100%;border:none;';
  return iframe;
}
```

**为什么 iframe 而非直接注入**：
- 插件代码不可信，需沙箱隔离
- 插件可使用任意前端框架，不污染主 app.js
- 通过 postMessage 通信，权限可控

### 4.3 通信协议

iframe ↔ 主界面通过 `postMessage`：

```javascript
// 插件 iframe 内
window.parent.postMessage({
  type: 'plugin:api:call',
  plugin_id: 'inventory-tracker',
  endpoint: '/api/resource/Item',
  method: 'GET'
}, '*');

// 主界面监听
window.addEventListener('message', async (e) => {
  if (e.data.type === 'plugin:api:call') {
    const resp = await fetch(e.data.endpoint, {method: e.data.method, headers: getAuthHeaders()});
    e.source.postMessage({type: 'plugin:api:response', data: await resp.json()}, '*');
  }
});
```

---

## 5. 生命周期管理

```
         ┌─────────┐
         │ install │  ← 上传 plugin.zip 到 /api/plugins/install
         └────┬────┘
              ▼
         ┌─────────┐
         │  load   │  ← 加载到内存，注册路由/事件/前端
         └────┬────┘
              ▼
   ┌─────────────────┐
   │ enabled (running)│  ← 正常运行
   └────┬───────┬────┘
        │       │
   ┌────▼──┐ ┌─▼─────┐
   │ disable│ │ reload│  ← 禁用/热重载
   └────┬──┘ └─┬─────┘
        │       │
   ┌────▼───────▼──┐
   │   unload      │  ← 从内存卸载
   └────┬──────────┘
        ▼
   ┌─────────┐
   │ uninstall│  ← 删除文件
   └─────────┘
```

管理 API（`/api/plugins/`）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/plugins/` | GET | 列出所有插件 |
| `/api/plugins/{id}` | GET | 获取插件详情 |
| `/api/plugins/install` | POST | 上传安装插件（zip） |
| `/api/plugins/{id}/enable` | POST | 启用插件 |
| `/api/plugins/{id}/disable` | POST | 禁用插件 |
| `/api/plugins/{id}/reload` | POST | 热重载 |
| `/api/plugins/{id}/uninstall` | DELETE | 卸载删除 |
| `/api/plugins/{id}/config` | GET/PUT | 获取/修改插件配置 |
| `/api/plugins/modules` | GET | 获取前端模块列表（前端调用） |

---

## 6. 沙箱执行

### 6.1 Python 插件沙箱

插件代码在加载时被限制可 import 的模块白名单：

```python
ALLOWED_IMPORTS = {
    'fastapi', 'pydantic', 'sqlalchemy', 'datetime',
    'typing', 'json', 'asyncio', 'logging',
    'plugins.sdk',  # 插件 SDK
}
```

通过 `importlib` + 自定义 `MetaPathFinder` 拦截非白名单 import。

### 6.2 资源限制

- 每个插件最多注册 20 个路由
- 事件处理超时 30s（超时自动 kill）
- 数据库查询超时 10s
- 独立 logger，日志前缀 `[plugin:{id}]`

---

## 7. 数据模型

```sql
-- 插件注册表
CREATE TABLE IF NOT EXISTS plugin_registry (
    id VARCHAR(64) PRIMARY KEY,          -- plugin_id
    name VARCHAR(128) NOT NULL,
    version VARCHAR(32) NOT NULL,
    author VARCHAR(64),
    description TEXT,
    manifest JSON NOT NULL,              -- 完整 plugin.json
    status ENUM('installed','enabled','disabled','error') DEFAULT 'installed',
    config JSON,                         -- 用户配置
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 插件事件日志
CREATE TABLE IF NOT EXISTS plugin_event_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    plugin_id VARCHAR(64) NOT NULL,
    event_name VARCHAR(128) NOT NULL,
    payload JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_plugin (plugin_id),
    INDEX idx_event (event_name)
);
```

---

## 8. 目录结构

```
OA/backend/
├── plugins/                    # 插件系统核心
│   ├── __init__.py
│   ├── loader.py
│   ├── registry.py
│   ├── event_bus.py
│   ├── sandbox.py
│   ├── permissions.py
│   ├── plugin_api.py
│   └── sdk.py                  # 插件开发者 SDK
├── plugins_data/               # 已安装插件文件
│   ├── inventory-tracker/
│   │   ├── plugin.json
│   │   ├── routes.py
│   │   ├── models.py
│   │   └── frontend/
│   │       └── index.html
│   └── ...
└── routers/
    └── plugins.py               # 插件管理 API（/api/plugins/*）
```

---

## 9. 示例插件

### plugin.json
```json
{
  "id": "low-stock-alert",
  "name": "库存预警",
  "version": "1.0.0",
  "author": "zzcc",
  "description": "采购审批通过后检查库存，低于阈值时推送通知",
  "permissions": ["database", "event:subscribe", "event:publish"],
  "events": {
    "subscribe": ["approval.approved"],
    "publish": ["inventory.low_stock"]
  },
  "routes": {"prefix": "/api/plugin/low-stock-alert", "router": "routes.py:router"},
  "frontend": {
    "module": {
      "id": "low-stock",
      "name": "库存预警",
      "emoji": "⚠️",
      "entry": "frontend/index.html"
    }
  },
  "config_schema": {
    "threshold": {"type": "integer", "default": 10}
  }
}
```

### routes.py
```python
from fastapi import APIRouter, Depends
from plugins.sdk import plugin_api, get_plugin_config

router = APIRouter()

@router.get("/status")
async def stock_status(user: dict = Depends(plugin_api.require_auth)):
    items = await plugin_api.query_table("Item", filters={})
    low = [i for i in items if i.get("quantity", 0) < get_plugin_config("threshold", 10)]
    return {"ok": True, "data": {"total": len(items), "low_stock": low}}
```

---

## 10. 实现路线图

| 阶段 | 内容 | 预估 |
|------|------|------|
| P1 | Plugin Loader + Registry + manifest 校验 | 2h |
| P2 | 事件总线 + 内置事件埋点（approval/user/flow） | 2h |
| P3 | 插件管理 API（/api/plugins/* CRUD） | 1h |
| P4 | 沙箱（import 白名单 + 资源限制） | 2h |
| P5 | 前端动态模块注入 + iframe 沙箱 | 2h |
| P6 | 示例插件（low-stock-alert）验证全链路 | 1h |
| 总计 | | ~10h |
