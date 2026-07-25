# Self-review

## Почему такой baseline

Фразовые веса и lexical retrieval запускаются без сети, легко объясняются
в audit и позволяют проверить главный тезис: safety-policy не зависит от
генератора. Для четырёх demo-тикетов обученная модель создала бы ложное
ощущение качества. Следующий честный baseline — TF-IDF + Logistic
Regression/Linear SVM на временном split.

## Самое слабое место и assumptions

Слабее всего классификатор: словари не покрывают морфологию, опечатки,
смешанные темы и новый сленг. Предполагается русскоязычный текст,
нормализованный channel input, актуальная база знаний и уникальный ticket
ID. Regex PII не является достаточным privacy-контролем для production.

Confidence — функция весов найденных фраз и штрафа за конкурирующую
категорию. Это не вероятность, потому что score не обучен и не
откалиброван на репрезентативных labels. Порог `0.70` демонстрирует
abstention, но не доказывает требуемую precision.

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

1. сравнить rules с TF-IDF Logistic Regression и Linear SVM по
   risk–coverage curve;
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
