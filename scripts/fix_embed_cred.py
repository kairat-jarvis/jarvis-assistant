import json

with open('../n8n_workflows/final_payload.json', encoding='utf-8') as f:
    w = json.load(f)

for n in w['nodes']:
    if n['name'] == 'Embed':
        n['credentials'] = {
            'openAiApi': {
                'id': 'K9JiW8NJnEvUzMrg',
                'name': 'OpenAi account'
            }
        }
        print(f'Fixed Embed credentials: {n["credentials"]}')

with open('../n8n_workflows/final_payload.json', 'w', encoding='utf-8') as f:
    json.dump(w, f, ensure_ascii=False)
print('Saved')
