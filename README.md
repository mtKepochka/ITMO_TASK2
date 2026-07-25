# Ticket Automation PoC

Локальный прототип безопасной классификации и маршрутизации тикетов
поддержки. Он показывает, как автоматически ответить на узкий безопасный
класс обращений, передать оператору рискованный или неуверенно распознанный
тикет и сохранить объяснимое решение без текста и PII в audit log.

Сервис с 5 млн пользователей получает около 200 тысяч тикетов в день и
всплески до 10–20 тысяч за 10 минут. Быстрая маршрутизация сокращает время
первого ответа и защищает операторов от повторяющихся вопросов.
Abstention и denylist удерживают billing/security у человека, поэтому
экономия нагрузки не достигается ценой небезопасных автоответов. PoC
проверяет эту архитектурную идею; эффект для бизнеса нужно измерять в
shadow/suggest-пилоте, а не выводить из искусственных примеров.

## Что реализовано

- два классификатора семи intent-категорий: rules по умолчанию и
  обучаемый TF-IDF + Logistic Regression;
- отдельные rules для email, телефона, номера карты и high-risk фраз;
- локальная JSON-база знаний и lexical retrieval;
- policy с denylist, узкой allowlist и abstention;
- детерминированный grounded-ответ и безопасный fallback при отказе;
- опциональные HTTP-адаптеры Ollama/OpenRouter с локальной валидацией;
- JSONL-аудит без исходного текста тикета;
- CLI, четыре demo-сценария, unit и smoke tests;
- idempotency по ticket ID в рамках одного экземпляра pipeline.

Runtime не требует API-ключей, сети или скачивания моделей.

Дополнительно реализована изолированная дискретно-событийная модель СМО:
она сравнивает baseline, burst, деградацию LLM и incident-mode на уровне
очередей и ограниченных ресурсов. Это исследование assumptions, а не
нагрузочный тест основного pipeline.

## Быстрый запуск

Требуется Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
make test
make demo
make smoke
make train-ml
make demo-ml
make simulate
make simulate-burst
make simulate-compare
```

После установки доступны отдельные команды:

```bash
python -m ticket_automation.cli process \
  --text "Не могу войти в аккаунт"
python -m ticket_automation.cli process --file data/demo_tickets.json
python -m ticket_automation.cli demo --simulate-generator-failure
```

CLI печатает категорию, эвристический confidence, risk, retrieval,
решение, fallback и путь к audit log. По умолчанию аудит записывается в
`audit/decisions.jsonl`; runtime-файл исключён из Git.

### Обучаемый классификатор

`make train-ml` обучает локальный sparse baseline на
`data/intent_dataset.jsonl`, сохраняет модель в
`artifacts/models/intent-classifier.joblib` и offline-отчёт в
`artifacts/ml/evaluation.json`. Оба runtime-артефакта исключены из Git.
После обучения режим включается командой:

```bash
python -m ticket_automation.cli process \
  --classifier ml \
  --classifier-model artifacts/models/intent-classifier.joblib \
  --text "Не могу войти в аккаунт"
```

Модель объединяет словные и символьные TF-IDF признаки и обучает
многоклассовую Logistic Regression с class weights. Датасет в
репозитории синтетический и нужен только для воспроизводимой
проверки train/evaluate/load/inference. Его метрики нельзя выдавать за
оценку качества на реальном потоке. Артефакт `joblib` следует загружать
только если он создан этим проектом в доверенной среде.

### Опциональный LLM

По умолчанию работает `deterministic`: тесты и demo не требуют сети.
Локальную установленную модель Ollama можно включить так:

```bash
TICKET_GENERATOR=ollama \
TICKET_LLM_MODEL='<installed-model>' \
python -m ticket_automation.cli process \
  --text "Приложение не открывается. Это общий сбой?"
