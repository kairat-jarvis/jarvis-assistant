"""
Fix Router to use single output + IF node (proven RAG-Consultant pattern).
Commands (/start, /help) return text → send directly.
Everything else → Classify pipeline.
"""
import json

with open('../n8n_workflows/live_wf.json', encoding='utf-8') as f:
    w = json.load(f)

# Remove Switch, Status Prep, Get Stats, Format Stats, Send Stats,
# Ideas Prep, Get Ideas, Format Ideas, Send Ideas
remove_nodes = [
    'Switch', 'Status Prep', 'Get Stats', 'Format Stats', 'Send Stats',
    'Ideas Prep', 'Get Ideas', 'Format Ideas', 'Send Ideas'
]
w['nodes'] = [n for n in w['nodes'] if n['name'] not in remove_nodes]
print(f'Removed {len(remove_nodes)} nodes')

# Update Router - single output, commands return text, rest goes to classify
for n in w['nodes']:
    if n['name'] == 'Router':
        n['parameters']['jsCode'] = """// =================================================================
// JARVIS Router — single output
// Commands: return {hasText: true, text, chatId}
// Messages: return {hasText: false, userMessage, chatId, ...}
// =================================================================

const update = $input.first().json;
const message = update.message || update;
const text = message?.text || message?.message?.text || '';

if (!text) return [];

const userMessage = text.trim();
const chatId = String(
  message?.chat?.id || message?.message?.chat?.id ||
  message?.from?.id || message?.message?.from?.id || ''
);
const userId = String(message?.from?.id || message?.message?.from?.id || '');
const username = message?.from?.username || message?.from?.first_name ||
  message?.message?.from?.username || message?.message?.from?.first_name || 'Unknown';

if (!chatId) return [];

// === Commands — return ready text ===
if (userMessage === '/start') {
  return [{
    json: {
      hasText: true,
      chatId,
      text: '\\u{1F916} *JARVIS \\u0430\\u043a\\u0442\\u0438\\u0432\\u0438\\u0440\\u043e\\u0432\\u0430\\u043d*\\n\\n' +
        '\\u042f \\u0432\\u0430\\u0448 \\u043f\\u0435\\u0440\\u0441\\u043e\\u043d\\u0430\\u043b\\u044c\\u043d\\u044b\\u0439 AI-\\u043e\\u0440\\u043a\\u0435\\u0441\\u0442\\u0440\\u0430\\u0442\\u043e\\u0440. \\u041f\\u0440\\u043e\\u0441\\u0442\\u043e \\u0433\\u043e\\u0432\\u043e\\u0440\\u0438\\u0442\\u0435 \\u2014 \\u044f \\u043f\\u043e\\u0439\\u043c\\u0443 \\u0447\\u0442\\u043e \\u0434\\u0435\\u043b\\u0430\\u0442\\u044c.\\n\\n' +
        '*\\u0427\\u0442\\u043e \\u044f \\u0443\\u043c\\u0435\\u044e:*\\n' +
        '\\u{1F4A1} \\u041f\\u0440\\u0438\\u043d\\u0438\\u043c\\u0430\\u0442\\u044c \\u0438\\u0434\\u0435\\u0438 \\u0438 \\u043e\\u0446\\u0435\\u043d\\u0438\\u0432\\u0430\\u0442\\u044c\\n' +
        '\\u{1F4DD} \\u0421\\u043e\\u0445\\u0440\\u0430\\u043d\\u044f\\u0442\\u044c \\u0437\\u0430\\u043c\\u0435\\u0442\\u043a\\u0438\\n' +
        '\\u{1F50D} \\u041e\\u0442\\u0432\\u0435\\u0447\\u0430\\u0442\\u044c \\u043d\\u0430 \\u0432\\u043e\\u043f\\u0440\\u043e\\u0441\\u044b\\n' +
        '\\u{1F4CB} \\u041f\\u0440\\u0438\\u043d\\u0438\\u043c\\u0430\\u0442\\u044c \\u0437\\u0430\\u0434\\u0430\\u0447\\u0438\\n\\n' +
        '*\\u041a\\u043e\\u043c\\u0430\\u043d\\u0434\\u044b:* /help'
    }
  }];
}

if (userMessage === '/help') {
  return [{
    json: {
      hasText: true,
      chatId,
      text: '\\u{1F4D6} *JARVIS \\u2014 \\u0421\\u043f\\u0440\\u0430\\u0432\\u043a\\u0430*\\n\\n' +
        '*\\u0422\\u0438\\u043f\\u044b (\\u043e\\u043f\\u0440\\u0435\\u0434\\u0435\\u043b\\u044f\\u044e \\u0430\\u0432\\u0442\\u043e\\u043c\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438):*\\n' +
        '\\u{1F4A1} IDEA \\u2014 \\u0438\\u0434\\u0435\\u0438 (\\u043e\\u0446\\u0435\\u043d\\u0438\\u0432\\u0430\\u044e)\\n' +
        '\\u{1F4DD} NOTE \\u2014 \\u0437\\u0430\\u043c\\u0435\\u0442\\u043a\\u0438\\n' +
        '\\u{1F50D} QUERY \\u2014 \\u0432\\u043e\\u043f\\u0440\\u043e\\u0441\\u044b\\n' +
        '\\u{1F4CB} TASK \\u2014 \\u0437\\u0430\\u0434\\u0430\\u0447\\u0438\\n\\n' +
        '\\u041f\\u0440\\u043e\\u0441\\u0442\\u043e \\u043d\\u0430\\u043f\\u0438\\u0448\\u0438\\u0442\\u0435 \\u0447\\u0442\\u043e \\u0443\\u0433\\u043e\\u0434\\u043d\\u043e!'
    }
  }];
}

// === Everything else — to classify ===
return [{
  json: {
    hasText: false,
    userMessage,
    userId,
    username,
    chatId
  }
}];"""
        print('Updated Router code')

