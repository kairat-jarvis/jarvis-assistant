"""
Fix: Replace Switch node with Code node multiple outputs.
Switch v3 routes everything to output 0. Code node is more reliable.
"""
import json

with open('../n8n_workflows/live_wf.json', encoding='utf-8') as f:
    w = json.load(f)

# 1. Remove Switch node
w['nodes'] = [n for n in w['nodes'] if n['name'] != 'Switch']
print('Removed Switch node')

# 2. Update Router to have 4 outputs instead of 1
for n in w['nodes']:
    if n['name'] == 'Router':
        # Rewrite code to use multiple outputs
        n['parameters']['jsCode'] = """// =================================================================
// JARVIS Router — 4 outputs: [Command, Status, Ideas, Classify]
// =================================================================

const update = $input.first().json;
const message = update.message || update;
const text = message?.text || message?.message?.text || '';

if (!text) return [[], [], [], []];

const userMessage = text.trim();
const chatId = String(
  message?.chat?.id || message?.message?.chat?.id ||
  message?.from?.id || message?.message?.from?.id || ''
);
const userId = String(message?.from?.id || message?.message?.from?.id || '');
const username = message?.from?.username || message?.from?.first_name ||
  message?.message?.from?.username || message?.message?.from?.first_name || 'Unknown';

if (!chatId) return [[], [], [], []];

// Output 0: Commands (/start, /help)
if (userMessage === '/start') {
  return [[{
    json: {
      chatId,
      text: '\\u{1F916} *JARVIS \\u0430\\u043a\\u0442\\u0438\\u0432\\u0438\\u0440\\u043e\\u0432\\u0430\\u043d*\\n\\n' +
        '\\u042f \\u0432\\u0430\\u0448 \\u043f\\u0435\\u0440\\u0441\\u043e\\u043d\\u0430\\u043b\\u044c\\u043d\\u044b\\u0439 AI-\\u043e\\u0440\\u043a\\u0435\\u0441\\u0442\\u0440\\u0430\\u0442\\u043e\\u0440. \\u041f\\u0440\\u043e\\u0441\\u0442\\u043e \\u0433\\u043e\\u0432\\u043e\\u0440\\u0438\\u0442\\u0435 \\u2014 \\u044f \\u043f\\u043e\\u0439\\u043c\\u0443 \\u0447\\u0442\\u043e \\u0434\\u0435\\u043b\\u0430\\u0442\\u044c.\\n\\n' +
        '*\\u0427\\u0442\\u043e \\u044f \\u0443\\u043c\\u0435\\u044e:*\\n' +
        '\\u{1F4A1} \\u041f\\u0440\\u0438\\u043d\\u0438\\u043c\\u0430\\u0442\\u044c \\u0438\\u0434\\u0435\\u0438 \\u0438 \\u043e\\u0446\\u0435\\u043d\\u0438\\u0432\\u0430\\u0442\\u044c \\u0438\\u0445\\n' +
        '\\u{1F4DD} \\u0421\\u043e\\u0445\\u0440\\u0430\\u043d\\u044f\\u0442\\u044c \\u0437\\u0430\\u043c\\u0435\\u0442\\u043a\\u0438 \\u0438 \\u0440\\u0435\\u0448\\u0435\\u043d\\u0438\\u044f\\n' +
        '\\u{1F50D} \\u041e\\u0442\\u0432\\u0435\\u0447\\u0430\\u0442\\u044c \\u043d\\u0430 \\u0432\\u043e\\u043f\\u0440\\u043e\\u0441\\u044b \\u0438\\u0437 \\u0431\\u0430\\u0437\\u044b \\u0437\\u043d\\u0430\\u043d\\u0438\\u0439\\n' +
        '\\u{1F4CB} \\u041f\\u0440\\u0438\\u043d\\u0438\\u043c\\u0430\\u0442\\u044c \\u0437\\u0430\\u0434\\u0430\\u0447\\u0438\\n\\n' +
        '*\\u041a\\u043e\\u043c\\u0430\\u043d\\u0434\\u044b:*\\n' +
        '/status \\u2014 \\u0441\\u0442\\u0430\\u0442\\u0438\\u0441\\u0442\\u0438\\u043a\\u0430 \\u043f\\u0430\\u043c\\u044f\\u0442\\u0438\\n' +
        '/ideas \\u2014 \\u0441\\u043f\\u0438\\u0441\\u043e\\u043a \\u0438\\u0434\\u0435\\u0439\\n' +
        '/help \\u2014 \\u0441\\u043f\\u0440\\u0430\\u0432\\u043a\\u0430\\n\\n' +
        '\\u041f\\u0440\\u043e\\u0441\\u0442\\u043e \\u043d\\u0430\\u043f\\u0438\\u0448\\u0438\\u0442\\u0435 \\u0447\\u0442\\u043e \\u0443\\u0433\\u043e\\u0434\\u043d\\u043e!'
    }
  }], [], [], []];
}

if (userMessage === '/help') {
  return [[{
    json: {
      chatId,
      text: '\\u{1F4D6} *JARVIS \\u2014 \\u0421\\u043f\\u0440\\u0430\\u0432\\u043a\\u0430*\\n\\n' +
        '*\\u0422\\u0438\\u043f\\u044b \\u0441\\u043e\\u043e\\u0431\\u0449\\u0435\\u043d\\u0438\\u0439:*\\n' +
        '\\u{1F4A1} IDEA \\u2014 \\u0438\\u0434\\u0435\\u0438\\n' +
        '\\u{1F4DD} NOTE \\u2014 \\u0437\\u0430\\u043c\\u0435\\u0442\\u043a\\u0438\\n' +
        '\\u{1F50D} QUERY \\u2014 \\u0432\\u043e\\u043f\\u0440\\u043e\\u0441\\u044b\\n' +
        '\\u{1F4CB} TASK \\u2014 \\u0437\\u0430\\u0434\\u0430\\u0447\\u0438\\n\\n' +
        '/status /ideas /help'
    }
  }], [], [], []];
}

// Output 1: Status
if (userMessage === '/status') {
  return [[], [{json: {chatId}}], [], []];
}

// Output 2: Ideas
if (userMessage === '/ideas') {
  return [[], [], [{json: {chatId}}], []];
}

// Output 3: Classify (default for all other messages)
return [[], [], [], [{
  json: {
    userMessage,
    userId,
    username,
    chatId
  }
}]];"""
        print('Updated Router with 4 outputs')

