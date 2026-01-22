# Nebula 接口服务使用指南

本服务是一个基于 FastAPI 的 Nebula Graph 轻量接口，提供图空间、模式（标签/边类型）及点/边的增删改查，同时支持执行 nGQL 查询。

- 服务默认连接：`124.223.47.167:9669`，用户：`root`，密码：`nebula`
- 每次请求可通过请求头覆盖连接：
  - `X-Nebula-Host`
  - `X-Nebula-Port`
  - `X-Nebula-User`
  - `X-Nebula-Password`
- Swagger 文档：`http://<接口主机>:8001/docs`

## 启动与健康检查

在部署服务的主机上（包含 Docker Compose 文件）：

```bash
cd ~/services/interface
sudo docker compose build --no-cache
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs -f nebula-interface
```

健康检查与文档：

```bash
curl -sS http://<接口主机>:8001/health
curl -sS http://<接口主机>:8001/docs
```

Windows PowerShell（pwsh）用户可使用 `Invoke-RestMethod` 或 `curl.exe`。

## 连接与请求头覆盖

所有端点均可通过以下请求头覆盖连接信息：

```pwsh
$headers = @{ 
  "X-Nebula-Host" = "124.223.47.167"
  "X-Nebula-Port" = "9669"
  "X-Nebula-User" = "root"
  "X-Nebula-Password" = "nebula"
}
```

## 图空间（Spaces）

- 列表：`GET /spaces`
- 创建：`POST /spaces`
- 修改：`PATCH /spaces/{name}`
- 删除：`DELETE /spaces/{name}`

示例（列出空间）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/spaces" -Headers $headers
```

示例（创建空间）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/spaces" -Method Post -Headers $headers -ContentType "application/json" -Body '{
  "name": "my_space",
  "partition_num": 3,
  "replica_factor": 1,
  "vid_type": "FIXED_STRING(64)"
}'
```

## 一键部署（/deploy）

- 端点：`POST /deploy`
- 功能：创建空间并按顺序创建标签与边类型。
- 无请求体时将自动读取同级目录的 `deploy_defaults.json` 作为默认配置。

示例（使用默认配置，无请求体）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/deploy" -Method Post -Headers $headers
```

示例（自定义部署请求体）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/deploy" -Method Post -Headers $headers -ContentType "application/json" -Body '{
  "space": "my_space",
  "partition_num": 3,
  "replica_factor": 1,
  "vid_type": "FIXED_STRING(64)",
  "tags": [
    {"name": "Person", "properties": [
      {"name": "name", "type": "string"},
      {"name": "age", "type": "int"}
    ]}
  ],
  "edges": [
    {"name": "KNOWS", "properties": [
      {"name": "since", "type": "int"}
    ]}
  ]
}'
```

注意：若返回空间未准备就绪（超时），请在 Nebula 集群中确认 `SHOW HOSTS STORAGE;` 所有存储节点为 ONLINE，并稍后重试。

## 执行 nGQL（/query）

- 端点：`GET /query?q=<nGQL>&space=<space>`
- 说明：在指定空间下执行 nGQL；请对 `q` 做 URL 编码。

示例（显示存储主机）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/query?q=SHOW%20HOSTS%20STORAGE&space=my_space" -Headers $headers
```

## 标签（Tag 类型）

- 列表：`GET /tags?space=<space>`
- 创建：`POST /tags`，请求体：`{ space, tag, properties }`
- 增加列：`PATCH /tags`，请求体：`{ space, tag, properties }`
- 删除：`DELETE /tags`，请求体：`{ space, tag }`

示例（创建标签类型）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/tags" -Method Post -Headers $headers -ContentType "application/json" -Body '{
  "space": "my_space",
  "tag": "Person",
  "properties": [
    {"name": "name", "type": "string"},
    {"name": "age", "type": "int"}
  ]
}'
```

## 边类型（Edge 类型）

- 列表：`GET /edge-types?space=<space>`
- 创建：`POST /edge-types`，请求体：`{ space, edge, properties }`
- 增加列：`PATCH /edge-types`，请求体：`{ space, edge, properties }`
- 删除：`DELETE /edge-types`，请求体：`{ space, edge }`

