#!/bin/bash
# OA 生产栈开机自启。
#
# 由 launchd 在用户登录时调用（RunAtLoad）。
# 关键约束：Docker Desktop 虽在登录项里，但其引擎就绪晚于 launchd 触发，
# 直接 docker compose up 会因 daemon 未就绪而失败。故先轮询等待，
# 最多 240 秒。
#
# 幂等：容器已在运行且配置一致时，compose up -d 为 no-op。

set -u

COMPOSE_FILE="/Users/mac/ZZCC/OA/docker-compose.prod.yml"
COMPOSE_DIR="/Users/mac/ZZCC/OA"
LOG_DIR="/Users/mac/ZZCC/OA/logs"
MAX_WAIT=240
INTERVAL=5

# launchd 的 PATH 极简（/usr/bin:/bin:/usr/sbin:/sbin），不含 /usr/local/bin，
# 直接用 `docker` 会 command not found——等待循环会空转到超时。
# 故固定解析为绝对路径。
DOCKER_BIN="/usr/local/bin/docker"
if [ ! -x "$DOCKER_BIN" ]; then
  DOCKER_BIN="$(command -v docker 2>/dev/null || true)"
fi

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*" >> "$LOG_DIR/autostart.log"; }

log "autostart invoked (pid $$, docker=$DOCKER_BIN, PATH=$PATH)"

if [ -z "$DOCKER_BIN" ] || [ ! -x "$DOCKER_BIN" ]; then
  log "ERROR: docker binary not found"
  exit 1
fi

# 等待 Docker daemon 就绪
waited=0
until "$DOCKER_BIN" info >/dev/null 2>&1; do
  if [ "$waited" -ge "$MAX_WAIT" ]; then
    log "ERROR: docker daemon not ready after ${MAX_WAIT}s, abort"
    exit 1
  fi
  log "docker daemon not ready, waiting (${waited}s/${MAX_WAIT}s)"
  sleep "$INTERVAL"
  waited=$((waited + INTERVAL))
done
log "docker daemon ready after ${waited}s"

cd "$COMPOSE_DIR" || { log "ERROR: cd failed"; exit 1; }

if "$DOCKER_BIN" compose -f "$COMPOSE_FILE" up -d >> "$LOG_DIR/autostart.log" 2>&1; then
  log "compose up -d OK"
else
  log "ERROR: compose up -d failed, see above"
  exit 1
fi

# 状态回写，便于事后核对
"$DOCKER_BIN" ps --filter "name=zzcc-oa-" --format '{{.Names}} {{.Status}}' >> "$LOG_DIR/autostart.log" 2>&1
log "done"