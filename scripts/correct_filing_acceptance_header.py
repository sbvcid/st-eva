import json, sys
def correct(ticker):
    in_path = 'data/historical_pe/' + ticker + '/filing_acceptance_evidence.json'
    out_path = 'data/historical_pe/' + ticker + '/filing_acceptance_evidence_corrected.json'
    with open(in_path, encoding='utf-8') as f: records = json.load(f)
    corrected = []
    missing_header = 0
    for r in records:
        h = r.get('acceptance_datetime_header_et')
        a = r.get('acceptance_datetime_submissions_api')
        new_r = dict(r)
        if h:
            new_r['acceptance_datetime'] = h
        else:
            missing_header += 1
            if a: new_r['acceptance_datetime'] = a
        new_r['acceptance_source'] = 'header_et' if h else ('submissions_api_fallback' if a else 'unknown')
        if 'acceptance_datetime_submissions_api' in new_r:
            new_r['acceptance_datetime_submissions_api_ref'] = new_r.pop('acceptance_datetime_submissions_api')
        corrected.append(new_r)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(corrected, f, ensure_ascii=False, indent=2)
    print(ticker + ': input=' + str(len(records)) + ' corrected=' + str(len(corrected)) + ' missing_header=' + str(missing_header) + ' wrote=' + out_path)
if __name__ == '__main__':
    for t in sys.argv[1:] or ['AAPL','MSFT','MU']:
        correct(t)
