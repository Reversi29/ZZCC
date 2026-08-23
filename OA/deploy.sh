#!/bin/bash
set -euo pipefail

# =====================================================
# zzcc-oa deploy.sh — 一键部署脚本
# 用法: ./deploy.sh [pull|build|restart|logs|health|status|clean]
# =====================================================

COMPOSE_FILE="docker-compose.prod.yml"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── Colors ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()  { echo -e "  ${GREEN}✓${NC} $1"; }
fail(){ echo -e "  ${RED}✗${NC} $1"; }
info(){ echo -e "  ${CYAN}→${NC} $1"; }

# ── Health Check ────────────────────────────────────────
check_health() {
  local max_wait=${1:-30}
  local elapsed=0
  info "等待后端就绪（最多 ${max_wait}s）..."
  while [ $elapsed -lt $max_wait ]; do
    local status
    status=$(curl -sf http://localhost:8003/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])" 2>/dev/null || echo "down")
    if [ "$status" = "up" ]; then
      ok "后端健康检查通过（${elapsed}s）"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  fail "后端未就绪，超时 ${max_wait}s"
  return 1
}

check_front_health() {
  local max_wait=${1:-15}
  local elapsed=0
  info "等待 nginx 就绪（最多 ${max_wait}s）..."
  while [ $elapsed -lt $max_wait ]; do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
      ok "前端已就绪（${elapsed}s）"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  fail "前端未就绪，超时 ${max_wait}s"
  return 1
}

# ── Sync Frontend ───────────────────────────────────────
sync_frontend() {
  info "同步前端 index.html 到 nginx 容器..."
  
  if docker ps --format '{{.Names}}' | grep -q zzcc-oa-nginx; then
    # 用 docker exec pipe 绕过 docker cp 的 "device or resource busy"
    # 分两段写：先写临时文件，再原子替换
    python3 -c "
import base64, sys
with open('$PROJECT_DIR/frontend/index.html','rb') as f:
    sys.stdout.write(base64.b64encode(f.read()).decode())
" | docker exec -i zzcc-oa-nginx sh -c 'cat | base64 -d > /tmp/index_deploy.html'
    # 原子替换：先 mv 旧文件，再 rename 新文件
    docker exec zzcc-oa-nginx sh -c 'mv /usr/share/nginx/html/index.html /usr/share/nginx/html/index.html.bak 2>/dev/null || true; mv /tmp/index_deploy.html /usr/share/nginx/html/index.html; rm -f /usr/share/nginx/html/index.html.bak'
    # reload nginx
    docker exec zzcc-oa-nginx nginx -s reload 2>/dev/null
    ok "前端已同步并 reload"
  else
    fail "nginx 容器未运行"
  fi
}

# ── Commands ─────────────────────────────────────────────
cmd_pull() {
  info "拉取最新镜像..."
  docker compose -f "$COMPOSE_FILE" pull
}

cmd_build() {
  info "构建后端镜像..."
  docker compose -f "$COMPOSE_FILE" build --no-cache backend
}

cmd_up() {
  info "启动所有容器..."
  docker compose -f "$COMPOSE_FILE" up -d
  check_health 45
  sync_frontend
  check_front_health 10
  echo ""
  ok "部署完成"
  echo ""
  docker compose -f "$COMPOSE_FILE" ps
}

cmd_restart() {
  info "重启所有容器..."
  docker compose -f "$COMPOSE_FILE" restart
  check_health 30
  sync_frontend
  check_front_health 10
  ok "重启完成"
}

cmd_logs() {
  docker compose -f "$COMPOSE_FILE" logs --tail=100 "$@"
}

cmd_health() {
  echo "=== 后端 /health ==="
  curl -s http://localhost:8003/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8003/health
  echo ""
  echo "=== 前端 /api/status ==="
  curl -sf http://localhost:8080/api/status | python3 -m json.tool 2>/dev/null || echo "前端未就绪"
  echo ""
  echo "=== 容器状态 ==="
  docker compose -f "$COMPOSE_FILE" ps
}

cmd_status() {
  docker compose -f "$COMPOSE_FILE" ps
}

cmd_clean() {
  info "停止并清理容器..."
  docker compose -f "$COMPOSE_FILE" down
  info "清理未使用的镜像..."
  docker image prune -f
  ok "清理完成"
}

# ── Main ─────────────────────────────────────────────────
ACTION="${1:-up}"
case "$ACTION" in
  pull)    cmd_pull ;;
  build)   cmd_build ;;
  up|start) cmd_up ;;
  restart) cmd_restart ;;
  logs)    cmd_logs "${@:2}" ;;
  health)  cmd_health ;;
  status)  cmd_status ;;
  clean|down) cmd_clean ;;
  *)
    echo "用法: $0 [up|restart|pull|build|logs|health|status|clean]"
    exit 1
    ;;
esac