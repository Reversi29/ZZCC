FROM python:3.11-slim

WORKDIR /app

# 安装依赖（Docker Hub 在国内通常可达）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
