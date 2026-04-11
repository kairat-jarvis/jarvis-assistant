import json

with open('../n8n_workflows/final_payload.json', encoding='utf-8') as f:
    w = json.load(f)

# Fix Merge Data - restore $() and $json references
for n in w['nodes']:
    if n['name'] == 'Merge Data':
        n['parameters']['jsCode'] = (
            'const parsed = $("Parse & Prepare").first().json;\n'
            'const embeddingData = $json.data?.[0]?.embedding || [];\n'
            '\n'
            'return [{\n'
            '  json: {\n'
            '    ...parsed,\n'
            '    embedding: embeddingData\n'
            '  }\n'
            '}];'
        )
        print('Fixed Merge Data jsCode')

    # Fix Embed jsonBody - restore $json reference
    if n['name'] == 'Embed':
        n['parameters']['jsonBody'] = (
            '={"model": "text-embedding-3-small", '
            '"input": {{ JSON.stringify($json.content) }}, '
            '"dimensions": 1536}'
        )
        print('Fixed Embed jsonBody')

    # Fix Save Memory fields - restore $json references
    if n['name'] == 'Save Memory':
        for fv in n['parameters'].get('fieldsUi', {}).get('fieldValues', []):
            val = fv.get('fieldValue', '')
            if val.startswith('={{ ') and 'json' not in val:
                # broken reference, fix it
                pass
        # Rewrite all fields properly
        n['parameters']['fieldsUi']['fieldValues'] = [
            {'fieldId': 'content', 'fieldValue': '={{ $json.content }}'},
            {'fieldId': 'content_type', 'fieldValue': '={{ $json.content_type }}'},
            {'fieldId': 'summary', 'fieldValue': '={{ $json.summary }}'},
            {'fieldId': 'tags', 'fieldValue': '={{ JSON.stringify($json.tags) }}'},
            {'fieldId': 'embedding', 'fieldValue': '={{ JSON.stringify($json.embedding) }}'},
            {'fieldId': 'source', 'fieldValue': '={{ $json.source }}'},
            {'fieldId': 'priority', 'fieldValue': '={{ $json.priority }}'},
            {'fieldId': 'status', 'fieldValue': '={{ $json.status }}'},
            {'fieldId': 'metadata', 'fieldValue': '={{ JSON.stringify($json.metadata) }}'},
        ]
        print('Fixed Save Memory fields')

    # Fix Log Action fields
    if n['name'] == 'Log Action':
        n['parameters']['fieldsUi']['fieldValues'] = [
            {'fieldId': 'agent_id', 'fieldValue': 'classifier'},
            {'fieldId': 'action', 'fieldValue': 'classify_message'},
            {'fieldId': 'input_data', 'fieldValue': '={{ JSON.stringify({ message: $json.content }) }}'},
            {'fieldId': 'output_data', 'fieldValue': '={{ JSON.stringify({ type: $json.classType, summary: $json.summary }) }}'},
            {'fieldId': 'status', 'fieldValue': 'success'},
        ]
        print('Fixed Log Action fields')

# Find OpenAI credential from existing nodes or set placeholder
openai_cred_found = False
for n in w['nodes']:
    creds = n.get('credentials', {})
    if 'openAiApi' in creds and creds['openAiApi'].get('id') != 'REPLACE_WITH_OPENAI_CREDENTIALS_ID':
        openai_id = creds['openAiApi']
        # Apply to Embed node
        for n2 in w['nodes']:
            if n2['name'] == 'Embed':
                n2['credentials']['openAiApi'] = openai_id
                openai_cred_found = True
                print(f'Applied OpenAI cred: {openai_id}')
        break

if not openai_cred_found:
    print('WARNING: OpenAI credential not found - Embed node needs manual credential setup')

with open('../n8n_workflows/final_payload.json', 'w', encoding='utf-8') as f:
    json.dump(w, f, ensure_ascii=False)

print('\nDone! Payload saved.')
