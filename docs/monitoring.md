# Monitoring

Метрики связываются по `ticket_id`, версии pipeline, rollout, classifier и
базы знаний. В PoC версии записываются в JSONL audit, а FastAPI endpoint
`/api/v1/metrics` показывает число запросов, распределение actions,
средний fast-path latency и technical fallback. Это process-local
счётчики, не замена Prometheus. Telemetry не содержит исходный текст или
найденное PII.

## Online-сигналы

| Область | Метрики |
|---|---|
| Нагрузка | throughput по каналу, queue depth, oldest-message lag |
| Надёжность | error, timeout, retry, fallback и dead-letter rate |
| Задержка | p50/p95/p99 hot path и end-to-end по этапам |
| Вход | category, channel/language mix, text length, PII rate |
| Решения | confidence distribution, abstention, action/route distribution |
| Retrieval | no-hit rate, score distribution, article/version frequency |
| Generation | invalid output, PII block, token usage, стоимость |
| Delayed quality | override, acceptance/edit, reopen, SLA и CSAT |

Стартовые технические алерты, уточняемые после baseline: p99 горячего пути
выше 500 мс пять минут; устойчивый рост oldest-message lag; ошибки или
fallback выше обычного коридора; невозможность записи аудита; ненулевой
PII leakage validator. Алерты по распределениям требуют минимального
размера окна и сравнения с тем же часом/днём недели, иначе всплеск создаст
шум.

Стоимость наблюдается как tokens и деньги на сгенерированный, показанный и
принятый черновик. Лимиты по категории и дневной budget выключают
необязательную генерацию, но не rules/classification.

## Drift и инциденты

- **Covariate drift:** изменились тексты, длина, язык или канал при прежней
  связи признаков с меткой.
- **Label shift:** изменилась доля истинных категорий, например во время
  outage.
- **Concept drift:** прежняя формулировка теперь означает другой маршрут
  из-за продукта или policy.
- **Knowledge-base change:** поменялся corpus/текст статей; это может
  изменить retrieval без деградации классификатора.
- **Продуктовый инцидент:** резкий согласованный рост одной темы и
  повторяющихся текстов, часто с нормальным качеством модели.

Изменение входного потока само по себе не доказывает деградацию. Диагностика
сопоставляет feature drift, delayed labels, operator override, версию KB,
релизы продукта и incident registry. Concept drift подтверждается ростом
ошибок на свежей размеченной выборке, а не одним PSI/KS сигналом.

## Контур качества

Ежедневно берётся стратифицированная выборка auto-reply, abstention,
fallback и high-risk. Операторы выбирают причину override; команда качества
проверяет выборку PII false negatives. Еженедельно пересчитываются
classification/retrieval срезы на накопившихся подтверждённых labels.
Смена threshold, taxonomy, модели или KB имеет версию, canary и возможность
отката.

Предполагаемые владельцы: platform/on-call — latency и очереди; ML —
confidence/drift; support quality — overrides и разметка; knowledge team —
актуальность статей; security/privacy — PII и unsafe actions; FinOps —
лимиты LLM.

## Связь с симуляцией

[Модель СМО](queueing-model.md) выдаёт те же queue depth/lag, latency,
throughput, utilization, fallback, timeout и loss-показатели в модельном
времени. Production telemetry используется для калибровки arrival и
service distributions, conditional probabilities и provider state.
Расхождение replay с наблюдаемыми очередями — сигнал неверных assumptions,
а не повод «подгонять» capacity по одному прогону.
