FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用层缓存）
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码与前端静态资源（自包含，不挂载也能跑）
COPY backend/ /app/
COPY frontend/index.html /frontend/index.html

RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8003

ENTRYPOINT ["/app/docker-entrypoint.sh"]
