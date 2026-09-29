import json, os

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

def get_ref_value(refs, ref_id):
    """Get the value of any ref, following derivations if needed."""
    obj = refs.get(ref_id, {})
    kind = obj.get('kind', 'unknown')
    if kind in ('obs', 'ev'):
        return obj.get('value'), obj.get('unit'), obj.get('currency'), obj.get('metric'), obj
    elif kind == 'der':
        # This is a derived figure's ref entry; look at the ref's value
        return obj.get('value'), obj.get('unit'), obj.get('currency'), obj.get('metric'), obj
    elif kind == 'refc':
        return obj.get('value'), obj.get('unit'), obj.get('currency'), obj.get('metric'), obj
    else:
        return obj.get('value'), obj.get('unit'), obj.get('currency'), obj.get('metric'), obj

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    print(f'\n{"#"*70}')
    print(f'# TICKER: {ticker}')
    print(f'{"#"*70}')

    prov = ctx.get('provenance', {})
    refs = prov.get('refs', {})
    derivations = prov.get('derivations', {})

    # Show ALL ref kinds
    ref_kinds = {}
    for k, v in refs.items():
        k2 = v.get('kind', 'unknown')
        ref_kinds[k2] = ref_kinds.get(k2, 0) + 1
    print(f'\nRef counts by kind: {ref_kinds}')

    # Show observation refs in detail
    obs_refs = {k: v for k, v in refs.items() if v.get('kind') == 'observation'}
    print(f'\nObservation refs ({len(obs_refs)}):')
    for ref_id in sorted(obs_refs.keys()):
        r = obs_refs[ref_id]
        metric = r.get('metric', 'N/A')
        value = r.get('value', 'N/A')
        unit = r.get('unit', 'N/A')
        curr = r.get('currency', 'N/A')
        curr_basis = r.get('currency_basis', 'N/A')
        ps = r.get('period_start', 'N/A')
        pe = r.get('period_end', 'N/A')
        as_of = r.get('as_of', 'N/A')
        avail = r.get('available_at', 'N/A')
        avail_basis = r.get('available_at_basis', 'N/A')
        prov_name = r.get('provider', 'N/A')
        src_type = r.get('source_type', 'N/A')
        method = r.get('methodology', 'N/A')[:80]
        status = r.get('status', 'N/A')
        # Truncate value if it's a dict (band)
        if isinstance(value, dict):
            value_str = json.dumps(value, ensure_ascii=False)[:120]
        else:
            value_str = str(value)
        print(f'  {ref_id}: metric={metric}, value={value_str}, unit={unit}, '
              f'curr={curr}, curr_basis={curr_basis}')
        print(f'    period={ps}..{pe}, as_of={as_of}, available_at={avail}, '
              f'avail_basis={avail_basis}')
        print(f'    provider={prov_name}, source_type={src_type}, status={status}')

    # Show refc refs (reference nodes)
    refc_refs = {k: v for k, v in refs.items() if v.get('kind') == 'refc'}
    print(f'\nReference refs ({len(refc_refs)}):')
    for ref_id in sorted(refc_refs.keys()):
        r = refc_refs[ref_id]
        metric = r.get('metric', 'N/A')
        value = r.get('value', 'N/A')
        basis = r.get('basis', 'N/A')
        src_ref = r.get('source_ref', 'N/A')
        obs_count = r.get('source_observation_count', 'N/A')
        eligible = r.get('eligible_as_reference', 'N/A')
        print(f'  {ref_id}: metric={metric}, value={value}, basis={basis}, '
              f'source_ref={src_ref}, obs_count={obs_count}, eligible={eligible}')

    # Show der refs
    der_refs = {k: v for k, v in refs.items() if v.get('kind') == 'der'}
    print(f'\nDerived refs ({len(der_refs)}):')
    for ref_id in sorted(der_refs.keys()):
        r = der_refs[ref_id]
        metric = r.get('metric', 'N/A')
        value = r.get('value', 'N/A')
        unit = r.get('unit', 'N/A')
        curr = r.get('currency', 'N/A')
        pk = r.get('provenance_kind', 'N/A')
        operand_field = r.get('operand_field', 'N/A')
        print(f'  {ref_id}: metric={metric}, value={value}, unit={unit}, '
              f'currency={curr}, provenance={pk}, operand_field={operand_field}')

    # Show evidence refs (ev)
    ev_refs = {k: v for k, v in refs.items() if v.get('kind') == 'ev'}
    print(f'\nEvidence refs ({len(ev_refs)}):')
    for ref_id in sorted(ev_refs.keys()):
        r = ev_refs[ref_id]
        obs = r.get('observation', 'N/A')
        print(f'  {ref_id}: observation={obs}, '
              f'validation_status={r.get("validation", {}).get("status", "N/A") if isinstance(r.get("validation"), dict) else r.get("validation_status", "N/A")}')

    # Show validation refs
    val_refs = {k: v for k, v in refs.items() if v.get('kind') == 'val'}
    print(f'\nValidation refs ({len(val_refs)}):')
    for ref_id in sorted(val_refs.keys()):
        r = val_refs[ref_id]
        subject = r.get('subject', 'N/A')
        status = r.get('status', 'N/A')
        ref_val = r.get('validation', {}).get('status', status) if isinstance(r.get('validation'), dict) else status
        print(f'  {ref_id}: subject={subject}, status={status}')

    # Operation registry
    registry = prov.get('operation_registry', {})
    print(f'\nOperation registry ({len(registry)} entries):')
    for op_id, op_def in registry.items():
        print(f'  {op_id}: version={op_def.get("version")}, '
              f'formula={op_def.get("formula", "")[:80]}, '
              f'output_unit={op_def.get("output_unit")}, '
              f'missing_value_rule={op_def.get("missing_value_rule")}')

print('\n\nDone.')
