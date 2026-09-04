# ZZCC 插件广场架构

## 1. 定位

插件广场是 ZZCC services 插件系统的发布与分发层，类似 VSCode Marketplace / DashScope 插件市场：第三方或内部开发者可以发布“插件 zip 包”，用户在插件广场浏览、搜索、下载并从市场安装到当前插件系统。

当前实现采用**文件系统后端**，优先打通端到端闭环；后续可替换为对象存储或独立 marketplace DB，而 API 语义保持不变。

## 2. 核心 API

管理路径：`/api/v1/plugin-market`

| 端点 | 方法 | 说明 |
|------|------|------|
| `/packages` | GET | 列出/搜索插件包，支持 `q/category/tag` |
| `/categories` | GET | 分类聚合统计 |
| `/packages/{pkg_id}` | GET | 获取插件包详情 |
| `/publish` | POST | 上传并发布 zip 插件包 |
| `/packages/{pkg_id}/download` | POST | 记录下载并返回下载路径 |
| `/packages/{pkg_id}/install` | POST | 从插件广场安装到当前插件系统 |
| `/packages/{pkg_id}` | DELETE | 删除已发布插件包 |

## 3. 包结构

插件广场包仍复用插件系统 manifest：

```text
pkg_xxx.zip
└── plugin.json
└── routes.py
└── frontend/index.html
└── hook.py        # optional
```

发布时会执行 `validate_manifest()` 校验：

- `id/name/version` 必填
- `permissions` 只能包含白名单权限
- `events` / `frontend` 结构必须为 dict
- zip 中必须包含 `plugin.json`

## 4. 市场元数据

每个插件包会生成一个目录：

```text
/app/plugin_market/
└── pkg_xxx/
    ├── pkg_xxx.zip
    └── market.json
```

`market.json` 字段：

- `package_id`
- `plugin_id`
- `name/version/author/publisher/description`
- `category/tags/readme`
- `permissions/events`
- `downloads/installs`
- `published_at/updated_at`
- `size_bytes`

环境变量：

```bash
ZZCC_PLUGIN_MARKET_DIR=/app/plugin_market
```

## 5. 安装流程

1. `POST /plugin-market/packages/{pkg_id}/install`
2. 从市场目录读取 zip
3. 校验 zip 内 `plugin.json`
4. 解压到当前插件系统安装目录：`ZZCC_PLUGINS_DIR/{plugin_id}`
5. 调用现有 `load_plugin()` 注册路由/事件/Brain 扩展
6. 持久化到 `plugin_registry`
7. 递增市场 `installs`

若插件已安装，返回 `409`，需先卸载再安装。

## 6. 权限与安全

当前阶段：任意已登录用户可发布/安装，符合内部系统最小闭环目标。

后续加固方向：

- 发布者身份绑定与版本签名
- 插件权限审批/沙箱策略
- 上传病毒扫描与 import 白名单强制
- 市场版本替换与回滚
- 对象存储替代本地文件目录
