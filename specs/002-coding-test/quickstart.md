# 제출 및 운영

## 제출 프로그램

시나리오 하나가 stdin으로 전달된다. 각 줄의 값은 공백으로 구분된다.

1. `N M D A`는 노드, 간선, 수요, 공격 후보 개수다.
2. `B Q S R`은 비용 예산, 예산 비율(%), 시나리오 시드, 전략 시드다. 결정적 실행에서 R은 -1이다.
3. N줄의 `node_id x y`가 이어진다.
4. M줄의 `edge_id u v capacity_mbps cost`가 이어진다.
5. D줄의 `demand_id source target amount_mbps`가 이어진다.
6. A줄의 `attack_id x y K edge_id_1 … edge_id_K`가 이어진다. K개 간선은 방호하지 않았을 때 끊기는 피해 목록이다.

ID는 0부터 시작하며 좌표는 실수, 용량과 비용 및 수요량은 정수다. stdout에는 선택 수와 오름차순의 중복 없는 간선 ID를 출력한다. 예산 이하일 때 간선 1번과 4번을 선택한 출력은 `2 1 4`다. 빈 방호안은 `0`이다. 디버그 로그는 stderr에 쓴다. 종료 코드 75는 골격의 미구현 상태를 표시한다.

## 웹 결과 읽기

연결 쌍 수는 연결된 쌍 / 전체 쌍으로, 전달률은 백분율로 표시한다. 각 격차는 최적해에서 제출안을 뺀 값이다. 전달률 격차는 연결 쌍 수와 관계없이 %p로 표시한다. 방호안 열의 비용을 펼치면 선택한 간선 번호를 확인할 수 있다.

## 확장 문제은행

`configs/expanded-certified-bank.json`에 노드 6·8·10·12·14개와 크기별 시드를 고정한다. 한 그래프의 두 예산에서 각 3시간 안에 모든 방호 조합을 평가하고, 전달 점수를 결정하는 유리수 증명이 확보돼야 웹 선택 목록에 두 사례를 함께 추가한다. 제출과 참조 계산은 공통 잠금으로 직렬 실행된다. 끝난 참조 계산과 다음 계산 사이에 대기 중인 채점이 실행될 수 있다.

`scenarios/expanded-certified-bank/bank.json`은 공개 목록이고 `records/`에는 실제 계산 결과가 남는다. `progress.json`에서 활성 사례와 실패 원인을 확인할 수 있다. 중단된 작업은 동일한 manifest로 `python -m protection.problem_bank --manifest configs/expanded-certified-bank.json --resume`을 실행해 이어간다.

## 로컬 채점

텍스트 입력은 `.venv/bin/protection input --bundle BUNDLE.json`으로 내려받을 수 있다. `configs/smoke-grading.json`을 바탕으로 제출 경로와 출력 경로를 지정한다. 경로는 manifest가 들어 있는 디렉터리 기준이다. 기존 manifest는 `submission.class_name`을 제거하고 메모리 값을 6000000000으로 지정한다.

Debian WSL 사용자 터미널에서 다음과 같이 위임된 임시 서비스로 채점한다.

```bash
systemd-run --user -p Delegate=yes -p DelegateSubgroup=supervisor \
  --working-directory="$PWD" "$PWD/.venv/bin/protection" grade --manifest "$PWD/configs/smoke-grading.json"
```

명령이 반환한 유닛 이름으로 `journalctl --user -u 유닛이름`에서 채점 상태를 확인한다. 계정 서비스와 동일한 기본 디렉터리를 사용하면 웹과 로컬 채점이 하나의 파일 잠금으로 직렬화된다. 노트북 smoke도 같은 위임을 받은 서비스에서 실행한다.

## 기존 Cloudflare 터널로 전환

프로젝트 루트에서 실행한다. 초기 암호는 이 터미널에 한 번 출력된다. 각자에게 자기 암호만 전달한다. 특정 암호를 재발급할 때는 `accounts --reset member1`처럼 지정한다.

```bash
sudo apt install -y bubblewrap
.venv/bin/python -m pip install -e '.[web]'
.venv/bin/python -m protection.web accounts
sudo bash deploy/switch-judge.sh
```

`switch-judge.sh`는 기존 localhost:18080 서비스를 교체한다. 본 서버 로그인 페이지를 확인한 후에만 새 서비스를 자동 시작 대상으로 설정한다. 시작 검증 실패 시 이전 테스트 서비스를 재시작한다. Cloudflare 터널 설정은 기존 서비스를 사용한다.