# Add IF node: hasText === true?
if_node = {
    'parameters': {
        'conditions': {
            'boolean': [
                {
                    'value1': '={{ $json.hasText }}',
                    'value2': True
                }
            ]
        }
    },
    'id': 'jarvis-if-route',
    'name': 'IF Command',
    'type': 'n8n-nodes-base.if',
    'typeVersion': 1,
    'position': [-512, 240]
}
w['nodes'].append(if_node)
print('Added IF Command node')

# Fix Send Command to use $json directly (IF passes data through)
for n in w['nodes']:
    if n['name'] == 'Send Command':
        n['parameters']['chatId'] = '={{ $json.chatId }}'
        n['parameters']['text'] = '={{ $json.text }}'
        print('Fixed Send Command expressions')

# Fix connections
w['connections'] = {
    'Telegram Trigger': {
        'main': [[{'node': 'Router', 'type': 'main', 'index': 0}]]
    },
    'Router': {
        'main': [[{'node': 'IF Command', 'type': 'main', 'index': 0}]]
    },
    'IF Command': {
        'main': [
            # TRUE (hasText) → Send Command
            [{'node': 'Send Command', 'type': 'main', 'index': 0}],
            # FALSE (no text) → Classify
            [{'node': 'Classify', 'type': 'main', 'index': 0}]
        ]
    },
    'Classify': {
        'main': [[{'node': 'Parse & Prepare', 'type': 'main', 'index': 0}]]
    },
    'Parse & Prepare': {
        'main': [[{'node': 'Embed', 'type': 'main', 'index': 0}]]
    },
    'Embed': {
        'main': [[{'node': 'Merge Data', 'type': 'main', 'index': 0}]]
    },
    'Merge Data': {
        'main': [[
            {'node': 'Send Result', 'type': 'main', 'index': 0},
            {'node': 'Save Memory', 'type': 'main', 'index': 0}
        ]]
    },
    'Save Memory': {
        'main': [[{'node': 'Log Action', 'type': 'main', 'index': 0}]]
    }
}
print('Updated all connections')

# Save
payload = {
    'name': w['name'],
    'nodes': w['nodes'],
    'connections': w['connections'],
    'settings': {'executionOrder': 'v1'}
}

with open('../n8n_workflows/final_payload.json', 'w', encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False)

print(f'\nFinal nodes: {[n["name"] for n in w["nodes"]]}')
print('Done!')
