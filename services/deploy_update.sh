#!/bin/bash
# ZZCC 后端更新部署脚本
# 用法: ./deploy_update.sh

set -e

SERVER="124.223.47.167"
SERVER_USER="ubuntu"
SERVER_PATH="/home/ubuntu/services/interface"
LOCAL_PATH="/Users/mac/ZZCC/services/interface"

echo "=== ZZCC 后端部署 ==="
echo "本地: $LOCAL_PATH"
echo "远程: $SERVER_USER@$SERVER:$SERVER_PATH"
echo ""

# 检查 SSH 连接
echo "检查 SSH 连接..."
ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER_USER@$SERVER" "echo OK" 2>/dev/null || {
    echo "❌ SSH 免密登录未配置"
    echo ""
    echo "请手动执行以下命令部署："
    echo ""
    echo "  rsync -avz --delete $LOCAL_PATH/ $SERVER_USER@$SERVER:$SERVER_PATH/"
    echo "  ssh $SERVER_USER@$SERVER 'cd $SERVER_PATH && docker compose build --no-cache && docker compose up -d'"
    echo ""
    echo "或者先配置 SSH 免密登录："
    echo "  ssh-copy-id $SERVER_USER@$SERVER"
    exit 1
}

echo "✅ SSH 连接正常"
echo ""

# 同步代码
echo "同步代码..."
rsync -avz --delete "$LOCAL_PATH/" "$SERVER_USER@$SERVER:$SERVER_PATH/"

# 重建并重启容器
echo ""
echo "重建并重启容器..."
ssh "$SERVER_USER@$SERVER" "cd $SERVER_PATH && docker compose build --no-cache && docker compose up -d"

echo ""
echo "✅ 部署完成"
echo ""
echo "验证:"
ssh "$SERVER_USER@$SERVER" "curl -s http://localhost:8001/health"
