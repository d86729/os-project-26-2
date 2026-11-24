"""Re-score all saved answers and independently check edge betweenness."""
from collections import Counter
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import collect_environment, initialize_single_thread
initialize_single_thread()

import networkx as nx
from protection.evaluation import Evaluator
from protection.models import load_bundle
from protection.program import scenario_input


def main():
    affinity = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {affinity[0]})
    protocol = json.loads((HERE/'protocol.json').read_text())
    rows = [json.loads(line) for line in (HERE/'runs.jsonl').read_text().splitlines()]
    expected = {(x['name'], y['method']) for x in protocol['cases'] for y in protocol['methods']}
    assert len(rows) == len(expected)
    assert {(r['name'], r['method']) for r in rows} == expected
    for method in protocol['methods']:
        assert sha256((ROOT/method['path']).read_bytes()).hexdigest() == method['sha256']
    spec = importlib.util.spec_from_file_location('baseline_centrality',
        ROOT/'results/agent-study/2026-11-22/agent-1/betweenness.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    grouped = {case['name']: [] for case in protocol['cases']}
    for row in rows:
        grouped[row['name']].append(row)
    checked = 0
    for case in protocol['cases']:
        bundle = load_bundle(ROOT / case['path'], require_reference=True)
        assert bundle.case_id == case['case_id']
        input_hash = sha256(scenario_input(bundle)).hexdigest()
        graph = nx.Graph()
        graph.add_nodes_from(range(len(bundle.scenario.nodes)))
        graph.add_edges_from((e.u,e.v) for e in bundle.scenario.edges)
        networkx_values = nx.edge_betweenness_centrality(graph, normalized=False, weight=None)
        edges = [(e.id,e.u,e.v,e.capacity_mbps,e.cost) for e in bundle.scenario.edges]
        values = baseline.centrality(len(bundle.scenario.nodes), edges)
        for edge in bundle.scenario.edges:
            assert abs(float(values[edge.id]) - networkx_values[edge.u,edge.v]) < 1e-9
        for row in grouped[case['name']]:
            assert row['case_id'] == bundle.case_id and row['stdin_sha256'] == input_hash
            assert row['source_sha256'] == next(m['sha256'] for m in protocol['methods'] if m['method'] == row['method'])
            if row['status'] == 'completed':
                result = Evaluator(bundle.scenario).evaluate(row['chosen_edges'],bundle.budget)
                assert result.connected_pairs == row['connected_pairs']
                assert result.delivery_units == row['delivery_units']
                assert abs(result.delivery_ratio - row['delivery_ratio']) < 1e-12
                assert result.cost == row['cost']
                assert result.score <= bundle.optimal_reference.evaluation.score
                checked += 1
    report = {'rows':len(rows), 'cases':len(protocol['cases']), 'successful_scores_recomputed':checked,
              'status_counts':dict(Counter(r['status'] for r in rows)),
              'source_hashes_checked':len(protocol['methods']), 'case_id_and_stdin_sha_checked':True,
              'networkx_betweenness_graphs':len(protocol['cases'])//2,
              'environment':collect_environment(),
              'notes':['source code was hashed, submitted output was re-scored, and source was not re-executed',
                       'runtime measurements were not regenerated']}
    (HERE/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f"Verified {len(rows)} rows, {checked} scores, {len(protocol['cases'])} references and independent centrality.", flush=True)


if __name__ == '__main__':
    main()
