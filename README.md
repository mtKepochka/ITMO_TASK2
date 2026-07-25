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

- интерпретируемый классификатор семи intent-категорий;
- отдельные rules для email, телефона, номера карты и high-risk фраз;
- локальная JSON-база знаний и lexical retrieval;
- policy с denylist, узкой allowlist и abstention;
- детерминированный grounded-ответ и безопасный fallback при отказе;
- JSONL-аудит без исходного текста тикета;
- CLI, четыре demo-сценария, unit и smoke tests;
- idempotency по ticket ID в рамках одного экземпляра pipeline.

Runtime не требует API-ключей, сети или скачивания моделей.

## Быстрый запуск

Требуется Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
make test
make demo
make smoke
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

Rules отвечают за PII/risk, lightweight baseline — за intent и confidence,
retrieval — за контекст, генератор — только за черновик после safety-
решения. Значение confidence основано на весах совпавших фраз и **не
является откалиброванной вероятностью**.

PoC выполняется одним процессом, последовательно и на четырёх статьях.
Здесь нет внешнего LLM, обученной модели, настоящей async-очереди,
межпроцессной идемпотентности, production storage или измеренного качества
на реальных данных. Целевая архитектура отделяет hot path до 500 мс от
асинхронных retrieval/generation.

## Документация

- [Архитектура](docs/architecture.md)
- [ML, retrieval и LLM](docs/ml.md)
- [Протокол оценки](docs/evaluation.md)
- [Monitoring](docs/monitoring.md)
- [Риски и эксплуатация](docs/risks-and-ops.md)
- [Использование AI](AI_USAGE.md)
- [Рабочий журнал](WORKLOG.md)
- [Самопроверка](SELF_REVIEW.md)
