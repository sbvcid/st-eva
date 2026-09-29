import json, os

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    prov = ctx['provenance']
    refs = prov['refs']
    derivations = prov['derivations']
    dq = ctx.get('data_quality', {})

    print(f'\n{"="*60}')
    print(f'TICKER: {ticker}')
    print(f'{"="*60}')

    # Metadata
    asset = ctx['asset']
    print(f'\n[Metadata]')
    print(f'  company_name: {asset.get("company_name")}')
    print(f'  exchange: {asset.get("exchange")}')
    print(f'  currency: {asset.get("currency")}')
    print(f'  cik: {asset.get("identifiers", {}).get("cik")}')
    print(f'  sec_entity_name: {asset.get("identifiers", {}).get("sec_entity_name")}')
    print(f'  schema: {ctx["context_schema_version"]}')
    print(f'  context_id: {ctx["context_id"]}')
    print(f'  as_of: {ctx["as_of"]}')
    print(f'  generated_at: {ctx["generated_at"]}')
    print(f'  knowledge_cutoff: {ctx["knowledge_cutoff"]}')

    # Observed - material figures
    print(f'\n[2] Observed material figures')
    observed = ctx.get('observed', {})
    # Material metrics: price, trailing_eps, forward_eps, consensus_forward_eps,
    # market_cap, enterprise_value, free_cash_flow, ebitda, revenue, pe_band,
    # ps_band, pfcf_band, ev_ebitda_band
    material = ['price', 'trailing_eps', 'forward_eps', 'consensus_forward_eps',
                'market_cap', 'enterprise_value', 'free_cash_flow', 'ebitda',
                'revenue', 'pe_band', 'ps_band', 'pfcf_band', 'ev_ebitda_band',
                'shares_outstanding', 'assets', 'cash', 'debt']
    for metric in material:
        if metric not in observed:
            continue
        entries = observed[metric]
        if not isinstance(entries, list):
            entries = [entries]
        for entry in entries:
            fig = entry.get('figure', {})
            pk = fig.get('provenance_kind', 'UNKNOWN')
            prov_name = entry.get('provider', '')
            if pk == 'OBSERVED':
                val = fig.get('value')
                if isinstance(val, dict):
                    val_str = json.dumps(val, ensure_ascii=False)
                else:
                    val_str = str(val)
                print(f'  {metric} [{prov_name}]: value={val_str}, '
                      f'unit={fig.get("unit")}, currency={fig.get("currency")}, '
                      f'curr_basis={fig.get("currency_basis")}, '
                      f'period={fig.get("period_start")}..{fig.get("period_end")}, '
                      f'as_of={fig.get("as_of")}, '
                      f'avail_at={fig.get("available_at")}, '
                      f'avail_basis={fig.get("available_at_basis")}, '
                      f'ref={fig.get("ref")}')
            else:
                print(f'  {metric} [{prov_name}]: {pk}, ref={fig.get("ref")}')

    # Cross-source validation verdicts
    print(f'\n[3] Cross-source validation')
    for metric, v in sorted(ctx.get('validated_evidence', {}).items()):
        print(f'  {metric}: status={v.get("status")}, comparable={v.get("comparable")}, '
              f'vendor={v.get("vendor_ref")}, filing={v.get("filing_ref")}')

    # Derived figures - key ones with value
    print(f'\n[4] Key derived figures (with value)')
    key_derived = ['current_pe', 'forward_pe', 'consensus_forward_pe',
                   'current_ps', 'current_pfcf', 'current_ev_ebitda',
                   'implied_forward_eps', 'required_eps_cagr',
                   'implied_fcf', 'implied_ebitda', 'implied_revenue',
                   'implied_shares', 'pe_percentile', 'ps_percentile',
                   'ev_ebitda_percentile', 'consensus_price_at_median',
                   'implied_net_margin']
    for fig_name in key_derived:
        if fig_name not in ctx.get('derived', {}):
            continue
        entry = ctx['derived'][fig_name]
        fig = entry.get('figure', {})
        val = fig.get('value', 'N/A')
        pk = fig.get('provenance_kind')
        der_ref = entry.get('derivation_ref', '')
        trc = derivations.get(der_ref, {})
        op = trc.get('operation', {})
        operands = op.get('operands', [])
        expr = trc.get('expression', '')
        flags = fig.get('state_flags', [])
        cond = trc.get('conditional_on', [])

        # Trace operands
        operands_trace = []
        for oref in operands:
            obj = refs.get(oref, {})
            ov = obj.get('value', 'N/A')
            if isinstance(ov, dict):
                ov_str = json.dumps(ov, ensure_ascii=False)
            else:
                ov_str = str(ov)
            operands_trace.append(f'{oref}={ov_str}')

        flag_strs = []
        for f in flags:
            flag_strs.append(f"{f.get('flag')} -> {f.get('detail_ref')}" if f.get('detail_ref') else f.get('flag'))

        print(f'  {fig_name}: value={val}, kind={pk}')
        print(f'    op={op.get("op")}, operands=[{", ".join(operands)}]')
        print(f'    operands_trace: {", ".join(operands_trace)}')
        print(f'    expression: {expr}')
        print(f'    conditional_on: {cond}')
        print(f'    state_flags: {flag_strs}')

    # Valuation reference
    vr = ctx.get('valuation_reference', {})
    print(f'\n[5] Valuation reference')
    print(f'  basis: {vr.get("basis")}')
    print(f'  multiple: {vr.get("multiple")}')
    print(f'  source_ref: {vr.get("source_ref")}')
    print(f'  source_observation_count: {vr.get("source_observation_count")}')
    print(f'  eligible_as_reference: {vr.get("eligible_as_reference")}')
    print(f'  eligibility_reason: {vr.get("eligibility_reason")}')

    # Market implied
    mi = ctx.get('market_implied', {})
    print(f'\n[6] Market implied')
    print(f'  conditional_statement: {mi.get("conditional_statement")}')
    for fn, fd in mi.get('figures', {}).items():
        if isinstance(fd, dict):
            print(f'  {fn}: value={fd.get("value")}, kind={fd.get("provenance_kind")}')

    # Data quality
    ec = dq.get('evidence_coverage', {})
    print(f'\n[7] Data quality')
    print(f'  evidence_coverage: available={ec.get("available")}, unavailable={ec.get("unavailable")}, total={ec.get("total")}')
    print(f'  cross_source: {dq.get("cross_source")}')
    print(f'  band_eligibility: {dq.get("band_eligibility")}')
    print(f'  identity_conflicts: {len(dq.get("identity_conflicts", []))} items')
    for ic in dq.get('identity_conflicts', []):
        print(f'    {ic.get("check")}: status={ic.get("status")}, '
              f'derived={ic.get("derived_ref")}={ic.get("derived_value")}, '
              f'reported={ic.get("reported_ref")}={ic.get("reported_value")}, '
              f'diff={ic.get("relative_difference")}, '
              f'resolution={ic.get("resolution")}')
    fr = dq.get('freshness', {})
    print(f'  freshness: checked={fr.get("checked")}, aged={fr.get("aged_observations")}, '
          f'stale_metrics={fr.get("stale_metrics")}, no_recent_value_for={fr.get("no_recent_value_for")}')

    # Unavailable
    print(f'\n[8] Unavailable ({len(ctx.get("unavailable", []))} items)')
    for item in ctx.get('unavailable', []):
        print(f'  {item.get("item")}: kind={item.get("reason_kind")}, '
              f'code={item.get("reason_code")}, blocks={item.get("blocks")}')

    # Series
    series = dq.get('series', {})
    print(f'\n[9] Series & discontinuities')
    for metric, sdata in series.items():
        dics = sdata.get('discontinuities', [])
        sp = sdata.get('same_period_pairs', [])
        print(f'  {metric}: status={sdata.get("series_status")}, '
              f'reason={sdata.get("series_status_reason")}, '
              f'obs={sdata.get("observations")}, '
              f'groups={list(sdata.get("bases", {}).keys())}')
        for d in dics:
            print(f'    discontinuity: {d.get("from_period")} -> {d.get("to_period")}, '
                  f'change={d.get("relative_change")}, group={d.get("series_group")}, '
                  f'expl={d.get("explanation")}')
        for p in sp:
            print(f'    same_period: {p.get("period_end")}, '
                  f'diff={p.get("relative_difference")}, '
                  f'rel={p.get("relationship")}, expl={p.get("explanation")}')

    print()
