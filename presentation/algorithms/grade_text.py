"""문제 파일과 답안 파일을 받아 공통 점수를 출력한다."""
import sys
from pathlib import Path

from protection.evaluation import Evaluator, validate_protection
from read_text import read_problem

if len(sys.argv) != 3:
    raise SystemExit('사용법: python 채점.py 문제.txt 답안.txt')

with open(sys.argv[1], encoding='ascii') as f:
    scenario, budget = read_problem(f)
tokens = Path(sys.argv[2]).read_text(encoding='ascii').split()
if not tokens or not all(t.isascii() and t.isdecimal() for t in tokens):
    raise ValueError('답안에는 선택 개수와 선 번호를 음이 아닌 정수로 적어야 합니다.')
count, *selected = map(int, tokens)
if count != len(selected):
    raise ValueError('선택한 선의 개수와 번호 수가 일치하지 않습니다.')
validate_protection(scenario, budget, selected)
result = Evaluator(scenario).evaluate(selected, budget)
print('선택한 선:', selected, '/ 방호 비용:', result.cost, '/', budget)
print('최악 공격 후 연결 쌍:', result.connected_pairs)
print('최악 공격 후 전달률:', f'{result.delivery_ratio:.2%}')
