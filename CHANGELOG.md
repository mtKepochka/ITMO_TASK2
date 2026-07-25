# Changelog

Формат основан на Keep a Changelog, версии используют Semantic Versioning.

## 0.4.0 — 2026-07-25

### Added

- optional E5 semantic retriever с pinned model revision;
- локальный cache модели и версионированных KB embeddings;
- lexical fallback с явными source/fallback полями в результате и audit;
- semantic offline fallback check в CI;
- продуктовый backlog, pilot design, guardrails и stop-критерии.

### Changed

- стандартный `make demo` использует обучаемый ML-классификатор;
- Docker image содержит воспроизводимо обученный ML baseline и запускает
  его по умолчанию;
- rules-сценарий сохранён отдельной командой `make demo-rules`.

## 0.3.0 — 2026-07-25

### Added

- FastAPI, OpenAPI, health/metrics endpoints и локальный dashboard;
- versioned suggest-by-default rollout с kill switch, allowlist и canary;
- параллельный hot path с общим deadline и fault-injection benchmark;
- HTML/Unicode normalization и PII masking до intent classifier;
- threshold/coverage curve и порог в ML-артефакте.

### Fixed

- конкурентные повторы одного ticket ID используют single-flight и создают
  одну audit-запись;
- автоматическая отправка больше не включена default-конфигурацией;
- JSONL-аудит защищён от конкурентной записи внутри процесса.

## 0.2.0 — 2026-07-25

### Added

- обучаемый TF-IDF + Logistic Regression классификатор;
- опциональные Ollama/OpenRouter-адаптеры;
- версионированный Docker/Compose deployment;
- версии pipeline, classifier и knowledge base в audit.

### Fixed

- PII, high-risk и low-confidence outage больше не завершаются fallback в
  СМО;
- `operator_required` имеет приоритет над incident template;
- risky/PII/low-confidence обращения не вызывают retrieval;
- CLI выдаёт контролируемую ошибку для битых входов и конфигурации.

## 0.1.0 — 2026-07-25

### Added

- rules-классификатор, PII/risk scan, lexical retrieval и safety-policy;
- детерминированная генерация, fallback, JSONL-аудит и CLI;
- SimPy-модель baseline, burst, provider degradation и incident-mode;
- unit/smoke tests, документация и CI.
