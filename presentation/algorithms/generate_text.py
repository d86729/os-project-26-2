"""생성 시드로 공통 문제를 만들어 표준 출력에 쓴다."""
import argparse

from protection.evaluation import budget_for
from protection.generation import generate_scenario
from protection.models import ScenarioBundle
from protection.program import scenario_input

parser = argparse.ArgumentParser(description='시드로 통신망 문제 생성')
parser.add_argument('seed', type=int, help='같은 문제를 다시 만들기 위한 생성 시드')
parser.add_argument('--nodes', type=int, default=6, help='기지 수 (기본 6)')
parser.add_argument('--budget', type=int, choices=[20, 40], default=20, help='예산 비율 (기본 20)')
args = parser.parse_args()

scenario = generate_scenario(args.nodes, args.seed)
budget = budget_for(scenario, args.budget)
bundle = ScenarioBundle(scenario, args.budget, budget)
print(scenario_input(bundle).decode('ascii'), end='')
