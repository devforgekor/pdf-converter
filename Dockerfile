FROM python:3.11-slim

# 시스템 의존성 설치 (PDF 처리용 poppler)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 설치 (캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사
COPY . .

# 디렉토리 생성
RUN mkdir -p uploads output instance

# 포트 노출
EXPOSE 8000

# 앱 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
