import json, os

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    print(f'\n{"="*60}')
    print(f'{ticker} — cross_source detail')
    print(f'{"="*60}')

    dv = ctx.get('data_quality', {}).get('cross_source', {})
    if isinstance(dv, dict):
        # If it has sub-keys like 'by_metric' or 'verdicts'
        for k, v in dv.items():
            if k == 'CONSISTENT' or k == 'METHODOLOGY_MISMATCH' or k == 'PERIOD_MISMATCH' or k == 'UNAVAILABLE':
                # It's a count dict
                continue
            print(f'  {k}: {json.dumps(v, ensure_ascii=False, indent=2)[:500]}')
        # Also print the count summary
        for verdict, count in dv.items():
            if isinstance(count, int):
                print(f'  VERDICT {verdict}: {count} metrics')

    # Now print what each metric in observed[] has as cross_source verdict
    print(f'\n  Per-metric observed cross-source verdicts:')
    obs = ctx.get('observed', {})
    for metric_name, sources in obs.items():
        verdicts = []
        cross_verdict = None
        for src in sources:
            cv = src.get('cross_source_verdict') or src.get('validation', {}).get('verdict') or src.get('verdict')
            if cv:
                verdicts.append(cv)
        # Check if there's a top-level cross_source verdict in data_quality
        print(f'  {metric_name}: {[s.get("provider") for s in sources]} → verdicts: {verdicts}')

    # Print the validated_evidence
    ve = ctx.get('data_quality', {}).get('validated_evidence', [])
    if ve:
        print(f'\n  validated_evidence:')
        for item in ve:
            print(f'    {json.dumps(item, ensure_ascii=False)[:300]}')

print('\nDone.')
