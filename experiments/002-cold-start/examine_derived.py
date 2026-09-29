import json, os

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    print(f'\n{"="*60}')
    print(f'{ticker} — DERIVED figures with operands + cross_source per-metric')
    print(f'{"="*60}')

    prov = ctx['provenance']

    # Print derivations
    derivations = prov.get('derivations', {})
    print(f'\n--- provenance.derivations ({len(derivations)} entries) ---')
    for der_ref, der_obj in derivations.items():
        print(f'  {der_ref}:')
        print(f'    operation: {der_obj.get("operation")}')
        print(f'    operands: {der_obj.get("operands")}')
        print(f'    expression: {der_obj.get("expression")}')
        print(f'    deterministic: {der_obj.get("deterministic")}')
        print(f'    conditional_on: {der_obj.get("conditional_on")}')

    # Now map each observed metric to its cross_source verdict
    print(f'\n--- cross_source verdict per metric with dual providers ---')
    obs = ctx.get('observed', {})
    for metric_name, sources in obs.items():
        if len(sources) < 2:
            continue  # only single-source, no cross-verification
        # Get the latest values
        vals = []
        for s in sources:
            v = s.get('figure', {}).get('value')
            vals.append((s.get('provider'), s.get('figure', {}).get('ref'), v))
        
        # Try to figure out the verdict by looking at values
        # Check the operation_registry or the derived data
        print(f'  {metric_name}:')
        for prov_name, ref, val in vals:
            val_str = json.dumps(val, ensure_ascii=False) if not isinstance(val, float) else f'{val:.4f}'
            print(f'    {prov_name}: ref={ref}, value={val_str}')

    # Also print the operation_registry
    op_reg = prov.get('operation_registry', {})
    print(f'\n--- provenance.operation_registry ({len(op_reg)} entries) ---')
    for op_name, op_obj in op_reg.items():
        print(f'  {op_name}: {json.dumps(op_obj, ensure_ascii=False)[:300]}')

print('\nDone.')
