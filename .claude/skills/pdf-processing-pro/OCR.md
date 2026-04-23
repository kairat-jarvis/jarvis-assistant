# PDF OCR — трёхуровневый waterfall

Стандарт извлечения текста из PDF в JARVIS. Фиксированный порядок уровней,
пропускать нельзя.

```
1. pdfplumber           (текстовый слой)
        ↓ если текста < MIN_TEXT_LEN
2. PaddleOCR-VL-1.5     (единственный OCR-движок)
        ↓ если avg_confidence < 0.6 ИЛИ текст пуст
3. Claude Vision        (fallback only)
```

## Почему именно так

- **pdfplumber** — мгновенный и точный для PDF с нативным текстовым слоем.
  Если есть — берём и не тратим ресурсы.
- **PaddleOCR-VL-1.5** — state-of-the-art VL-модель для документов (таблицы,
  чертежи, многоязычные сканы). В JARVIS это **единственный разрешённый OCR-движок**.
- **Claude Vision** — fallback для трудных случаев: рукопись, низкое
  качество сканирования, сложный layout. Стоит дороже остальных, поэтому
  вызывается только когда уровень 2 не справился.

## Запрещённые движки

Политикой проекта запрещены:
- Tesseract / pytesseract
- EasyOCR
- doctr
- Surya
- PaddleOCR < 1.5

Не добавляйте их в новый код даже как временное решение.

## Запрещённые сокращения

- **Пропуск уровней** — нельзя вызвать Claude Vision минуя PaddleOCR.
- **Claude Vision как OCR первого выбора** — только fallback.
- **Изменение порядка** per-document или per-page.

## Использование

```python
from ird_extract.ocr_waterfall import extract_pdf

text, results = extract_pdf("document.pdf")

for i, r in enumerate(results, 1):
    print(f"Page {i}: tier={r.tier} conf={r.confidence:.2f}")
    if r.fallback_reason:
        print(f"  → Claude Vision because: {r.fallback_reason}")
```

Также доступна обратно-совместимая обёртка:

```python
from ird_extract.extractor import extract_pdf_text
text = extract_pdf_text("document.pdf")
```

## Конфигурация (переменные окружения)

| Переменная              | По умолчанию       | Смысл                                             |
| ----------------------- | ------------------ | ------------------------------------------------- |
| `WATERFALL_MIN_TEXT_LEN`| `50`               | Минимум символов, чтобы считать страницу «не сканом» |
| `PADDLE_CONF_THRESHOLD` | `0.6`              | Порог avg-confidence для принятия результата L2   |
| `PADDLE_LANG`           | `ru`               | Язык модели PaddleOCR                             |
| `PADDLE_VL_MODEL`       | `PaddleOCR-VL-1.5` | Имя VL-модели                                     |
| `CLAUDE_VISION_MODEL`   | `claude-sonnet-4-6`| Модель для fallback                               |
| `ANTHROPIC_API_KEY`     | —                  | Требуется для уровня 3                            |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | —  | Для записи в `jarvis_agent_logs`                  |
| `POPPLER_PATH`          | —                  | Windows-путь к poppler (для pdf2image)            |

## Логирование эскалаций

Каждое срабатывание уровня 3 пишется в `jarvis_agent_logs` с полями:

```json
{
  "agent": "ocr_waterfall",
  "action": "claude_vision_fallback",
  "status": "fallback",
  "details": {
    "pdf": "contract_2026.pdf",
    "page": 7,
    "reason": "paddle_low_confidence(0.41<0.6)",
    "metrics": { "paddle_confidence": 0.41, "paddle_text_len": 120, ... },
    "tier": "claude-vision"
  }
}
```

Если Supabase недоступен — запись уходит в `waterfall_fallbacks.jsonl`
(путь переопределяется через `WATERFALL_LOG_PATH`). Эскалации не теряются
молча — это позволяет потом анализировать, на каких документах PaddleOCR
систематически не справляется, и улучшать предобработку.

## Установка

```bash
pip install 'paddleocr>=3.1' paddlepaddle numpy anthropic pdfplumber pdf2image pillow
```

Poppler (для `pdf2image`):
- **Windows**: скачать бинарник, добавить в PATH или задать `POPPLER_PATH`
- **macOS**: `brew install poppler`
- **Linux**: `apt-get install poppler-utils`

## Preprocessing

PaddleOCR-VL-1.5 имеет встроенные `use_doc_orientation_classify=True` и
`use_textline_orientation=True`, которые выправляют повёрнутые страницы
и строки. Дополнительный preprocessing (контраст, denoise) обычно
не нужен — модель обучалась на сырых сканах.

Если качество скана катастрофическое и PaddleOCR систематически уходит
в fallback → решать на уровне сканирования (DPI, освещение), а не
подмешивать Tesseract.

## Диагностика

- **Уровень 2 не вызывается** → проверьте `import paddleocr`. Если падает —
  установите `paddleocr>=3.1 paddlepaddle`.
- **Все страницы уходят в Claude Vision** → снизили `PADDLE_CONF_THRESHOLD`
  или плохой скан. Смотрите `metrics` в `jarvis_agent_logs`.
- **Пустые результаты** → вероятно, `pdf2image`/poppler не установлен.
