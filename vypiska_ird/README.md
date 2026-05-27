# Выписка ИРД — десктоп

Десктоп-приложение (Python + tkinter) для извлечения полей из PDF с ИРД
и формирования выписки в DOCX / XLSX.

## Что делает

1. Открыть PDF (ИРД / заключение экспертизы / АПЗ).
2. Извлечь текст через трёхуровневый waterfall:
   - **pdfplumber** — текстовый слой PDF (мгновенно)
   - **PaddleOCR-VL-1.5** — сканы и изображения (локально, без сети)
   - **Claude Vision** — fallback при провале PaddleOCR (опционально, требует `ANTHROPIC_API_KEY`)
3. Распарсить ~25 стандартных полей ИРД регулярными выражениями
   (наименование, заказчик, категория сложности, ТЭП, ТУ, пожарные классы и т.д.).
4. Показать в таблице — инженер редактирует двойным кликом.
5. Экспорт: DOCX (с таблицей под офиц. выписку) или XLSX.

## Установка (macOS)

### 1. Системные зависимости (Homebrew)

```bash
brew install poppler   # pdf2image — рендер PDF → PNG для OCR
```

### 2. Python-зависимости

```bash
cd vypiska_ird
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. PaddleOCR-VL-1.5 (tier 2, обязателен для сканов)

```bash
pip install "paddleocr>=3.1" paddlepaddle numpy
```

### 4. Claude Vision (tier 3, опционально)

Нужен только для сложных случаев: рукопись, повреждённые сканы, нестандартный layout.
При отсутствии ключа приложение работает полностью offline — waterfall останавливается на tier 2.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

> **Документы ограниченного распространения:** запускайте без `ANTHROPIC_API_KEY` —
> тогда tier 3 не вызывается и ни один байт документа не уходит за пределы машины.

## Запуск

```bash
cd vypiska_ird
source .venv/bin/activate
python main.py
```

## Сборка .app (для распространения)

```bash
cd vypiska_ird
bash build.sh
# → dist/VypiskaIRD.app
open dist/VypiskaIRD.app         # запустить
cp -r dist/VypiskaIRD.app /Applications/   # установить
```

## Конфигурация (переменные окружения)

| Переменная | По умолчанию | Смысл |
|------------|-------------|-------|
| `WATERFALL_MIN_TEXT_LEN` | `50` | Порог длины текста для признания страницы «не сканом» |
| `PADDLE_CONF_THRESHOLD` | `0.6` | Минимальная уверенность PaddleOCR для принятия результата |
| `PADDLE_LANG` | `ru` | Язык модели PaddleOCR |
| `ANTHROPIC_API_KEY` | — | Если не задан — tier 3 не вызывается (offline-режим) |
| `CLAUDE_VISION_MODEL` | `claude-sonnet-4-6` | Модель для Claude Vision fallback |

## Архитектура

```
vypiska_ird/
├── main.py                       # точка входа
├── requirements.txt
├── build.sh                      # сборка macOS .app
├── VypiskaIRD.spec               # PyInstaller spec (macOS bundle)
├── README.md
└── ird_extract/
    ├── ocr_waterfall.py          # 3-tier waterfall: pdfplumber → PaddleOCR-VL → Claude Vision
    ├── extractor.py              # тонкая обёртка над ocr_waterfall
    ├── fields.py                 # определения полей и регулярки
    ├── parser.py                 # текст → словарь полей
    ├── classifier.py             # классификация документов по разделам
    ├── exporter.py               # одиночный экспорт → DOCX / XLSX
    ├── batch_exporter.py         # пакетный экспорт → DOCX
    ├── batch_tab.py              # tkinter UI пакетной обработки
    └── ui.py                     # главное окно
```

## Поля, которые извлекаются

- Наименование объекта, вид строительства, адрес
- Заказчик, генпроектировщик, АПЗ (№/дата)
- Кадастровый номер, площадь и назначение участка
- Категория сложности, уровень ответственности, этажность, высота
- Площадь застройки, общая, полезная, строительный объём
- Степень огнестойкости, классы пожарной опасности (функц. и констр.)
- ТУ: электро-, водо-, канализация, тепло-, газо-, связь

Список полей и регулярки редактируются в [ird_extract/fields.py](ird_extract/fields.py) —
под специфический формат ваших ИРД.
