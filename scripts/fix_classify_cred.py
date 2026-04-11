"""Add placeholder for Anthropic credential and upload."""
import json

with open('../n8n_workflows/final_payload.json', encoding='utf-8') as f:
    w = json.load(f)

# The Classify node needs anthropicApi credential
# User must create it in n8n Settings -> Credentials -> Anthropic API
for n in w['nodes']:
    if n['name'] == 'Classify':
        # Set credential reference - user will need to select it in n8n UI
        n['credentials'] = {
            'anthropicApi': {
                'id': 'CREATE_IN_N8N',
                'name': 'Anthropic API'
            }
        }
        print(f'Set Classify credential placeholder')

with open('../n8n_workflows/final_payload.json', 'w', encoding='utf-8') as f:
    json.dump(w, f, ensure_ascii=False)
print('Saved')
