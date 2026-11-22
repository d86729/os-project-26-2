# 구현 계획

**Feature ID**: `002-coding-test`

**Spec**: [코딩 테스트](spec.md) · [공통 연구](../001-network-protection-study/spec.md)

1. `protection/program.py`는 저장 번들을 stdin으로 직렬화하고 stdout 방호안을 검증한다. 노드 좌표는 번들의 노드 순서로 쓰고 끝점 참조는 해당 순서의 0 기반 행 번호를 사용한다. ID 필드 제거는 텍스트 직렬화에 적용한다. `protection/cli.py`의 `input`과 `grade`, `protection/web.py`의 예시·다운로드와 채점 워커가 이 계약을 공유한다. 공식 평가는 `protection/evaluation.py`가 담당한다. (FR-002~005, SC-005, SC-007)
2. Flask와 Gunicorn은 계정, 본인 제출 및 결과 화면을 제공한다. SQLite는 제출 소유자·소스·선택 사례·한도·상태와 실행 행을 보관한다. 워커는 대기 순서대로 제출을 가져오고 각 반복 실행이 끝날 때 행을 저장한다. (FR-001, FR-003, FR-006, SC-002, SC-004)
3. 위임된 Linux cgroup v2 서비스에서 별도 워커 감독자가 실행별 CPU·메모리·프로세스 수를 제한하고 최대 메모리를 기록한다. Bubblewrap은 제출 실행의 네트워크와 파일 접근을 격리한다. 웹·로컬·은행 생성은 같은 상태 디렉터리에서 잠금을 공유한다. `deploy/`의 systemd 유닛이 워커와 localhost 웹 서비스를 기동한다. (FR-004~005, SC-005~006)
4. 웹 결과 렌더링은 저장 행의 사례 ID를 공개 번들과 대조한다. 제출안의 연결 쌍 수와 비용을 복원하고 원정밀도 전달률로 %p 격차를 표시한다. CSV는 연구 보고에 쓰는 공식 격차를 따른다. (FR-006~008, SC-001~002)
5. `protection/problem_bank.py`는 사전 등록된 입력을 사용하고 실행 기록 및 진행 상태를 저장한다. `protection/exact.py`의 평가 건수를 독립적으로 대조하고 유리수 인증이 있는 참조만 결합한다. 두 예산의 번들을 검증한 그래프를 `scenarios/problem-bank/bank.json`에 함께 추가하며 웹과 워커가 이 인덱스를 공유한다. 인덱스의 번들 경로와 저장 manifest의 출력 경로는 각 파일을 기준으로 해석한다. (FR-009, SC-003)

현행 경로와 재현 절차는 [운영 안내](quickstart.md), 과거 검증 및 남은 재검증은 [작업 목록](tasks.md)에 기록한다.
