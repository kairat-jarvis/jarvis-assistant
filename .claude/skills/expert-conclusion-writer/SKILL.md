---
name: expert-conclusion-writer
description: Интерфейс JARVIS → expertise-orchestrator для экспертизы проектной документации. Использовать когда: «проверь АПС», «запусти экспертизу», «найди замечания по ОВ», «прочитай результаты прогона», «напиши замечание по норме», «что говорит СП о...». JARVIS делегирует фактический анализ — не делает его сам.
---

# Expert Conclusion Writer — мост JARVIS → expertise-orchestrator

JARVIS является центральным оркестратором (Winston из «Происхождения» Дэна Брауна).
**Экспертизу проектной документации выполняет expertise-orchestrator** — специализированная multi-agent система с 31 агентом, каждый на свой раздел ПСД.

JARVIS:
- принимает задачу от пользователя
- транслирует её в команды expertise-orchestrator
- запускает прогон, отслеживает выполнение
- читает и интерпретирует результаты (`замечания.xlsx`)
- при необходимости — уточняет замечания через прямой поиск НТД

---

## Путь к expertise-orchestrator

```
/Users/kairat/Claude Code/PROGRAMMING/expertise-orchestrator/
```

Запуск:
```bash
cd "/Users/kairat/Claude Code/PROGRAMMING/expertise-orchestrator"
npm run poc -- <agent>:<файл.pdf> [<agent2>:<файл2.pdf> ...]
```

Выходные файлы: `data/runs/<timestamp>/замечания.xlsx` (основной), `findings.json`, `run.json`.

---

## Агенты (31) — быстрый справочник

| Группа | Коды | Раздел ПСД |
|--------|------|-----------|
| fire-safety | `aps` | АПС (пожарная сигнализация) |
| | `soue` | СОУЭ (оповещение) |
| | `apt` | АУПТ (автоматическое пожаротушение) |
| | `pt` | ПТ (противопожарный водопровод) |
| | `ppo` | ППО (первичные средства) |
| engineering | `ov` | ОВиК (вентиляция, кондиционирование) |
| | `vk` | ВК (водоснабжение и канализация) |
| | `tm` | ТМ (теплоснабжение) |
| | `eg` | Наружные газовые сети |
| electrical | `elec` | ЭМ/ЭО (электроснабжение) |
| low-current | `skud` | СКУД |
| | `video` | СВН (видеонаблюдение) |
| | `sks` | СКС (структурированная кабельная сеть) |
| | `ss` | СС (связь/диспетчеризация) |
| | `kipia` | КИПиА |
| structural | `kr` | КР/КЖ/КМ (конструктив) |
| planning | `gp` | ГП (генеральный план) |
| | `vn` | ВН (наружные сети) |
| | `pos` | ПОС/ППО |
| docs | `mopb` | МОПБ |
| | `pz` | Пояснительная записка |
| | `ar` | АР |
| | `tkh` | ТХ (технологические решения) |
| | `igi` | ИГИ |
| | `goch` | ГОЧС |
| | `odi` | ОДИ (МГН) |
| formatting | `fmt` | Форматный контроль СПДС |
| equipment | `equip` | Вендорская документация |
| | `agsk` | Коды АГСК-3 в спецификациях → **делегирует в проект АГСК-3** |
| | `price` | Прайс-листы vs спецификации |
| cross-analysis | `qa` | Контроль качества, межразделовые связи |

**8 кросс-пар** (запускаются автоматически при одновременном запуске пары):
`aps↔soue`, `aps↔pt`, `aps↔apt`, `aps↔elec`, `ov↔aps`, `aps↔skud`, `aps↔video`, `aps↔ss`

---

## Агент `agsk` — делегирование в проект АГСК-3

Агент `agsk` — единственный в expertise-orchestrator, который **не анализирует PDF через Claude API**,
а делегирует его специализированному проекту АГСК-3.

```
JARVIS
  └─ expertise-orchestrator агент agsk
       └─ agsk-bridge.py (Python-мост)
            └─ /Users/kairat/Claude Code/АГСК-3/pipeline/*
                 ├─ pdf_detector → native | scanned
                 ├─ pdfplumber / Claude Vision
                 ├─ MdReference (234K кодов, апрель 2026)
                 ├─ compare_names() 9-уровневое сравнение
                 └─ шаблон проверки спецификации на АГСК-3.xlsx → Excel-отчёт
```

**Когда пользователь запрашивает проверку спецификаций на коды АГСК-3:**
- Запуск через expertise-orchestrator: `npm run poc -- agsk:Спецификация.pdf`
- Прямой запуск АГСК-3: `python validate_agsk3.py spec.pdf -r "base/АГСК-3_апрель 2026.md" --format xlsx`
- Результат: Excel-отчёт по шаблону (9 колонок: Позиция, Наименование, Код, Статус кода, Статус наименования, Замечание…)

**Логика проверки, справочник и шаблон живут только в АГСК-3** — не дублировать в expertise-orchestrator и не в JARVIS ASSISTANT.

