FROM python:3.11-slim

WORKDIR /app

# Cài đặt dependencies hệ thống
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements và cài đặt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Chạy bot
CMD ["python", "main.py"]
