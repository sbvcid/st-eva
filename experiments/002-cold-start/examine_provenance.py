import json, os

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

# Key material observation refs to trace
key_obs_refs = [
    'obs:ev-price-001',
    'obs:ev-current-eps-001',
    'obs:ev-forward-eps-001',
    'obs:ev-consensus-eps-001',
    'obs:ev-market-cap-001',
    'obs:ev-enterprise-value-001',
    'obs:ev-fcf-001',
    'obs:ev-ebitda-001',
    'obs:ev-revenue-001',
    'obs:ev-pe-band-001',
    'obs:ev-ps-band-001',
    'obs:ev-pfcf-band-001',
    'obs:ev-ev-ebitda-band-001',
    'obs:ev-metrics-001',
]

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    refs = ctx['provenance']['refs']

    print(f'\n{"="*60}')
    print(f'{ticker} - PROVENANCE REFS FOR KEY OBSERVATIONS')
    print(f'{"="*60}')

    for ref_id in key_obs_refs:
        ref_obj = refs.get(ref_id)
        if ref_obj is None:
            print(f'  {ref_id}: NOT FOUND IN PROVENANCE')
        else:
            print(f'  {ref_id}:')
            print(f'    kind: {ref_obj.get("kind")}')
            print(f'    observation_id: {ref_obj.get("observation_id")}')
            print(f'    metric: {ref_obj.get("metric")}')
            val = ref_obj.get("value")
            if isinstance(val, dict):
                print(f'    value: {json.dumps(val, ensure_ascii=False)[:200]}')
            else:
                print(f'    value: {val}')
            print(f'    unit: {ref_obj.get("unit")}')
            print(f'    currency: {ref_obj.get("currency")}')
            print(f'    currency_basis: {ref_obj.get("currency_basis")}')
            print(f'    basis: {ref_obj.get("basis")}')
            print(f'    period_start: {ref_obj.get("period_start")}')
            print(f'    period_end: {ref_obj.get("period_end")}')
            print(f'    as_of: {ref_obj.get("as_of")}')
            print(f'    available_at: {ref_obj.get("available_at")}')
            print(f'    available_at_basis: {ref_obj.get("available_at_basis")}')
            print(f'    provider: {ref_obj.get("provider")}')
            print(f'    source_type: {ref_obj.get("source_type")}')
            src_url = ref_obj.get("source_url", "") or ""
            print(f'    source_url: {src_url[:120]}')
            defn = ref_obj.get("definition", "") or ""
            print(f'    definition: {defn[:120]}')
            meth = ref_obj.get("methodology", "") or ""
            print(f'    methodology: {meth[:120]}')
            print(f'    retrieved_at: {ref_obj.get("retrieved_at")}')
            print(f'    observation_count: {ref_obj.get("observation_count")}')
            print(f'    status: {ref_obj.get("status")}')
            print(f'    status_reasons: {ref_obj.get("status_reasons")}')
            print(f'    raw_preserved: {ref_obj.get("raw_preserved")}')
            print(f'    inputs: {ref_obj.get("inputs")}')

    # Also show scope and glossary
    print(f'\n  SCOPE:')
    scope = ctx.get('scope', {})
    for prov in scope.get('provides', []):
        print(f'    provides: {prov}')
    for prov in scope.get('does_not_provide', []):
        print(f'    does_not_provide: {prov}')
    print(f'    authority_note: {scope.get("authority_note", "")[:200]}')

    print(f'\n  GLOSSARY keys: {list(ctx.get("glossary", {}).keys())[:10]}')

print('\n\nDone.')
