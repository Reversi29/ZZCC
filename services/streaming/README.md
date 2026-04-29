# 短视频推流服务

基于 SRS (Simple Realtime Server) 的短视频推流服务。

## 服务架构

```
┌─────────────────────────────────────────────────────────┐
│                    streaming-stack                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌──────────────┐      ┌──────────────┐                │
│   │              │      │              │                │
│   │  SRS Server  │◄────►│ SRS Console  │                │
│   │  (推流核心)   │      │  (管理界面)   │                │
│   │              │      │              │                │
│   └──────┬───────┘      └──────────────┘                │
│          │                                               │
│          ▼                                               │
│   ┌──────────────┐                                      │
│   │              │                                       │
│   │   FFmpeg     │  (可选，按需启动)                      │
│   │  (转码服务)   │                                       │
│   │              │                                       │
│   └──────────────┘                                      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## 端口说明

| 端口 | 协议 | 用途 |
|------|------|------|
| 1935 | RTMP | 推流端口 |
| 8080 | HTTP | API / HLS 拉流 |
| 443 | HTTPS | 安全连接 |
| 10080 | SRT | 低延迟传输 |
| 1985 | WebRTC | 超低延迟播放 |
| 8081 | HTTP | SRS 控制台 |

## 快速开始

### 1. 启动服务

```bash
cd /Users/mac/ZZCC/services/streaming
docker-compose up -d
```

### 2. 查看日志

```bash
docker-compose logs -f srs
```

### 3. 访问控制台

打开浏览器访问: http://localhost:8081

## 推流方式

### RTMP 推流（最常用）

**推流地址**: `rtmp://localhost:1935/live/{stream_name}`

**使用 OBS 推流**:
1. 设置 → 推流
2. 服务器: `rtmp://localhost:1935/live/`
3. 串流密钥: `test` （自定义）

**使用 FFmpeg 推流**:
```bash
ffmpeg -re -i input.mp4 \
  -c:v libx264 -c:a aac \
  -f flv rtmp://localhost:1935/live/test
```

### SRT 推流（低延迟）

```bash
ffmpeg -re -i input.mp4 \
  -c:v libx264 -c:a aac \
  -f mpegts "srt://localhost:10080?mode=push&streamid=live/test"
```

## 拉流播放

### HLS 播放

```
http://localhost:8080/live/{stream_name}.m3u8
```

### HTTP-FLV 播放

```
http://localhost:8080/live/{stream_name}.flv
```

### WebRTC 播放（超低延迟）

```
webrtc://localhost:1985/live/{stream_name}
```

## API 接口

### 获取版本信息

```bash
curl http://localhost:8080/api/v1/versions
```

### 获取流列表

```bash
curl http://localhost:8080/api/v1/streams
```

### 获取客户端列表

```bash
curl http://localhost:8080/api/v1/clients
```

## 录制文件

录制文件保存在 `data/srs/recordings/` 目录：

```
data/srs/recordings/
└── {app}/
    └── {stream}/
        └── {year}/
            └── {month}/
                └── {day}/
                    └── {hour}{minute}{second}.mp4
```

## 常用命令

```bash
# 启动所有服务
docker-compose up -d

# 启动 SRS + 控制台
docker-compose up -d srs srs-console

# 启动转码服务（按需）
docker-compose --profile transcode up -d ffmpeg

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f srs

# 停止服务
docker-compose down

# 重启服务
docker-compose restart srs
```

## 生产环境部署

### 1. 配置公网 IP

编辑 `conf/srs.conf`，取消注释：

```nginx
webrtc {
    candidate {你的公网IP};
}
```

### 2. 添加鉴权

取消 `conf/srs.conf` 中的鉴权配置注释，配置后端 API 地址。

### 3. 使用 HTTPS

建议配置 Nginx 反向代理，启用 HTTPS。

### 4. 集群部署

对于高并发场景，使用 Edge 边缘架构：

```
Origin (源站) → Edge1, Edge2, Edge3 (边缘节点) → 用户
```

## 目录结构

```
streaming/
├── docker-compose.yml   # Docker Compose 配置
├── .env                  # 环境变量
├── conf/
│   └── srs.conf          # SRS 配置文件
├── data/
│   └── srs/
│       └── recordings/   # 录制文件存储
├── logs/
│   └── srs/              # 日志文件
└── scripts/              # 转码脚本
```

## 相关文档

- [SRS 官方文档](https://ossrs.io/l/zh-cn/docs/v5/doc/config)
- [SRS GitHub](https://github.com/ossrs/srs)
- [WebRTC 低延迟](https://ossrs.io/l/zh-cn/docs/v5/doc/webrtc)
