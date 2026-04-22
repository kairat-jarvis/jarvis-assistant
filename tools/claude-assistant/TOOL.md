# claude-assistant

## Назначение
Библиотека из 25+ инженерных скилов и промптов (узкоспециализированные агенты: проектировщик ВК, ОВ, ЭОМ, сметчик, ГИП, BIM-координатор и т.д.).

## Репозиторий
`github.com/kairat-jarvis/claude-assistant`

## MCP-серверы
- `google-drive` — чтение промптов из `AI/Claude Code/Claude Assistant/`
- `supabase` — сохранение результатов агентов в `jarvis_memory`

## Когда использовать
Триггеры: «как инженер-…», «спроектируй …», «посчитай …», «собери смету», «проверь раздел …», «делегируй агенту …», «нужен специалист по …».

## Интеграция с JARVIS
- **Читает промпты**: Google Drive → `Claude Assistant/skills/<name>.md`
- **Пишет в**: `jarvis_memory` (type='report', tag='<agent_name>')
- **Логирует в**: `jarvis_agent_logs` (action='agent_delegation', agent=<name>)

## Правила
- JARVIS — динамический делегатор: НЕ зашивать список агентов в системный промпт, каждый раз тянуть актуальный из Drive/GitHub.
- Перед делегированием сохранять контекст задачи в `jarvis_memory`.

## Статус
🟢 Production — 25+ агентов готовы, интегрировано через Google Drive MCP.
