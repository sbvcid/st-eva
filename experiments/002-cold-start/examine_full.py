import json, os, sys

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    print(f'\n{"#"*70}')
    print(f'# {ticker} — FULL STRUCTURE: observed, derived, validation')
    print(f'{"#"*70}')

    # observed section
    obs = ctx.get('observed', {})
    print(f'\n--- observed (keys: {list(obs.keys())}) ---')
    for key, val in obs.items():
        if isinstance(val, dict):
            print(f'  {key}:')
            print(json.dumps(val, ensure_ascii=False, indent=2))
        else:
            print(f'  {key}: {val}')

    # derived section
    der = ctx.get('derived', {})
    print(f'\n--- derived (keys: {list(der.keys())}) ---')
    for key, val in der.items():
        if isinstance(val, dict):
            print(f'  {key}:')
            print(json.dumps(val, ensure_ascii=False, indent=2))
        else:
            print(f'  {key}: {val}')

    # validation section
    val = ctx.get('validation', {})
    print(f'\n--- validation (keys: {list(val.keys())}) ---')
    for key, v in val.items():
        if isinstance(v, (dict, list)):
            print(f'  {key}:')
            print(json.dumps(v, ensure_ascii=False, indent=2))
        else:
            print(f'  {key}: {v}')

print('\nDone.')
