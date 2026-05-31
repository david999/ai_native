FROM docker.1ms.run/library/alpine:3.20

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

RUN adduser -D -u 10001 aicr && chown -R aicr:aicr /app
USER aicr

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3)" || exit 1

CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
