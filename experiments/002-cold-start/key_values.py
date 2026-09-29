import json, os

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

# Collect key data points for all tickers
print('SUMMARY TABLE ACROSS ALL TICKERS')
print('='*70)

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    prov = ctx['provenance']
    refs = prov['refs']
    derivations = prov['derivations']
    asset = ctx['asset']
    dq = ctx['data_quality']
    vr = ctx['valuation_reference']

    # Get observed material figures
    observed = ctx.get('observed', {})

    def get_obs_value(metric):
        """Get the primary vendor observation value for a metric."""
        entries = observed.get(metric, [])
        if not isinstance(entries, list):
            entries = [entries]
        for entry in entries:
            fig = entry.get('figure', {})
            if fig.get('provenance_kind') == 'OBSERVED':
                return fig.get('value'), fig.get('currency'), fig.get('ref')
        return 'N/A', 'N/A', 'N/A'

    def get_derived_value(fig_name):
        """Get a derived figure value and trace it."""
        entry = ctx.get('derived', {}).get(fig_name, {})
        fig = entry.get('figure', {})
        val = fig.get('value', 'N/A')
        pk = fig.get('provenance_kind', 'N/A')
        der_ref = entry.get('derivation_ref', '')
        trc = derivations.get(der_ref, {})
        op = trc.get('operation', {})
        operands = op.get('operands', [])
        # Trace operands
        operand_info = []
        for oref in operands:
            obj = refs.get(oref, {})
            operand_info.append(f'{oref}={obj.get("value", "N/A")}')
        flags = fig.get('state_flags', [])
        flag_str = ', '.join(f.get('flag', '') for f in flags)
        return val, pk, operand_info, flag_str

    def get_refc_info(refc_name):
        """Get reference node info."""
        ref_obj = refs.get(refc_name, {})
        return ref_obj.get('value'), ref_obj.get('basis'), ref_obj.get('eligible_as_reference')

    # Key observed values
    price_val, price_curr, price_ref = get_obs_value('price')
    cap_val, cap_curr, cap_ref = get_obs_value('market_cap')
    ev_val, ev_curr, ev_ref = get_obs_value('enterprise_value')
    trail_eps_val, trail_eps_curr, trail_eps_ref = get_obs_value('trailing_eps')
    fwd_eps_val, fwd_eps_curr, fwd_eps_ref = get_obs_value('forward_eps')
    cons_eps_val, cons_eps_curr, cons_eps_ref = get_obs_value('consensus_forward_eps')
    fcf_val, fcf_curr, fcf_ref = get_obs_value('free_cash_flow')
    ebitda_val, ebitda_curr, ebitda_ref = get_obs_value('ebitda')
    rev_val, rev_curr, rev_ref = get_obs_value('revenue')

    # PE band
    pe_band_entries = observed.get('pe_band', [])
    if pe_band_entries and isinstance(pe_band_entries, list):
        pe_band = pe_band_entries[0].get('figure', {}).get('value', {})
        pe_obs_count = pe_band.get('observations') if isinstance(pe_band, dict) else 'N/A'
        pe_median = pe_band.get('median') if isinstance(pe_band, dict) else 'N/A'
    else:
        pe_obs_count = 'N/A'
        pe_median = 'N/A'

    # Key derived
    curr_pe_val, curr_pe_kind, _, _ = get_derived_value('current_pe')
    fwd_pe_val, fwd_pe_kind, _, _ = get_derived_value('forward_pe')
    cons_pe_val, cons_pe_kind, _, _ = get_derived_value('consensus_forward_pe')
    curr_ps_val, curr_ps_kind, _, ps_flags = get_derived_value('current_ps')
    curr_pfcf_val, curr_pfcf_kind, _, pfcf_flags = get_derived_value('current_pfcf')
    curr_ev_ebitda_val, curr_ev_ebitda_kind, _, _ = get_derived_value('current_ev_ebitda')
    implied_shares_val, _, shares_operands, _ = get_derived_value('implied_shares')

    # Cross-source verdicts
    ve = ctx.get('validated_evidence', {})
    ve_summary = {m: v.get('status') for m, v in ve.items()}

    print(f'\n--- {ticker} ---')
    print(f'  company: {asset.get("company_name")}, exchange={asset.get("exchange")}, '
          f'currency={asset.get("currency")}')
    print(f'  as_of: {ctx["as_of"]}, generated_at: {ctx["generated_at"]}')
    print(f'  schema: {ctx["context_schema_version"]}, context_id: {ctx["context_id"]}')
    print(f'  refs: {len(refs)}, derived: {len(derivations)}')
    print(f'  price: {price_val} {price_curr} ({price_ref})')
    print(f'  market_cap: {cap_val} {cap_curr}')
    print(f'  enterprise_value: {ev_val} {ev_curr}')
    print(f'  trailing_eps: {trail_eps_val} {trail_eps_curr}')
    print(f'  forward_eps: {fwd_eps_val} {fwd_eps_curr}')
    print(f'  consensus_eps: {cons_eps_val} {cons_eps_curr}')
    print(f'  free_cash_flow: {fcf_val} {fcf_curr}')
    print(f'  ebitda: {ebitda_val} {ebitda_curr}')
    print(f'  revenue: {rev_val} {rev_curr}')
    print(f'  pe_band: median={pe_median}, obs={pe_obs_count}')
    print(f'  current_pe: {curr_pe_val} ({curr_pe_kind})')
    print(f'  forward_pe: {fwd_pe_val} ({fwd_pe_kind})')
    print(f'  consensus_pe: {cons_pe_val} ({cons_pe_kind})')
    print(f'  current_ps: {curr_ps_val} ({curr_ps_kind}), flags={ps_flags}')
    print(f'  current_pfcf: {curr_pfcf_val} ({curr_pfcf_kind}), flags={pfcf_flags}')
    print(f'  current_ev_ebitda: {curr_ev_ebitda_val} ({curr_ev_ebitda_kind})')
    print(f'  implied_shares: {implied_shares_val}, operands={shares_operands}')
    print(f'  valuation_ref: basis={vr.get("basis")}, multiple={vr.get("multiple")}, '
          f'obs_count={vr.get("source_observation_count")}, '
          f'eligible={vr.get("eligible_as_reference")}')
    print(f'  refc:pfcf_reference: {get_refc_info("refc:pfcf_reference")}')
    print(f'  refc:ev_ebitda_reference: {get_refc_info("refc:ev_ebitda_reference")}')
    print(f'  refc:ps_reference: {get_refc_info("refc:ps_reference")}')
    print(f'  cross_source verdicts: {ve_summary}')
    print(f'  evidence_coverage: {dq.get("evidence_coverage")}')
    print(f'  identity_conflicts: {len(dq.get("identity_conflicts", []))} items')
    print(f'  band_eligibility: {dq.get("band_eligibility")}')
    print(f'  freshness: stale={dq.get("freshness", {}).get("stale_metrics")}, '
          f'no_recent={dq.get("freshness", {}).get("no_recent_value_for")}')
    print(f'  unavailable: {len(ctx.get("unavailable", []))} items')
    for item in ctx.get('unavailable', []):
        print(f'    {item.get("item")}: kind={item.get("reason_kind")}, '
              f'code={item.get("reason_code")}, blocks={item.get("blocks")}')

    # Series status for key metrics
    series = dq.get('series', {})
    print(f'  series status:')
    for metric in ['price', 'revenue', 'market_cap', 'net_income', 'eps_diluted',
                   'assets', 'cash', 'debt', 'shares_outstanding', 'free_cash_flow', 'ebitda']:
        if metric in series:
            s = series[metric]
            dics = s.get('discontinuities', [])
            print(f'    {metric}: status={s.get("series_status")}, '
                  f'reason={s.get("series_status_reason")}, '
                  f'obs={s.get("observations")}, dics={len(dics)}')
            for d in dics:
                print(f'      dic: {d.get("from_period")} -> {d.get("to_period")}, '
                      f'change={d.get("relative_change"):.4f}, '
                      f'expl={d.get("explanation")}')

    # Limitations
    for lim in ctx.get('limitations', []):
        print(f'  limitation: {lim}')

print('\n\nDone.')
