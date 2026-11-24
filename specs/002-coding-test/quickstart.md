# 제출 및 운영

## 제출 프로그램

시나리오 하나가 stdin으로 전달된다. 각 줄의 값은 공백으로 구분된다.

1. `N M D A`는 노드, 간선, 수요, 공격 후보 개수다.
2. `B`는 방호 비용 예산이다.
3. N줄의 `x y`가 이어진다. 첫 좌표 줄은 노드 0이며, 이후 좌표 줄 순서로 번호를 매긴다.
4. M줄의 `u v capacity_mbps cost`가 이어진다. 간선 번호는 입력 줄 순서로 0부터 매긴다.
5. D줄의 `source target amount_mbps`가 이어진다.
6. A줄의 `x y K edge_id_1 … edge_id_K`가 이어진다. K개 간선은 방호하지 않았을 때 끊기는 피해 목록이다.

ID는 0부터 시작하며 좌표는 실수, 용량과 비용 및 수요량은 정수다. stdout에는 선택 수와 오름차순의 중복 없는 간선 ID를 출력한다. 예산 이하일 때 간선 1번과 4번을 선택한 출력은 `2 1 4`다. 빈 방호안은 `0`이다. 디버그 로그는 stderr에 쓴다. stdout·stderr 합계는 64KiB 이하, 제출 소스는 128KiB 이하다. 종료 코드 75는 골격의 미구현 상태를 표시한다.

간선과 수요의 끝점에 나온 노드 번호를 좌표 리스트의 인덱스로 사용한다. 이전 입력에서 `node_id x y`를 읽던 프로그램은 좌표 두 값만 읽도록 바꾸고, 테스트용 TXT는 다시 내려받거나 `protection input`으로 생성한다. 처음 두 헤더를 읽은 뒤 좌표 구역을 다음과 같이 읽을 수 있다.

```python
nodes = []
for _ in range(node_count):
    x, y = map(float, input().split())
    nodes.append((x, y))
```

## 웹 제출과 결과 읽기

웹에서 소스를 붙여 넣거나 Python 파일을 업로드하면 서버의 SQLite에 저장된다. 채점 중에는 임시 디렉토리에 소스를 기록해 실행하고 종료 시 파일을 정리한다. 로그인 후 직접 선택하거나 개수를 지정해 비복원 무작위로 사례를 선택한다. 각 제출에서는 선택한 사례를 각각 한 번 실행하며 필요하면 다시 제출한다. 계정당 활성 제출은 한 건이다.

연결 쌍 수는 연결된 쌍 / 전체 쌍으로, 전달률은 백분율로 표시한다. 각 격차는 최적해에서 제출안을 뺀 값이다. 전달률 격차는 연결 쌍 수와 관계없이 %p로 표시한다. 방호안 열의 비용을 펼치면 선택한 간선 번호를 확인할 수 있다.

화면의 전달률 격차는 %p이며 CSV의 `gap_delivery_units`는 공식 보고 규칙에 따라 연결 쌍이 같은 완료 행에만 기록한다. 대기 중 취소한 제출은 선택 목록이 남는다. 이미 저장된 결과는 취소나 워커 중단 이후에도 볼 수 있다.

## 공개 문제은행

`scenarios/problem-bank/`는 그래프 72개와 예산별 사례 144개를 제공한다. `configs/problem-bank.json`에 노드 6·8·10·12·14개와 크기별 시드를 고정한다. 한 그래프의 두 예산에서 각 3시간 안에 모든 방호 조합을 평가하고, 전달 점수를 결정하는 유리수 증명이 확보돼야 웹 선택 목록에 두 사례를 함께 추가한다. 제출과 참조 계산은 공통 잠금으로 직렬 실행된다. 끝난 참조 계산과 다음 계산 사이에 대기 중인 채점이 실행될 수 있다.

`bank.json`은 공개 목록이고 `records/`에는 계산 기록이 남는다. `progress.json`에서 활성 사례와 실패 원인을 확인할 수 있다. 승인된 생성 작업의 중단 후에는 `.venv/bin/python -m protection.problem_bank --manifest configs/problem-bank.json --resume`을 사용한다. 재개는 종료 기록이 있는 조건을 다시 검증하고 기록이 없는 조건을 계산한다. 초기 탐색의 미공개 사례와 계산 이력은 `history/`에 보존한다.

## 로컬 채점

텍스트 입력은 `.venv/bin/protection input --bundle BUNDLE.json`으로 내려받을 수 있다. `configs/smoke-grading.json`은 공개 은행의 저장 번들 두 개를 가리킨다. 템플릿의 `ready=false`를 `true`로 바꾸고 `submission.file`에 실제 소스 경로, `output_dir`에 새 출력 경로를 지정한다. 상대 경로는 manifest가 들어 있는 디렉터리 기준이다. 이전 클래스 방식의 manifest를 옮기는 경우 `submission.class_name`을 제거하고 메모리 값을 6000000000으로 지정한다.

Debian WSL 사용자 터미널에서 다음과 같이 위임된 임시 서비스로 채점한다.

```bash
systemd-run --user -p Delegate=yes -p DelegateSubgroup=supervisor \
  --working-directory="$PWD" "$PWD/.venv/bin/protection" grade --manifest "$PWD/configs/smoke-grading.json"
```

명령이 반환한 유닛 이름으로 `journalctl --user -u 유닛이름`에서 채점 상태를 확인한다. `PROTECTION_STATE_DIR`을 웹 및 워커와 같은 경로로 맞추면 웹·로컬 채점과 문제은행 계산이 파일 잠금을 공유한다. 기본값은 실행 사용자의 `~/.local/state/protection-judge`다. 노트북 smoke도 같은 위임을 받은 서비스에서 실행한다.

## 운영 서버 배포

배포 유닛은 `user` 계정과 `/home/user/os-project-26-2`를 사용한다. 운영 서버의 해당 프로젝트 루트에서 계정 설정을 실행한다. 초기 암호는 이 터미널에 한 번 출력된다. 각자에게 자기 암호만 전달한다. 특정 암호를 재발급할 때는 `accounts --reset member1`처럼 지정한다.

```bash
sudo apt install -y bubblewrap
.venv/bin/python -m pip install -e '.[web]'
.venv/bin/python -m protection.web accounts
sudo bash deploy/switch-judge.sh
```

`switch-judge.sh`는 이전 테스트 서비스가 설치돼 있으면 중지하고 자동 시작 등록과 유닛 파일을 제거한다. 채점 웹 서비스와 워커를 시작하고 `127.0.0.1:18080/login`을 확인한 뒤 두 서비스를 자동 시작 대상으로 설정한다. 로그인 화면을 확인하지 못하면 배포 명령은 오류를 반환한다. Cloudflare 터널은 `127.0.0.1:18080`을 계속 사용한다.
