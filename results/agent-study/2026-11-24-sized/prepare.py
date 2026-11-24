"""Prepare pre-registered inputs; preserve existing bank and exact references."""
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from protection.runner import initialize_single_thread
initialize_single_thread()
from protection.evaluation import budget_for
from protection.generation import generate_scenario
from protection.models import ScenarioBundle, feasible_protection_count, load_bundle, to_data
from protection.program import scenario_input


def main():
    protocol = json.loads((HERE/'protocol.json').read_text())
    out = HERE/'cases.json'
    if out.exists():
        raise RuntimeError('cases already prepared')
    cases = []
    for n_string, seeds in protocol['seed_selection']['seeds_by_size'].items():
        n = int(n_string)
        for seed in seeds:
            new_scenario = generate_scenario(n,seed) if n >= 16 else None
            for percent in protocol['budgets_percent']:
                name = f'n{n}-seed{seed}-p{percent}'
                if new_scenario is None:
                    path = ROOT/'scenarios/problem-bank/bundles'/(name+'.json')
                    bundle = load_bundle(path, require_reference=True)
                else:
                    bundle = ScenarioBundle(new_scenario, percent, budget_for(new_scenario,percent))
                    path = HERE/'bundles'/(name+'.json')
                    path.parent.mkdir(parents=True,exist_ok=True)
                    data = to_data(bundle)
                    data.pop('optimal_reference')
                    data['artifact_kind'] = 'scenario_bundle'
                    with path.open('x',encoding='utf-8') as f:
                        json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
                        f.write('\n')
                assert len(bundle.scenario.nodes)==n and bundle.scenario.seed==seed
                text = scenario_input(bundle)
                cases.append({'name':name,'n':n,'seed':seed,'budget_percent':percent,
                    'edge_count':len(bundle.scenario.edges),'budget':bundle.budget,
                    'case_id':bundle.case_id,'path':str(path.relative_to(ROOT)),
                    'stdin_sha256':sha256(text).hexdigest(),
                    'reference_available':bundle.optimal_reference is not None,
                    'feasible_sets':feasible_protection_count(bundle.scenario,bundle.budget)})
    assert len(cases)==20
    out.write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n')
    for case in cases:
        print(case['name'],'m=',case['edge_count'],'feasible=',case['feasible_sets'],
              'reference=',case['reference_available'],flush=True)


if __name__=='__main__':
    main()