```

Для OpenRouter ключ передаётся только через окружение:

```bash
export OPENROUTER_API_KEY='<key>'
TICKET_GENERATOR=openrouter \
TICKET_LLM_MODEL='<provider/model>' \
python -m ticket_automation.cli process \
  --text "Приложение не открывается. Это общий сбой?"
```

Те же значения можно задать флагами `--generator`, `--model`,
`--llm-base-url` и `--llm-timeout`; API key намеренно не принимается через
CLI. Дополнительные переменные: `OLLAMA_BASE_URL`, `OPENROUTER_BASE_URL` и
`TICKET_LLM_TIMEOUT`.

Адаптер вызывается только после PII/risk scan и получает очищенный текст
вместе с найденной статьёй. Пустой, слишком длинный, содержащий PII или
запрещённое обещание output отклоняется и включает прежний
fallback/escalation. Это минимальный guardrail, а не полноценная проверка
groundedness. Контракты соответствуют официальным
[Ollama Chat API](https://docs.ollama.com/api/chat) и
[OpenRouter Chat Completions](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request).

Simulation CLI поддерживает фиксированный seed и JSON/CSV:

```bash
python -m simulation.cli baseline --seed 42
python -m simulation.cli burst --seed 42 --output /tmp/burst.json
python -m simulation.cli llm-degradation --seed 42
python -m simulation.cli incident-mode --seed 42
python -m simulation.cli compare --seed 42
```

По умолчанию отчёты сохраняются в игнорируемый каталог
`artifacts/simulation/`. Для временных рядов передайте `--timeseries`,
для одного из двух PNG-графиков — `--plots DIR` и установите
`python -m pip install -e '.[plots]'`.

## CI

GitHub Actions запускается для push в `main`, pull request и вручную.
Workflow устанавливает проект с нуля, выполняет tests/demo/smoke,
обучает и запускает ML-классификатор, исполняет четыре simulation-сценария,
проверяет воспроизводимость JSON, balance и safety-инварианты, а также
рендерит Mermaid. ML-отчёт, отчёты симуляции и SVG доступны в артефакте
workflow в течение семи дней.

## Demo

| Ticket | Ожидаемое решение | Причина |
|---|---|---|
| приложение не открывается, общий сбой | `auto_reply` | безопасная allowlist и релевантная статья |
| двойное списание с номером карты | `escalate` | payment, PII и high risk |
| «Опять не работает» | `escalate` | низкий confidence |
| вопрос о тарифе | `suggest_to_agent` | категория вне auto-reply allowlist |

С `--simulate-generator-failure` outage получает утверждённый шаблон и
`fallback_used=true`; категория без такого шаблона эскалируется.

## Подход и границы

Rules отвечают за PII/risk, выбранный классификатор — за intent и
confidence, retrieval — за контекст, генератор — только за черновик после
safety-решения. В rules-режиме confidence основан на весах фраз; в
ML-режиме это максимальный `predict_proba`. Ни одно значение не
откалибровано на репрезентативных данных.

PoC выполняется одним процессом, последовательно и на четырёх статьях.
Внешний LLM по умолчанию выключен; адаптеры являются точкой расширения, а
не production-интеграцией. Обучаемая модель является sparse baseline на
небольшом синтетическом наборе, а не production-моделью. Здесь нет
настоящей async-очереди, межпроцессной идемпотентности, production storage
или измеренного качества на реальных данных. Целевая архитектура отделяет
hot path до 500 мс от асинхронных retrieval/generation.

## Документация

- [Архитектура](docs/architecture.md)
- [ML, retrieval и LLM](docs/ml.md)
- [Протокол оценки](docs/evaluation.md)
- [Monitoring](docs/monitoring.md)
- [Риски и эксплуатация](docs/risks-and-ops.md)
- [Дискретно-событийная модель СМО](docs/queueing-model.md)
- [Mermaid-схема СМО](docs/queueing-model.md#схема-сети)
- [Использование AI](AI_USAGE.md)
- [Рабочий журнал](WORKLOG.md)
- [Самопроверка](SELF_REVIEW.md)
