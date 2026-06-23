# OpenCodeReview GitLab CI runner image.
#
# LLM resolution at Job runtime (OCR native):
#   environment variables  >  /root/.opencodereview/config.json
#
# Build:
#   .\scripts\build_image.ps1    # reads %USERPROFILE%\.opencodereview\config.json
#
# Set GitLab CI/CD Variable OCR_CI_IMAGE=ocr-ci:local (or registry tag).

FROM docker.1ms.run/library/node:20

ARG OCR_NPM_VERSION=@alibaba-group/open-code-review

# Global OCR CLI (same npm channel as local dev)
RUN npm install -g "${OCR_NPM_VERSION}" \
    && ocr version || true

# Baked file config (overridden at runtime by OCR_LLM_* env when set in CI)
COPY .build/config.json /root/.opencodereview/config.json

COPY scripts/post_ocr_to_gitlab.py /usr/local/lib/ocr-ci/post_ocr_to_gitlab.py
COPY scripts/ocr_ci_config.py /usr/local/lib/ocr-ci/ocr_ci_config.py
RUN chmod +x /usr/local/lib/ocr-ci/post_ocr_to_gitlab.py
