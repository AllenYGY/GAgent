#!/bin/bash
# 后端启动脚本 - 从环境变量读取配置

# 加载 .env 文件
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 读取环境变量，提供默认值
BACKEND_HOST=${BACKEND_HOST:-0.0.0.0}
BACKEND_PORT=${BACKEND_PORT:-9000}

echo "Starting backend server..."
echo "Host: $BACKEND_HOST"
echo "Port: $BACKEND_PORT"
echo "CORS Origins: $CORS_ORIGINS"

# 启动 FastAPI 应用
python -m uvicorn app.main:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    --reload