# 3. Update connections: Router directly connects to all targets (no Switch)
w['connections']['Router'] = {
    'main': [
        [{'node': 'Send Command', 'type': 'main', 'index': 0}],
        [{'node': 'Status Prep', 'type': 'main', 'index': 0}],
        [{'node': 'Ideas Prep', 'type': 'main', 'index': 0}],
        [{'node': 'Classify', 'type': 'main', 'index': 0}]
    ]
}

# Remove Switch from connections
if 'Switch' in w['connections']:
    del w['connections']['Switch']

print('Updated connections: Router -> [Send Command, Status Prep, Ideas Prep, Classify]')

# 4. Verify Classify node has Anthropic credential
for n in w['nodes']:
    if n['name'] == 'Classify':
        creds = n.get('credentials', {})
        print(f'Classify credentials: {creds}')
        # Fix jsonBody to use $json from Router output
        body = n['parameters'].get('jsonBody', '')
        if '$json.userMessage' in body:
            print('Classify jsonBody OK - references $json.userMessage')
        else:
            print(f'WARNING: Classify jsonBody may need fix: {body[:100]}')

# Save as update payload
payload = {
    'name': w['name'],
    'nodes': w['nodes'],
    'connections': w['connections'],
    'settings': {'executionOrder': 'v1'}
}

with open('../n8n_workflows/final_payload.json', 'w', encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False)

print('\nDone! Ready to upload.')