## 点（Vertices）

- 创建：`POST /vertices`，请求体：`{ space, tag, vid, props }`
- 更新：`PATCH /vertices`，请求体：`{ space, tag, vid, props }`
- 删除：`DELETE /vertices`，请求体：`{ space, vid, with_edges }`
- 查询：`GET /vertices/{vid}?space=<space>&tag=<可选>`

示例（创建点）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/vertices" -Method Post -Headers $headers -ContentType "application/json" -Body '{
  "space": "my_space",
  "tag": "Person",
  "vid": "p_1",
  "props": { "name": "Alice", "age": 30 }
}'
```

## 边（Edges）

- 创建：`POST /edges`，请求体：`{ space, edge, src, dst, props }`
- 更新：`PATCH /edges`，请求体：`{ space, edge, src, dst, props }`
- 删除：`DELETE /edges`，请求体：`{ space, edge, src, dst }`
- 查询：`GET /edges?space=<space>&edge=<edge>&src=<src>&dst=<dst>`

示例（创建边）：

```pwsh
Invoke-RestMethod -Uri "http://<接口主机>:8001/edges" -Method Post -Headers $headers -ContentType "application/json" -Body '{
  "space": "my_space",
  "edge": "KNOWS",
  "src": "p_1",
  "dst": "p_2",
  "props": { "since": 2020 }
}'
```

## CSV 批量导入

- 点导入：`POST /import/csv/vertices?space=<space>&tag=<tag>`
  - CSV 首行必须包含 `vid` 列，其余列为属性名（需符合 Nebula 标识符规则：字母/数字/下划线，且以字母或下划线开头）。
- 边导入：`POST /import/csv/edges?space=<space>&edge=<edge>`
  - CSV 首行必须包含 `src,dst` 列，其余列为属性名。
- 自动类型转换：空值会被忽略；`true/false` 解析为布尔；纯整数解析为 int；其余尝试解析为 float，否则按字符串写入。

示例（点 CSV，UTF-8，包含表头）：

```csv
vid,name,confidence
root-1,Alice,90000
root-2,Bob,80000
```

示例（PowerShell 上传点 CSV）：

```pwsh
$file = Get-Item "./vertices.csv"
Invoke-RestMethod -Uri "http://<接口主机>:8001/import/csv/vertices?space=my_space&tag=Person" `
  -Method Post `
  -Form @{ file = $file }
```

示例（边 CSV）：

```csv
src,dst,since
root-1,root-2,2020
```

示例（PowerShell 上传边 CSV）：

```pwsh
$file = Get-Item "./edges.csv"
Invoke-RestMethod -Uri "http://<接口主机>:8001/import/csv/edges?space=my_space&edge=KNOWS" `
  -Method Post `
  -Form @{ file = $file }
```

## 默认部署配置（deploy_defaults.json）

- 位置：与 `main.py` 同级目录：`services/interface/deploy_defaults.json`
- 无请求体调用 `/deploy` 时将使用此 JSON。可直接编辑以切换默认空间、标签与边类型。

## 使用 curl.exe（可选）

```pwsh
curl.exe "http://<接口主机>:8001/spaces" `
  -H "X-Nebula-Host: 124.223.47.167" `
  -H "X-Nebula-Port: 9669" `
  -H "X-Nebula-User: root" `
  -H "X-Nebula-Password: nebula"
```

## 常见问题

- “Host not enough!”：存储主机不足或未在线。请先检查 `SHOW HOSTS STORAGE;`。
- “SpaceNotFound” 或空间未就绪：确认集群健康后重试；本服务会在 `/deploy` 中等待空间就绪（可能需要数十秒）。
- PowerShell 多行命令：使用反引号 `` ` `` 作为换行连接符；或将命令写在单行。
- `/query` 能执行任意 nGQL，使用时需谨慎（避免破坏性操作）。

## Swagger 与调试

- 打开 `http://<接口主机>:8001/docs`，点击对应端点的 “Try it out”，在 Headers 中填入四个 Nebula 请求头，提交测试。

---
如需扩展更多操作（例如 `LOOKUP`、分页查询、批量写入等），可在此服务基础上继续添加端点。欢迎反馈。