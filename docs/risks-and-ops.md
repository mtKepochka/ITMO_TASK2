# Риски и эксплуатация

| Риск | Сигнал | Mitigation | Fallback | Владелец |
|---|---|---|---|---|
| PII leakage | validator block, privacy-аудит, canary PII | локальный scan и redaction до внешних вызовов; минимум данных | запрет генерации и оператор | Security / Privacy |
| Hallucination или unsafe action | groundedness review, запрещённые обещания, override | retrieval-grounding, allowlist, output validator | шаблон или оператор | ML + Support Quality |
| Prompt injection | попытки изменить инструкцию, anomalous output | текст пользователя только как недоверенные данные; отделённый контекст | отбросить output | AppSec + ML |
| Неверная маршрутизация | confusion matrix, override, high-risk recall | abstention, denylist, калибровка, свежая разметка | general triage | ML + Support Ops |
| Устаревшая база знаний | no-hit, жалобы, истёкший review date | versioning, owner и срок ревью статьи | suggest без отправки | Knowledge team |
| Drift без быстрых labels | distribution alert + delayed error | temporal evaluation, срезы, targeted labeling | поднять thresholds | ML |
| Отказ LLM | timeout/error/fallback, circuit state | bounded timeout, circuit breaker, очередь | утверждённый шаблон или оператор | Platform |
| Переполнение очереди | depth, oldest lag, SLA budget | backpressure, приоритеты, autoscaling async workers | отключить необязательную генерацию | Platform / Support Ops |
| Рост inference cost | tokens/cost per accepted draft | model routing, context limits, category budgets | lexical + templates | ML / FinOps |
| Недоступность аудита | write failures, reconciliation gap | durable store, outbox, immutable retention | запрет auto-reply | Platform / Compliance |

## Эксплуатационные правила

Синхронный контур ограничен нормализацией, rules, классификацией и policy;
очередь изолирует retrieval/generation и поглощает всплеск. Повторная
доставка безопасна через idempotency key, а retries имеют лимит и jitter.
Runbook отдельно описывает LLM outage, lag, PII-инцидент и массовый
продуктовый сбой.

Нельзя автоматически закрывать billing, refund, account security,
необработанное PII, unknown и low-confidence. Human-in-the-loop видит
сигналы и статью, но не должен слепо доверять черновику. Любое расширение
allowlist проходит shadow → suggest → ограниченный canary и может быть
откачено независимо от модели.

Хранение разделено: исходный тикет — в защищённом операционном store,
аудит — без текста/PII, обучающие snapshots — деидентифицированы и имеют
retention. Доступ, удаление и экспорт проверяются по требованиям компании
и применимому законодательству до пилота.
