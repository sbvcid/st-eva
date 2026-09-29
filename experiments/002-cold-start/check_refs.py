import json

ctx = json.load(open('experiments/002-cold-start/contexts/AAPL.context.json'))
refs = ctx['provenance']['refs']

kinds_seen = set()
for ref_id, ref_obj in refs.items():
    kind = ref_obj.get('kind', 'unknown')
    if kind not in kinds_seen:
        kinds_seen.add(kind)
        print(f'Kind: {kind}, sample ref: {ref_id}')
        print(f'  keys: {list(ref_obj.keys())}')
        data = {k: v for k, v in ref_obj.items() if k != 'raw'}
        print(f'  data: {json.dumps(data, ensure_ascii=False, default=str)[:500]}')
        print()

reg = ctx['provenance'].get('operation_registry', {})
print(f'Operation registry type: {type(reg).__name__}')
print(f'Keys: {list(reg.keys())}')
for k in list(reg.keys()):
    v = reg[k]
    print(f'{k}: type={type(v).__name__}, value={json.dumps(v, ensure_ascii=False, default=str)[:300]}')