---

## Режимы работы

### Режим A — Полный прогон (делегирование)

Пользователь предоставил PDF-файлы разделов. JARVIS запускает прогон.

**Алгоритм:**
1. Уточни пути к PDF (если не указаны явно — спроси)
2. Определи коды агентов по названиям разделов (таблица выше)
3. Запусти прогон:

```bash
cd "/Users/kairat/Claude Code/PROGRAMMING/expertise-orchestrator"
npm run poc -- aps:"/path/to/АПС.pdf" soue:"/path/to/СОУЭ.pdf"
```

4. Найди последний результат:
```bash
ls -t "/Users/kairat/Claude Code/PROGRAMMING/expertise-orchestrator/data/runs/" | head -3
```

5. Прочитай `run.json` для метрик, `findings.json` для замечаний:
```bash
cat "data/runs/<timestamp>/run.json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('Агентов:', len(d.get('agents', {})))
for a, v in d.get('agents', {}).items():
    print(f'  {a}: {len(v.get(\"findings\",[]))} замечаний, статус={v.get(\"status\")}')
"
```

6. Сообщи пользователю: количество замечаний по агентам, путь к замечания.xlsx

### Режим B — Ad-hoc замечание (без прогона)

Пользователь хочет быстро написать одно замечание или проверить конкретный пункт.

**Алгоритм:**
1. Поиск в базе НТД:
```bash
cd "/Users/kairat/Claude Code/JARVIS ASSISTANT"
.venv/bin/python .claude/skills/expert-conclusion-writer/scripts/ntd_search.py \
  "текст запроса по теме нарушения" --format remark -n 5
```

2. Выбрать наиболее точный пункт из результатов
3. Заполнить шаблон:

```
Замечание: [Раздел ПД, лист/чертёж NN].

[Описание нарушения в проектном решении] не соответствует требованиям
[doc_code], п. [clause_no]:
«[цитата нормы — дословно]».

Требуется: [конкретное исправление].
```

### Режим C — Чтение и анализ результатов прогона

Пользователь хочет просмотреть / обсудить результаты предыдущего прогона.

```bash
# Последние прогоны:
ls -t "/Users/kairat/Claude Code/PROGRAMMING/expertise-orchestrator/data/runs/"

# Читаем findings.json конкретного прогона:
python3 -c "
import json
with open('data/runs/<timestamp>/findings.json') as f:
    data = json.load(f)
for agent, findings in data.items():
    for fnd in findings:
        print(f\"[{fnd.get('severity','?').upper()}] {fnd.get('norm','')} — {fnd.get('title','')[:80]}\")
"
```

### Режим D — Устранение замечаний

Проверка, устранено ли конкретное замечание:
1. Найти норму через `ntd_search.py --format cite`
2. Сравнить с описанием исправления от пользователя
3. Сформулировать «замечание устранено» или «замечание не устранено, т.к. …»

---

## Что НЕ делать

- ❌ **Не запускать Claude API для анализа PDF самостоятельно** — это делает expertise-orchestrator
- ❌ **Не дублировать логику агентов** — они уже покрывают 31 раздел
- ❌ **Не выдумывать нормы** — только из базы НТД (expertise_ntd) или из результатов прогона
- ❌ **Не запускать прогон без PDF-файлов** — спросить путь у пользователя

---

## Быстрые команды

```bash
# Запуск прогона по АПС
cd "/Users/kairat/Claude Code/PROGRAMMING/expertise-orchestrator" && npm run poc -- aps:"data/sample/АПС.pdf"

# Несколько разделов параллельно
npm run poc -- aps:"АПС.pdf" soue:"СОУЭ.pdf" elec:"ЭС.pdf"

# Спецификации (АГСК + прайс вместе)
npm run poc -- "agsk:Спец.pdf" "price:КП.pdf,Спец.pdf"

# Последний прогон — краткая сводка
ls -t data/runs | head -1 | xargs -I{} cat data/runs/{}/run.json | \
  python3 -m json.tool | grep -E '"(status|total|agent)"' | head -20

# Поиск нормы для быстрого замечания
cd "/Users/kairat/Claude Code/JARVIS ASSISTANT"
.venv/bin/python .claude/skills/expert-conclusion-writer/scripts/ntd_search.py "запрос" --format remark
```

---

## Сохранение результатов в JARVIS Memory

После завершения прогона — сохранить в `jarvis_memory`:
```python
import sys; sys.path.insert(0, "/Users/kairat/Claude Code/JARVIS ASSISTANT")
from scripts.jarvis_local import JarvisLocal
cli = JarvisLocal()
cli.add_memory(
    content=f"Прогон expertise-orchestrator: {run_id}. Агентов: N. Замечаний: M.",
    content_type="agent_report",
    summary="Результат экспертизы [объект] от [дата]",
    tags=["экспертиза", "expertise-orchestrator", "замечания"],
    priority="high",
    related_project="expertise-orchestrator",
    metadata={"run_id": run_id, "agents_run": [...], "total_findings": M},
)
```
