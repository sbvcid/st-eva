import json, subprocess, os, sys

tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']
output_dir = 'experiments/002-cold-start/contexts'
os.makedirs(output_dir, exist_ok=True)

for ticker in tickers:
    print(f'Generating context for {ticker}...', flush=True)
    result = subprocess.run(
        [sys.executable, 'st_eva_runner.py', ticker, '--mode', 'live',
         '--no-snapshot', '--context', '-', '--context-sources', 'yahoo', 'sec'],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f'  FAILED for {ticker}:')
        print(f'  stderr (first 1000): {result.stderr[:1000]}')
        print(f'  stdout (first 500): {result.stdout[:500]}')
    else:
        try:
            ctx = json.loads(result.stdout)
            path = os.path.join(output_dir, f'{ticker}.context.json')
            with open(path, 'w') as f:
                json.dump(ctx, f, ensure_ascii=False, indent=2)
            sv = ctx.get('context_schema_version')
            refs = len(ctx.get('provenance', {}).get('refs', {}))
            derived = len(ctx.get('derived', {}))
            print(f'  OK: schema={sv}, refs={refs}, derived={derived}')
        except json.JSONDecodeError as e:
            print(f'  JSON parse error for {ticker}: {e}')
            print(f'  stdout (first 500): {result.stdout[:500]}')
            print(f'  stderr (first 500): {result.stderr[:500]}')
