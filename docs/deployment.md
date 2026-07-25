# Развёртывание и обновления

Проект является CLI/исследовательским PoC, а не постоянно работающим HTTP-
сервисом. Поэтому deployment означает сборку воспроизводимого образа и
запуск нужной команды в контейнере. Образ работает от непривилегированного
пользователя, а audit, ML-модель и evaluation report хранятся в отдельном
Docker volume.

## Быстрый запуск

Требуются Docker и Docker Compose:

```bash
make container-demo
```

Команда собирает immutable-тег вида
`ticket-automation:0.2.0-<git-revision>`, а также удобные указатели
`ticket-automation:0.2.0` и `ticket-automation:latest`, затем запускает
demo. Для ML-пути:

```bash
make container-train-ml
make container-demo-ml
```

Compose использует именованный volume `ticket-automation_ticket-runtime`.
Поэтому модель, отчёт и audit переживают пересоздание контейнера и не
попадают в Git. Посмотреть версию без запуска demo:

```bash
docker run --rm ticket-automation:0.2.0 --version
```

## Версионность

Единственный источник версии приложения — `ticket_automation.__version__`.
Setuptools получает из него версию wheel, CLI печатает её через
`--version`, Docker сохраняет её вместе с Git revision в OCI labels и
immutable-теге, audit — в `pipeline_version`. Версия classifier включает
формат артефакта и первые 12 символов SHA-256 обучающего набора; версия KB
— первые 12 символов SHA-256 JSON-файла.

Проект использует Semantic Versioning:

- patch — совместимое исправление;
- minor — новая совместимая возможность или изменение PoC-контракта;
- major — несовместимое изменение CLI, данных или audit schema.

Перед выпуском меняются `__version__` и `CHANGELOG.md`, выполняются CI и
smoke, затем создаётся Git tag `vX.Y.Z`. Тег `<version>-<revision>` не
перезаписывается; `<version>` и `latest` являются только удобными
локальными указателями.

## Быстрое обновление

На хосте с чистым checkout:

```bash
make update
```

Цель выполняет только fast-forward `git pull --ff-only`, заново читает
версию из обновлённого кода, собирает образ с `--pull` и проверяет его
командой `--version`. Для развёртывания ML-режима с переобучением модели:

```bash
make update-ml
```

Переобучение после обновления намеренно явно: `joblib`-артефакты требуют
совпадения версии scikit-learn. Обновление не удаляет старые revision
tags, поэтому быстрый rollback выполняется запуском предыдущего тега:

```bash
docker run --rm ticket-automation:0.1.0-<previous-revision> demo
```

В production этот процесс заменяется публикацией immutable image digest в
закрытый registry и rolling update оркестратора. Для данного PoC registry,
автоматический push и долгоживущий сервис сознательно не добавлены.
