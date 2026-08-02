#!/usr/bin/env bash
# ============================================
# ZZCC OA — 一键初始化脚本
# ============================================
set -euo pipefail

cd "$(dirname "$0")"

echo "========================================"
echo " ZZCC OA 系统初始化"
echo "========================================"

# 1. 启动 Docker Desktop（macOS）
if ! docker ps &>/dev/null; then
    echo "[1/4] 启动 Docker Desktop..."
    open -a Docker
    echo "     请等待 Docker 就绪后重新运行此脚本"
    echo "     或用: docker compose up -d"
    exit 1
fi
echo "[1/4] ✅ Docker 就绪"

# 2. 启动所有服务
echo "[2/4] 拉取并启动服务..."
docker compose pull --quiet
docker compose up -d
echo "      等待服务就绪..."
sleep 15
echo "[2/4] ✅ 服务已启动"

# 3. 创建 ERPNext 站点
echo "[3/4] 创建 ERPNext 站点..."
source .env 2>/dev/null || true
SITE_NAME="${SITE_NAME:-site1.local}"
ADMIN_PASS="${ADMIN_PASSWORD:-admin}"

docker compose exec -T backend \
    bench new-site "$SITE_NAME" \
    --mariadb-root-password "${DB_PASSWORD:-admin}" \
    --admin-password "$ADMIN_PASS" \
    --force
echo "[3/4] ✅ 站点创建完成: $SITE_NAME"

# 4. 安装 ERPNext + 核心模块
echo "[4/4] 安装应用模块..."
docker compose exec -T backend \
    bench --site "$SITE_NAME" install-app erpnext

# 安装自定义 AI 应用
if [ -d "apps/oa_ai" ]; then
    docker compose exec -T backend \
        bench --site "$SITE_NAME" install-app oa_ai
fi

# 启用系统模块（按需）
docker compose exec -T backend \
    bench --site "$SITE_NAME" enable-scheduler

echo "[4/4] ✅ 模块安装完成"

# 5. 输出访问信息
echo ""
echo "========================================"
echo " ✅ ZZCC OA 部署完成！"
echo "========================================"
echo " 访问地址: http://localhost:8080"
echo " 管理员:   Administrator"
echo " 密码:     ${ADMIN_PASS}"
echo "========================================"
echo ""
echo "下一步："
echo "  - 打开浏览器访问 http://localhost:8080"
echo "  - 在 ERPNext 中配置业务模块"
echo "  - 在 ai/ 目录下配置 AI Agent 模块"
echo "========================================"
