FROM python:3.11-slim

ARG APP_VERSION
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="Ticket Automation PoC" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/mtKepochka/ITMO_TASK2"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TICKET_PROJECT_ROOT=/app \
    TICKET_AUDIT_PATH=/runtime/audit/decisions.jsonl \
    TICKET_MODEL_PATH=/runtime/models/intent-classifier.joblib \
    TICKET_CLASSIFIER_MODEL=/runtime/models/intent-classifier.joblib \
    TICKET_ML_REPORT_PATH=/runtime/ml/evaluation.json

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data

RUN python -m pip install --no-cache-dir . \
    && test "$(python -c 'import ticket_automation; print(ticket_automation.__version__)')" = "${APP_VERSION}" \
    && groupadd --system ticket \
    && useradd --system --gid ticket --home-dir /nonexistent ticket \
    && mkdir -p /runtime \
    && chown ticket:ticket /runtime

USER ticket
VOLUME ["/runtime"]

ENTRYPOINT ["ticket-automation"]
CMD ["demo"]
