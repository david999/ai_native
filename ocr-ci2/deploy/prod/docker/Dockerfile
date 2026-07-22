# OCR Gateway — 生产 Docker 镜像（build context = ocr-ci2 仓库根）
#
# 构建：deploy/prod/docker/build_image.ps1
# 运行：deploy/prod/docker/run.ps1
#
# 逻辑清单：
# - 始终：镜像内 npm install -g OCR CLI（全新层，无 skip-if-present）
# - 复制：bake 后的 .build/config.json、gateway/、scripts/、发帖脚本到 /usr/local/lib/ocr-ci
# - 构建：viewer-spa（Vue 3）产物到 /app/viewer-spa/dist（方案 C，由 OCR_DASHBOARD_SPA 开关）
# - 不做：运行时挂载宿主机 ~/.opencodereview（配置在构建时 bake）

FROM docker.1ms.run/library/node:20

ARG OCR_NPM_VERSION=@alibaba-group/open-code-review

# 官方 node 镜像无 Python/pip；Gateway 需 uvicorn，ocr review 需 git
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g "${OCR_NPM_VERSION}" \
    && ocr version || true

COPY .build/config.json /root/.opencodereview/config.json

COPY scripts/post_ocr_to_gitlab.py /usr/local/lib/ocr-ci/post_ocr_to_gitlab.py
COPY scripts/gitlab_mr.py /usr/local/lib/ocr-ci/gitlab_mr.py
COPY scripts/ocr_ci_config.py /usr/local/lib/ocr-ci/ocr_ci_config.py
RUN chmod +x /usr/local/lib/ocr-ci/post_ocr_to_gitlab.py

COPY gateway/requirements.txt /tmp/gateway-requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/gateway-requirements.txt

# 方案 C：先装 SPA 依赖再拷源码，利于 Docker 层缓存
COPY viewer-spa/package.json viewer-spa/package-lock.json* /app/viewer-spa/
WORKDIR /app/viewer-spa
RUN npm install --no-audit --no-fund
COPY viewer-spa /app/viewer-spa
RUN npm run build

WORKDIR /app
COPY gateway /app/gateway
COPY scripts /app/scripts
COPY viewer /app/viewer
ENV PYTHONPATH=/app
ENV OCR_POST_SCRIPT=/usr/local/lib/ocr-ci/post_ocr_to_gitlab.py
# 默认仍用方案 A；生产按需设 OCR_DASHBOARD_SPA=1
ENV OCR_DASHBOARD_SPA=1

EXPOSE 8010
CMD ["python3", "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8010"]
