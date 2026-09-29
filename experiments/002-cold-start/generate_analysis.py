import json, os
from collections import OrderedDict

context_dir = 'experiments/002-cold-start/contexts'
tickers = ['AAPL', 'MSFT', 'MU', 'NVDA', 'TSM', 'NU']

results = OrderedDict()

for ticker in tickers:
    path = os.path.join(context_dir, f'{ticker}.context.json')
    with open(path) as f:
        ctx = json.load(f)

    prov = ctx['provenance']
    refs = prov['refs']
    derivations = prov['derivations']
    registry = prov['operation_registry']

    t_data = OrderedDict()
    t_data['metadata'] = {
        'ticker': ctx['asset'].get('ticker'),
        'company_name': ctx['asset'].get('company_name'),
        'exchange': ctx['asset'].get('exchange'),
        'currency': ctx['asset'].get('currency'),
        'cik': ctx['asset'].get('identifiers', {}).get('cik'),
        'sec_entity_name': ctx['asset'].get('identifiers', {}).get('sec_entity_name'),
        'schema_version': ctx['context_schema_version'],
        'context_id': ctx['context_id'],
        'as_of': ctx['as_of'],
        'generated_at': ctx['generated_at'],
        'knowledge_cutoff': ctx['knowledge_cutoff'],
        'built_from': ctx['built_from'],
    }

    # Observed - primary vendor figure per material metric
    observed_summary = OrderedDict()
    for metric, entries in ctx.get('observed', {}).items():
        if not isinstance(entries, list):
            observed_summary[metric] = {'raw': entries}
            continue
        figures = []
        for entry in entries:
            fig = entry.get('figure', {})
            pk = fig.get('provenance_kind', 'UNKNOWN')
            if pk == 'OBSERVED':
                figures.append({
                    'provider': entry.get('provider'),
                    'value': fig.get('value'),
                    'unit': fig.get('unit'),
                    'currency': fig.get('currency'),
                    'currency_basis': fig.get('currency_basis'),
                    'period_start': fig.get('period_start'),
                    'period_end': fig.get('period_end'),
                    'as_of': fig.get('as_of'),
                    'available_at': fig.get('available_at'),
                    'available_at_basis': fig.get('available_at_basis'),
                    'ref': fig.get('ref'),
                    'methodology': fig.get('methodology', '')[:100],
                    'status': fig.get('status'),
                })
            else:
                figures.append({
                    'provider': entry.get('provider'),
                    'provenance_kind': pk,
                    'ref': fig.get('ref'),
                    'reason_kind': fig.get('reason_kind'),
                })
        observed_summary[metric] = figures
    t_data['observed'] = observed_summary

    # Validated evidence
    val_evidence = OrderedDict()
    for metric, v in ctx.get('validated_evidence', {}).items():
        val_evidence[metric] = {
            'status': v.get('status'),
            'comparable': v.get('comparable'),
            'vendor_ref': v.get('vendor_ref'),
            'filing_ref': v.get('filing_ref'),
            'tolerance': v.get('tolerance'),
            'independence': v.get('comparison_basis', {}).get('independence', 'N/A') if v.get('comparison_basis') else 'N/A',
            'explanation': v.get('explanation', '')[:200],
            'references': v.get('references', []),
        }
    t_data['validated_evidence'] = val_evidence

    # Derived figures with full trace
    derived_summary = OrderedDict()
    for fig_name, entry in ctx.get('derived', {}).items():
        fig = entry.get('figure', {})
        der_ref = entry.get('derivation_ref', '')
        trc = derivations.get(der_ref, {})
        op = trc.get('operation', {})

        operand_values = []
        for operand_ref in op.get('operands', []):
            obj = refs.get(operand_ref, {})
            operand_info = {
                'ref': operand_ref,
                'kind': obj.get('kind'),
                'value': obj.get('value'),
                'unit': obj.get('unit'),
                'currency': obj.get('currency'),
                'metric': obj.get('metric'),
                'period_start': obj.get('period_start'),
                'period_end': obj.get('period_end'),
            }
            operand_values.append(operand_info)

        state_flags = fig.get('state_flags', [])
        has_undated_input = any(f.get('flag') == 'UNDATED_INPUT' for f in state_flags) if state_flags else False
        has_unvalidated_inputs = any(f.get('flag') == 'UNVALIDATED_INPUTS' for f in state_flags) if state_flags else False

        derived_summary[fig_name] = {
            'value': fig.get('value'),
            'provenance_kind': fig.get('provenance_kind'),
            'ref': fig.get('ref'),
            'derivation_ref': der_ref,
            'op': op.get('op'),
            'version': op.get('version'),
            'operands': op.get('operands'),
            'operand_values': operand_values,
            'expression': trc.get('expression'),
            'deterministic': trc.get('deterministic'),
            'depends_on': trc.get('depends_on'),
            'inputs_observed_at': trc.get('inputs_observed_at'),
            'conditional_on': trc.get('conditional_on'),
            'state_flags': state_flags,
            'has_undated_input': has_undated_input,
            'has_unvalidated_inputs': has_unvalidated_inputs,
        }
    t_data['derived'] = derived_summary

    # Valuation reference
    t_data['valuation_reference'] = ctx.get('valuation_reference', {})

    # Market implied
    mi = ctx.get('market_implied', {})
    t_data['market_implied'] = {
        'conditional_statement': mi.get('conditional_statement'),
        'min_observations_for_reference': mi.get('min_observations_for_reference'),
        'figures': {},
    }
    for fig_name, fig_data in mi.get('figures', {}).items():
        if isinstance(fig_data, dict):
            t_data['market_implied']['figures'][fig_name] = {
                'value': fig_data.get('value'),
                'provenance_kind': fig_data.get('provenance_kind'),
                'ref': fig_data.get('ref'),
            }

    # Data quality
    dq = ctx.get('data_quality', {})
    t_data['data_quality'] = {
        'evidence_coverage': dq.get('evidence_coverage'),
        'cross_source': dq.get('cross_source'),
        'acquisition_errors': dq.get('acquisition_errors'),
        'consensus_forward_eps_period': dq.get('consensus_forward_eps_period'),
        'band_eligibility': dq.get('band_eligibility'),
        'identity_conflicts': dq.get('identity_conflicts'),
        'freshness': {
            'checked': dq.get('freshness', {}).get('checked'),
            'aged_observations': dq.get('freshness', {}).get('aged_observations'),
            'stale_metrics': dq.get('freshness', {}).get('stale_metrics'),
            'no_recent_value_for': dq.get('freshness', {}).get('no_recent_value_for'),
        },
    }

    # Unavailable
    t_data['unavailable'] = ctx.get('unavailable', [])

    # Series / discontinuities
    series = dq.get('series', {})
    series_summary = OrderedDict()
    for metric, sdata in series.items():
        dics = sdata.get('discontinuities', [])
        sp = sdata.get('same_period_pairs', [])
        bases = sdata.get('bases', {})
        series_summary[metric] = {
            'series_status': sdata.get('series_status'),
            'series_status_reason': sdata.get('series_status_reason'),
            'observations': sdata.get('observations'),
            'comparability': sdata.get('comparability'),
            'latest_value': sdata.get('latest_value'),
            'providers': sdata.get('providers'),
            'first_period': sdata.get('first_period'),
            'last_period': sdata.get('last_period'),
            'groups': list(bases.keys()),
            'discontinuities': dics,
            'same_period_pairs': sp,
        }
    t_data['series'] = series_summary

    # Limitations
    t_data['limitations'] = ctx.get('limitations', [])

    results[ticker] = t_data

# Save summary
output_path = 'experiments/002-cold-start/analysis_summary.json'
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
print(f'Saved analysis to {output_path}')
print(f'Size: {os.path.getsize(output_path)} bytes')
