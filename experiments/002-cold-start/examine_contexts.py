import json, os, sys

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    print(f'\n{"="*70}')
    print(f'TICKER: {ticker}')
    print(f'{"="*70}')

    # Basic metadata
    print(f'\n[1] METADATA')
    print(f'  schema: {ctx["context_schema_version"]}')
    print(f'  context_id: {ctx["context_id"]}')
    print(f'  as_of: {ctx["as_of"]}')
    print(f'  generated_at: {ctx["generated_at"]}')
    print(f'  knowledge_cutoff: {ctx["knowledge_cutoff"]}')
    asset = ctx.get('asset', {})
    print(f'  ticker: {asset.get("ticker")}')
    print(f'  company_name: {asset.get("company_name")}')
    print(f'  exchange: {asset.get("exchange")}')
    print(f'  currency: {asset.get("currency")}')
    print(f'  identifiers: {asset.get("identifiers")}')

    # Provenance structure
    prov = ctx.get('provenance', {})
    refs = prov.get('refs', {})
    derivations = prov.get('derivations', {})
    registry = prov.get('operation_registry', {})

    ref_kinds = {}
    for k, v in refs.items():
        k2 = v.get('kind', 'unknown')
        ref_kinds[k2] = ref_kinds.get(k2, 0) + 1
    print(f'\n  provenance.refs: {len(refs)} total')
    print(f'  ref kinds: {ref_kinds}')
    print(f'  provenance.derivations: {len(derivations)}')
    print(f'  operation_registry entries: {len(registry)}')

    # Observed figures
    print(f'\n[2] OBSERVED')
    observed = ctx.get('observed', {})
    for metric in sorted(observed.keys()):
        entries = observed[metric]
        print(f'  {metric}:')
        for entry in entries:
            fig = entry.get('figure', {})
            prov_kind = fig.get('provenance_kind', '')
            if prov_kind == 'OBSERVED':
                print(f'    [{entry["provider"]}] value={fig.get("value")}, '
                      f'unit={fig.get("unit")}, currency={fig.get("currency")}, '
                      f'currency_basis={fig.get("currency_basis")}, '
                      f'period={fig.get("period_start")}..{fig.get("period_end")}, '
                      f'as_of={fig.get("as_of")}, available_at={fig.get("available_at")}, '
                      f'available_at_basis={fig.get("available_at_basis")}, '
                      f'ref={fig.get("ref")}')
            else:
                print(f'    [{entry["provider"]}] UNAVAILABLE, ref={fig.get("ref")}, '
                      f'reason_kind={fig.get("reason_kind", entry.get("reason_kind"))}')
            # Show raw if present
            raw = fig.get('raw')
            if raw is not None:
                if isinstance(raw, dict) and 'samples' in raw:
                    print(f'      raw samples count: {raw.get("samples_count", len(raw.get("samples", [])))}')
                elif isinstance(raw, dict) and 'prices' in raw:
                    print(f'      raw prices count: {len(raw.get("prices", []))}')
                else:
                    print(f'      raw keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}')

    # Validated evidence
    print(f'\n[3] VALIDATED EVIDENCE')
    validated = ctx.get('validated_evidence', {})
    for metric in sorted(validated.keys()):
        v = validated[metric]
        print(f'  {metric}:')
        print(f'    status: {v.get("status")}')
        print(f'    comparable: {v.get("comparable")}')
        print(f'    vendor_ref: {v.get("vendor_ref")}')
        print(f'    filing_ref: {v.get("filing_ref")}')
        tb = v.get('tolerance', {})
        print(f'    tolerance: relative={tb.get("relative")}, absolute={tb.get("absolute")}, '
              f'rule={tb.get("rule")}')
        print(f'    explanation: {v.get("explanation", "")[:300]}')
        # Show comparison_basis if present
        cb = v.get('comparison_basis', {})
        if cb:
            print(f'    comparison_basis: {json.dumps(cb, ensure_ascii=False)}')
        # Show references if present
        refs_list = v.get('references', [])
        if refs_list:
            print(f'    references: {refs_list}')

    # Derived figures with full traceability
    print(f'\n[4] DERIVED (with full traceability)')
    derived = ctx.get('derived', {})
    for fig_name in sorted(derived.keys()):
        entry = derived[fig_name]
        fig = entry.get('figure', {})
        val = fig.get('value', 'N/A')
        pk = fig.get('provenance_kind', 'N/A')
        ref = fig.get('ref', 'N/A')
        flags = fig.get('state_flags', [])

        # Get derivation record
        der_ref = entry.get('derivation_ref', '')
        trc = derivations.get(der_ref, {})

        print(f'  {fig_name}:')
        print(f'    value={val}, provenance_kind={pk}, ref={ref}')
        print(f'    state_flags={flags}')
        if trc:
            op = trc.get('operation', {})
            print(f'    operation: op={op.get("op")}, version={op.get("version")}, '
                  f'operands={op.get("operands")}')
            print(f'    expression: {trc.get("expression")}')
            print(f'    deterministic: {trc.get("deterministic")}')
            print(f'    depends_on: {trc.get("depends_on")}')
            print(f'    inputs_observed_at: {trc.get("inputs_observed_at")}')
            print(f'    conditional_on: {trc.get("conditional_on")}')

            # Trace operands to their values
            print(f'    --- operand trace ---')
            for operand_ref in op.get('operands', []):
                operand_obj = refs.get(operand_ref, {})
                operand_kind = operand_obj.get('kind', 'unknown')
                if operand_kind in ('obs', 'ev'):
                    print(f'      {operand_ref} ({operand_kind}): '
                          f'value={operand_obj.get("value")}, metric={operand_obj.get("metric")}, '
                          f'currency={operand_obj.get("currency")}, period={operand_obj.get("period_start")}..'
                          f'{operand_obj.get("period_end")}, as_of={operand_obj.get("as_of")}, '
                          f'provider={operand_obj.get("provider")}')
                elif operand_kind == 'refc':
                    print(f'      {operand_ref} (refc): value={operand_obj.get("value")}, '
                          f'basis={operand_obj.get("basis")}, multiple={operand_obj.get("multiple")}')
                else:
                    print(f'      {operand_ref} ({operand_kind}): {operand_obj}')
        else:
            print(f'    WARNING: no derivation record found for ref={der_ref}')

    # Valuation reference
    print(f'\n[5] VALUATION REFERENCE')
    vr = ctx.get('valuation_reference', {})
    print(f'  {json.dumps(vr, indent=2, ensure_ascii=False)}')

    # Market implied
    print(f'\n[6] MARKET IMPLIED')
    mi = ctx.get('market_implied', {})
    print(f'  conditional_statement: {mi.get("conditional_statement")}')
    print(f'  min_observations_for_reference: {mi.get("min_observations_for_reference")}')
    for fig_name, fig_data in mi.get('figures', {}).items():
        print(f'  {fig_name}: value={fig_data.get("value")}, '
              f'provenance={fig_data.get("provenance_kind")}, ref={fig_data.get("ref")}')

    # Data quality
    print(f'\n[7] DATA QUALITY')
    dq = ctx.get('data_quality', {})
    print(f'  evidence_coverage: {dq.get("evidence_coverage")}')
    print(f'  cross_source: {dq.get("cross_source")}')
    print(f'  acquisition_errors: {dq.get("acquisition_errors")}')
    print(f'  consensus_forward_eps_period: {dq.get("consensus_forward_eps_period")}')
    print(f'  band_eligibility: {dq.get("band_eligibility")}')
    print(f'  identity_conflicts: {dq.get("identity_conflicts")}')
    freshness = dq.get('freshness', {})
    print(f'  freshness.checked: {freshness.get("checked")}')
    print(f'  freshness.aged_observations: {freshness.get("aged_observations")}')
    print(f'  freshness.stale_metrics: {freshness.get("stale_metrics")}')
    print(f'  freshness.no_recent_value_for: {freshness.get("no_recent_value_for")}')

    # Unavailable
    print(f'\n[8] UNAVAILABLE ({len(ctx.get("unavailable", []))} items)')
    for item in ctx.get('unavailable', []):
        print(f'  {item.get("item")}: reason_kind={item.get("reason_kind")}, '
              f'reason_code={item.get("reason_code")}, blocks={item.get("blocks")}')

    # Series / discontinuities
    print(f'\n[9] SERIES & DISCONTINUITIES')
    series = dq.get('series', {})
    if series:
        for metric, sdata in series.items():
            dics = sdata.get('discontinuities', [])
            sp = sdata.get('same_period_pairs', [])
            print(f'  {metric}: series_status={sdata.get("series_status")}, '
                  f'reason={sdata.get("series_status_reason")}, '
                  f'observations={sdata.get("observations")}, '
                  f'groups={list(sdata.get("bases", {}).keys())}')
            for d in dics:
                print(f'    discontinuity: {d.get("from_period")} -> {d.get("to_period")}, '
                      f'change={d.get("relative_change")}, '
                      f'group={d.get("series_group")}, '
                      f'explanation={d.get("explanation")}')
            for p in sp:
                print(f'    same_period_pair: {p.get("period_end")}, '
                      f'change={p.get("relative_difference")}, '
                      f'relationship={p.get("relationship")}, '
                      f'explanation={p.get("explanation")}')
    else:
        print('  No series data found in data_quality')

    # Limitations
    print(f'\n[10] LIMITATIONS ({len(ctx.get("limitations", []))} items)')
    for lim in ctx.get('limitations', []):
        if isinstance(lim, str):
            print(f'  {lim}')
        else:
            print(f'  {lim}')

print('\n\nDone.')
