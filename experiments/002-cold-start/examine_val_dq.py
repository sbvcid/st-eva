import json, os, sys

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    print(f'\n{"#"*70}')
    print(f'# {ticker} — validation, cross_source, valuations, data_quality')
    print(f'{"#"*70}')

    # validation
    val = ctx.get('validation', {})
    print(f'\n--- validation ---')
    print(json.dumps(val, ensure_ascii=False, indent=2))

    # valuations
    val_ref = ctx.get('valuations', {})
    print(f'\n--- valuations ---')
    print(json.dumps(val_ref, ensure_ascii=False, indent=2))

    # data_quality
    dq = ctx.get('data_quality', {})
    print(f'\n--- data_quality ---')
    print(json.dumps(dq, ensure_ascii=False, indent=2))

print('\nDone.')
