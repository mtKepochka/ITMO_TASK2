# Changelog

Формат основан на Keep a Changelog, версии используют Semantic Versioning.

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
