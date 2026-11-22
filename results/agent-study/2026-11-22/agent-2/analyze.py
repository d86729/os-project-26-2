"""Summarize the 20-case development experiment without treating budgets as independent graphs."""
import csv
from decimal import Decimal, ROUND_HALF_EVEN
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent


def load(name):
    with (HERE/name).open(encoding='utf-8-sig',newline='') as handle:
        return {row['scenario']:row for row in csv.DictReader(handle)}


def official_key(row):
    # Connected ratios have a common denominator within the same case.
    # Delivery comparisons use the official six-decimal HALF_EVEN score.
    return (Decimal(row['connected_ratio']),
            Decimal(row['delivery_ratio']).quantize(Decimal('.000001'),rounding=ROUND_HALF_EVEN))


def summarize():
    single=load('ablation_single-web.csv'); bundle=load('submission-web.csv')
    assert set(single)==set(bundle)
    summary={'sample':'development_only','graphs':len(single)//2,'cases':len(single),'methods':{},'case_comparison':{},'graph_blocks':[]}
    for name,data in [('single',single),('bundle',bundle)]:
        good=[r for r in data.values() if r['status']=='completed']
        summary['methods'][name]={'completed':len(good),'failed':len(data)-len(good),
            'optimal_score_matches':sum(r['gap_connected_pairs']=='0' and r['gap_delivery_units']=='0' for r in good),
            'optimal_connectivity_matches':sum(r['gap_connected_pairs']=='0' for r in good),
            'median_seconds':statistics.median(float(r['search_seconds']) for r in good),
            'max_seconds':max(float(r['search_seconds']) for r in good),
            'max_worker_mb':max(float(r['worker_peak_mb']) for r in good)}
    wins=ties=losses=0
    for graph in sorted({case.rsplit('-p',1)[0] for case in single}):
        rows=[]
        for budget in (20,40):
            case=f'{graph}-p{budget}'; a,b=single[case],bundle[case]
            assert a['status']==b['status']=='completed'
            ka,kb=official_key(a),official_key(b)
            outcome=1 if kb>ka else (-1 if kb<ka else 0)
            wins+=outcome==1; ties+=outcome==0; losses+=outcome==-1
            rows.append({'case':case,'bundle_vs_single':outcome,
                         'connected_ratio_difference':float(b['connected_ratio'])-float(a['connected_ratio']),
                         'delivery_ratio_difference':float(b['delivery_ratio'])-float(a['delivery_ratio']),
                         'seconds_difference':float(b['search_seconds'])-float(a['search_seconds'])})
        summary['graph_blocks'].append({'graph':graph,'budget_results':rows,
            'mean_connected_ratio_difference':statistics.mean(r['connected_ratio_difference'] for r in rows),
            'mean_seconds_difference':statistics.mean(r['seconds_difference'] for r in rows)})
    summary['case_comparison']={'wins':wins,'ties':ties,'losses':losses}
    summary['descriptive_graph_mean_connected_ratio_difference']=statistics.mean(r['mean_connected_ratio_difference'] for r in summary['graph_blocks'])
    summary['inference']='No significance test: 10 development graphs, two correlated budgets per graph; held-out confirmation is coordinated separately.'
    return summary


if __name__=='__main__':
    result=summarize()
    (HERE/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='graph_blocks'},indent=2))
