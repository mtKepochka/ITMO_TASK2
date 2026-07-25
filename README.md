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

- два классификатора семи intent-категорий: обучаемый TF-IDF + Logistic
  Regression в стандартном demo/контейнере и rules как offline fallback;
- отдельные rules для email, телефона, номера карты и high-risk фраз;
- локальная JSON-база знаний, lexical retrieval и optional pinned E5
  semantic retrieval с кешем и fallback;
- policy с denylist, узкой allowlist и abstention;
- versioned rollout с suggest-by-default, kill switch, allowlist и canary;
- детерминированный grounded-ответ и безопасный fallback при отказе;
- опциональные HTTP-адаптеры Ollama/OpenRouter с локальной валидацией;
- JSONL-аудит без исходного текста тикета;
- CLI, FastAPI, web-панель, benchmark, unit и smoke tests;
- single-flight idempotency по ticket ID в рамках одного процесса;
- параллельные classification/risk scorers с общим deadline 500 мс.

Runtime не требует API-ключей, сети или скачивания моделей.
Текущая версия приложения — `0.4.0`.

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
make demo-rules
make demo-auto
python -m pip install -e '.[semantic]'
make demo-semantic
make api
make benchmark
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

`make demo` сначала воспроизводимо обучает ML baseline и запускает его в
suggest-only режиме. `make demo-rules` не требует ML-артефакта.

CLI печатает категорию, confidence, risk, retrieval source/fallback,
решение, fallback и путь к audit log. По умолчанию аудит записывается в
`audit/decisions.jsonl`; runtime-файл исключён из Git.

`make api` запускает API и dashboard на `http://127.0.0.1:8000`;
OpenAPI доступен на `/docs`, health — на `/api/v1/health`. Контейнерный
вариант запускается одной командой `make container-api`.

### Быстрое развёртывание

При наличии Docker весь локальный setup заменяется одной командой:

```bash
make container-demo
```

Контейнер содержит обученный при сборке ML baseline и использует его по
умолчанию. Для явного переобучения с сохранением модели в volume:

```bash
make container-train-ml
make container-demo-ml
```

`make deploy` собирает версионированный образ и проверяет его версию.
`make update` выполняет fast-forward обновление checkout и повторный
deployment; `make update-ml` дополнительно переобучает и проверяет
ML-артефакт. Полный контракт версий, rollback и эксплуатационные команды
описаны в [руководстве по развёртыванию](docs/deployment.md).

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
Отчёт строит threshold/coverage curve и сохраняет выбранный sanity-порог
в артефакте модели. Сейчас это даёт ненулевую selective coverage, но
порог подобран на том же маленьком синтетическом holdout и не является
доказательством качества.

### Опциональный semantic retrieval

После установки optional extra можно включить E5:

```bash
python -m pip install -e '.[semantic]'
python -m ticket_automation.cli process \
  --classifier ml \
  --classifier-model artifacts/models/intent-classifier.joblib \
  --retriever e5 \
  --text "Экран авторизации постоянно отвергает мои данные"
```

Используется `intfloat/multilingual-e5-small` с зафиксированной ревизией
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. Модель и версионированные
KB embeddings кешируются в `artifacts/embeddings/`. Для запуска только из
локального cache передайте `--semantic-offline`.

Если optional dependency, сеть или checkpoint недоступны, runtime явно
помечает `retrieval.fallback_used=true` и использует lexical retriever.
Runtime-ошибка encoder имеет тот же fallback. Semantic score и margin
остаются некалиброванными sanity-порогами; E5 не меняет safety-policy и
не расширяет auto-reply allowlist.

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
собирает и запускает deployment image и рендерит Mermaid. ML-отчёт,
отчёты симуляции и SVG доступны в артефакте workflow в течение семи дней.

## Demo

| Ticket | Ожидаемое решение | Причина |
|---|---|---|
| приложение не открывается, общий сбой | `suggest_to_agent` | default rollout не отправляет ответ автоматически |
| двойное списание с номером карты | `escalate` | payment, PII и high risk |
| «Опять не работает» | `escalate` | низкий confidence |
| вопрос о тарифе | `suggest_to_agent` | категория вне auto-reply allowlist |

`make demo-auto` использует отдельную демонстрационную rollout-конфигурацию
и показывает `auto_reply` только для разрешённого `service_outage`.

С `--simulate-generator-failure` outage получает утверждённый шаблон и
`fallback_used=true`; категория без такого шаблона эскалируется.

## Подход и границы

Rules отвечают за PII/risk, выбранный классификатор — за intent и
confidence, retrieval — за контекст, генератор — только за черновик после
safety-решения. В rules-режиме confidence основан на весах фраз; в
ML-режиме это максимальный `predict_proba`. CLI без явной конфигурации
сохраняет быстрый rules fallback, а `make demo` и Docker используют ML.
Ни одно значение не откалибровано на репрезентативных данных.

PoC выполняется одним процессом и на четырёх статьях. Preprocessing
нормализует HTML/Unicode и маскирует PII до классификатора; classification
и risk scan выполняются параллельно с общим deadline. Retrieval и
generation остаются синхронными после safety gate.
Внешний LLM по умолчанию выключен; адаптеры являются точкой расширения, а
не production-интеграцией. Обучаемая модель является sparse baseline на
небольшом синтетическом наборе, а не production-моделью. Здесь нет
настоящей async-очереди, межпроцессной идемпотентности, production storage
или измеренного качества на реальных данных. Целевая архитектура отделяет
hot path до 500 мс от асинхронных retrieval/generation.

## Документация

- [Архитектура](docs/architecture.md)
- [Продуктовая гипотеза и пилот](docs/product.md)
- [ML, retrieval и LLM](docs/ml.md)
- [Протокол оценки](docs/evaluation.md)
- [Monitoring](docs/monitoring.md)
- [Риски и эксплуатация](docs/risks-and-ops.md)
- [Развёртывание и обновления](docs/deployment.md)
- [Дискретно-событийная модель СМО](docs/queueing-model.md)
- [История версий](CHANGELOG.md)
- [Mermaid-схема СМО](docs/queueing-model.md#схема-сети)
- [Использование AI](AI_USAGE.md)
- [Рабочий журнал](WORKLOG.md)
- [Самопроверка](SELF_REVIEW.md)
