# Self-review

## Почему такой baseline

Фразовые веса и lexical retrieval запускаются без сети, легко объясняются
в audit и позволяют проверить главный тезис: safety-policy не зависит от
генератора. Дополнительно реализован TF-IDF + Logistic Regression baseline,
но он выключен по умолчанию: 77 синтетических фраз проверяют инженерный
контур, а не качество. Следующий честный шаг — сравнение с rules и Linear
SVM на временном split реальных данных.

## Самое слабое место и assumptions

Слабее всего классификатор: словари не покрывают морфологию, опечатки,
смешанные темы и новый сленг. Предполагается русскоязычный текст,
нормализованный channel input, актуальная база знаний и уникальный ticket
ID. Regex PII не является достаточным privacy-контролем для production.

В rules-режиме confidence — функция весов найденных фраз и штрафа за
конкурирующую категорию. В ML-режиме это максимальный `predict_proba`, но
он также не откалиброван на репрезентативных labels. Evaluation теперь
сохраняет ненулевой sanity-порог из risk–coverage curve, но выбор порога
и оценка сделаны на одном синтетическом test split. Это устраняет
неработающий ML-demo, но не доказывает требуемую precision.

## Что нельзя доказать

Искусственные данные не показывают macro F1, high-risk recall,
калибровку, retrieval Recall@k, p99 под нагрузкой, operator acceptance,
CSAT, reopen rate или экономию. Они также не воспроизводят adversarial
PII и prompt injection. Возможен evaluation leakage, если дубликаты
инцидента попадут в разные split, будущая версия статьи используется для
старого тикета или operator route без проверки принимается как ground
truth.

## До production

Нужны согласованная taxonomy и разметка, temporal evaluation с incident и
high-risk slices, privacy/security review, durable idempotency, outbox,
очередь с backpressure, versioned KB, output validator, access/retention
policy, dashboards и runbooks. Раскатка должна пройти shadow и
suggest-mode до ограниченного auto-reply canary.

Следующие эксперименты:

1. сравнить реализованные rules и TF-IDF Logistic Regression с Linear SVM
   по risk–coverage curve на реальном temporal split;
2. сравнить BM25 и hybrid retrieval по incorrect-context и Recall@k;
3. в suggest-пилоте сравнить детерминированный шаблон и grounded LLM по
   acceptance, размеру правок, safety и стоимости;
4. провести replay массового инцидента и отказов audit/LLM.

От LLM следует отказаться для категории, если шаблон не хуже по
acceptance/правкам и безопаснее или дешевле. Только suggest-mode следует
оставить, если high-risk recall нестабилен, верхняя граница unsafe
auto-action превышает guardrail, растут reopen/override либо качество
ломается на новых инцидентах. Полностью автоматизировать payment, refund,
security, юридические угрозы и необработанное PII не следует.

Проект нужно остановить или радикально пересмотреть, если пилот не снижает
время обработки/нагрузку при неизменных safety, CSAT и reopen guardrails;
если операторы систематически переписывают черновики; либо стоимость и
ошибки сопровождения выше пользы.

## Ограничения симуляции

СМО формализует assumptions, но не измеряет производительность кода и не
доказывает capacity. Пуассоновский вход, lognormal service times и
условные вероятности не откалиброваны по production telemetry; один seed
не даёт доверительного интервала. Operator pool упрощён до общей очереди
без смен и skill-based routing, а recovery автоматического пути не означает
исчезновение operator backlog. До практических выводов нужны incident
replay, реальные latency/arrival histograms и серия репликаций.

## Ограничения LLM-адаптеров

Ollama/OpenRouter-адаптеры проверяют совместимость интерфейса, а не
качество конкретной модели. Вызов в PoC синхронный, нет retry/backoff,
rate-limit budget, полноценного circuit breaker и schema-groundedness
validator. Локальный denylist output снижает очевидный риск, но не
доказывает отсутствие галлюцинаций. Поэтому внешний provider по умолчанию
выключен, а расширять auto-reply allowlist из-за наличия LLM нельзя.

## Развёртывание и версии

Docker/Compose дают воспроизводимый CLI/API deployment и быстрый fast-forward
update, но это не production rollout: нет registry promotion, подписания
образов, SBOM, vulnerability gate и оркестратора. Version tags не должны
перезаписываться; ML-артефакт переобучается после смены scikit-learn.
