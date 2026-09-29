import json, os

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    print(f'\n{"="*60}')
    print(f'{ticker}')
    print(f'{"="*60}')

    dv = ctx.get('data_quality', {}).get('cross_source', {})
    print(f'\n--- cross_source verdicts ---')
    print(json.dumps(dv, ensure_ascii=False, indent=2))

    # Find valuations reference (valuation_reference)
    vr = ctx.get('valuation_reference', {})
    print(f'\n--- valuation_reference ---')
    print(json.dumps(vr, ensure_ascii=False, indent=2))

    # Series section
    series = ctx.get('series', {})
    print(f'\n--- series (keys) ---')
    if series:
        print(f'series keys: {list(series.keys())}')
        for k, v in series.items():
            print(f'  {k}: {json.dumps(v, ensure_ascii=False)[:300]}')
    else:
        print('  (empty)')

print('\nDone.')
