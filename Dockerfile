FROM python:3.11-slim

# 시스템 의존성 설치 (PDF 처리용 poppler + qpdf)
RUN apt-get update && apt-get install -y \
    poppler-utils \
    qpdf \
    && rm -rf /var/lib/apt/lists/*

# uv 설치 (docs.astral.sh/uv 가이드: python 기본 이미지 + uv 바이너리 복사)
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/

WORKDIR /app

# 컨테이너의 python:3.11 을 사용하고 (호스트 관리 파이썬 다운로드 금지)
ENV UV_SYSTEM_PYTHON=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 의존성 레이어: pyproject.toml + uv.lock 만 먼저 복사해 빌드 캐시 극대화
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# 소스코드 복사
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# 디렉토리 생성
RUN mkdir -p uploads output instance

# 포트 노출
EXPOSE 8000

# 런타임에는 uv 를 거치지 않는다 (read_only + non-root 컨테이너).
# compose 의 command: ["uvicorn", ...] 가 venv 바이너리를 찾도록 PATH 주입
# (uv 공식 Docker 가이드: ENV PATH="/app/.venv/bin:$PATH")
ENV PATH="/app/.venv/bin:$PATH"

# 앱 실행 (기본값 — kuhwa compose 가 --root-path 와 함께 오버라이드)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
