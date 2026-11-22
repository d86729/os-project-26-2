#!/usr/bin/env bash
set -Eeuo pipefail
cd /home/user/os-project-26-2

if [[ $EUID != 0 ]] || [[ ! -x /usr/bin/bwrap ]]; then
    echo 'Run with sudo after installing Debian bubblewrap.' >&2
    exit 1
fi

install -m 0644 deploy/protection-judge-{worker,web}.service /etc/systemd/system/

# 삭제된 테스트 앱의 로컬 서비스를 한 번만 정리한다.
legacy_unit=/etc/systemd/system/algorithm-flask.service
if [[ -f $legacy_unit ]]; then
    systemctl disable --now algorithm-flask.service
    rm -- "$legacy_unit"
fi

systemctl daemon-reload
systemctl restart protection-judge-web.service

for attempt in {1..15}; do
    if login_page=$(curl -fsS --max-time 2 http://127.0.0.1:18080/login) &&
        [[ $login_page == *'팀원 로그인'* ]]; then
        systemctl enable --now protection-judge-worker.service protection-judge-web.service
        exit 0
    fi
    sleep 1
done

echo '채점 앱의 로그인 화면을 http://127.0.0.1:18080/login 에서 확인하지 못했습니다.' >&2
exit 1
