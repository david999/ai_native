# OCR Gateway — 生产 Docker 镜像（build context = ocr-ci2 仓库根）
#
# 构建：deploy/prod/docker/build_image.ps1
# 运行：deploy/prod/docker/run.ps1
#
# 逻辑清单：
# - 始终：镜像内 npm install -g OCR CLI（全新层，无 skip-if-present）
# - 复制：bake 后的 .build/config.json、gateway/、scripts/、发帖脚本到 /usr/local/lib/ocr-ci
# - 不做：运行时挂载宿主机 ~/.opencodereview（配置在构建时 bake）

FROM docker.1ms.run/library/node:20

ARG OCR_NPM_VERSION=@alibaba-group/open-code-review

RUN npm install -g "${OCR_NPM_VERSION}" \
    && ocr version || true

COPY .build/config.json /root/.opencodereview/config.json

COPY scripts/post_ocr_to_gitlab.py /usr/local/lib/ocr-ci/post_ocr_to_gitlab.py
COPY scripts/gitlab_mr.py /usr/local/lib/ocr-ci/gitlab_mr.py
COPY scripts/ocr_ci_config.py /usr/local/lib/ocr-ci/ocr_ci_config.py
RUN chmod +x /usr/local/lib/ocr-ci/post_ocr_to_gitlab.py

COPY gateway/requirements.txt /tmp/gateway-requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/gateway-requirements.txt

COPY gateway /app/gateway
COPY scripts /app/scripts
WORKDIR /app
ENV PYTHONPATH=/app
ENV OCR_POST_SCRIPT=/usr/local/lib/ocr-ci/post_ocr_to_gitlab.py

EXPOSE 8010
CMD ["python3", "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8010"]
