# Рабочий журнал

1. Сначала изучены требования трека «ИИ», а локальный HTML-референс
   исключён только через Git-local exclude.
2. Scope ограничен одним Python-процессом без внешних сервисов и ключей.
3. Создан запускаемый каркас; пустой набор тестов обнаружен проверкой и
   исправлен до первого нового коммита.
4. Отдельными этапами добавлены интерпретируемая классификация и rules для
   PII/high-risk.
5. Затем связаны локальная база знаний, retrieval и консервативная policy.
6. End-to-end pipeline получил CLI, JSONL-аудит, happy, risky,
   low-confidence и generator-failure сценарии.
7. Unit и smoke tests закрепили safety-инварианты, после чего документация
   была сверена с реальными threshold и поведением кода.
8. На первом этапе сознательно не реализованы внешний LLM, UI, настоящий
   брокер, production storage и Kubernetes: они не нужны для проверки
   выбранной архитектурной идеи.
9. После основного PoC добавлена изолированная SimPy-модель сети очередей с
   условными переходами, конечными буферами и balance-инвариантами.
10. Отдельно реализованы burst, provider degradation, circuit breaker и
    incident-шаблон; сценарии сравниваются на одинаковом seeded потоке.
11. Результаты seed 42 внесены в технический документ как следствия
    assumptions, а не как доказательство production capacity.
12. Для дальнейших экспериментов добавлены выключенные по умолчанию
    Ollama/OpenRouter-адаптеры; секрет остаётся в окружении, а provider
    errors и небезопасный output используют прежний fail-closed fallback.
13. Добавлен опциональный обучаемый TF-IDF + Logistic Regression
    классификатор, синтетический train/test harness, сохранение модели и
    отчёт с macro F1/confusion matrix/risk coverage.
14. ML-путь встроен через интерфейс pipeline, но rules оставлен default;
    прежняя safety-policy применяется к обоим классификаторам без
    послабления порога ради demo.
15. Финальный аудит выявил расхождение safety-переходов СМО с основным
    pipeline; PII/high-risk/low-confidence и `operator_required` приведены
    к единой fail-closed семантике и закреплены regression-тестами.
16. Для воспроизводимого развёртывания добавлены единая версия приложения,
    Docker/Compose, immutable version tag, audit-версии и fast-forward
    update/rollback workflow.
17. Архитектурное ревью привело к suggest-by-default rollout, локальному
    FastAPI/dashboard, HTML/Unicode preprocessing и конкурентному
    fault-injection benchmark.
18. Classification и risk scan распараллелены под общим deadline;
    idempotency усилена single-flight, а ML-артефакт получил явно
    ограниченный sanity threshold/coverage curve.
19. Добавлен optional semantic retrieval с pinned E5 revision, кешированием
    KB embeddings, offline-режимом и наблюдаемым lexical fallback.
20. Стандартный demo и контейнер переведены на обучаемый ML baseline;
    rules оставлен явным быстрым fallback.
21. Продуктовый контур формализован через backlog гипотез, controlled
    pilot, sensitivity formula, guardrails и stop-критерии без заявления
    неподтверждённого ROI.
