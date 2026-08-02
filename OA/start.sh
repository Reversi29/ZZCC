#!/bin/bash
# ZZCC OA — 一键启动脚本
# 用法：./start.sh  [dev|prod]
#   dev:   启动 FastAPI 后端（host 模式，直接连 localhost:8000）
#   prod:  docker compose 模式（需要 Docker 网络畅通）

MODE="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

API_KEY="${API_KEY:-zzcc_oadev_key_2024}"

echo "=== ZZCC OA 启动 ==="
echo "模式: $MODE | API_KEY: $API_KEY"
echo

if [ "$MODE" = "dev" ]; then
    # ── 启动 Redis（数据缓存，可选）─────────────────────────
    if ! docker ps --format '{{.Names}}' | grep -q "^zzcc-oa-redis$"; then
        echo "[1/3] 启动 Redis..."
        docker run -d --name zzcc-oa-redis \
            --restart unless-stopped \
            -v "$SCRIPT_DIR/data/redis:/data" \
            redis:alpine redis-server --appendonly yes
        echo "  Redis 启动完成"
    else
        echo "[1/3] Redis 已运行"
    fi

    # ── 启动 MariaDB（可选，SQLite 已默认启用）───────────────
    if ! docker ps --format '{{.Names}}' | grep -q "^zzcc-oa-mariadb$"; then
        echo "[2/3] 启动 MariaDB..."
        docker run -d --name zzcc-oa-mariadb \
            --restart unless-stopped \
            -e MARIADB_ROOT_PASSWORD=zzcc_oa_2024 \
            -p 3307:3306 \
            -v "$SCRIPT_DIR/data/mariadb:/var/lib/mysql" \
            mariadb:10.8 \
            --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
        echo "  MariaDB 启动完成（root 密码: zzcc_oa_2024）"
    else
        echo "[2/3] MariaDB 已运行"
    fi

    # ── 启动 FastAPI 后端 ─────────────────────────────────────
    echo "[3/3] 启动 FastAPI 后端..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null; true
    sleep 1
    cd "$SCRIPT_DIR/backend"
    nohup env API_KEY="$API_KEY" \
        python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 \
        >> "$SCRIPT_DIR/logs/backend.log" 2>&1 &
    BACKEND_PID=$!
    echo "  后端 PID=$BACKEND_PID"
    sleep 3

    # ── 健康检查 ──────────────────────────────────────────────
    if curl -sf "http://localhost:8000/api/status" > /dev/null 2>&1; then
        echo "  ✓ 后端健康检查通过"
    else
        echo "  ✗ 后端启动失败，查看日志："
        tail -20 "$SCRIPT_DIR/logs/backend.log"
    fi

    echo
    echo "=== 启动完成 ==="
    echo "  前端（nginx SPA）: http://localhost:8080"
    echo "  后端 API:          http://localhost:8000"
    echo "  API 文档:          http://localhost:8000/docs"
    echo "  MariaDB:           localhost:3307（root / zzcc_oa_2024）"
    echo "  Redis:             localhost:6379"
    echo "  后端日志:          $SCRIPT_DIR/logs/backend.log"

elif [ "$MODE" = "prod" ]; then
    echo "[1/1] Docker Compose 启动..."
    cd "$SCRIPT_DIR"
    docker compose up -d --build
    echo "  Docker Compose 完成（前台日志：docker compose logs -f）"
    echo "  访问：http://localhost:8080"

else
    echo "用法：$0 [dev|prod]"
    exit 1
fi
