#!/usr/bin/env bash
set -Eeuo pipefail
cd /home/user/os-project-26-2

if [[ $EUID != 0 ]] || [[ ! -x /usr/bin/bwrap ]]; then
    echo 'Run with sudo after installing Debian bubblewrap.' >&2
    exit 1
fi

install -m 0644 deploy/protection-judge-{worker,web}.service /etc/systemd/system/
systemctl daemon-reload
systemctl start protection-judge-worker.service

# 새 서비스의 로그인 화면이 열리지 않으면 기존 서버를 다시 가동한다.
rollback() {
    systemctl stop protection-judge-web.service protection-judge-worker.service || true
    systemctl start algorithm-flask.service
}
trap rollback ERR
systemctl stop algorithm-flask.service
systemctl start protection-judge-web.service

for attempt in {1..15}; do
    if curl -fsS --max-time 2 http://127.0.0.1:18080/login | grep '팀원 로그인' >/dev/null; then
        systemctl enable protection-judge-worker.service protection-judge-web.service
        systemctl disable algorithm-flask.service
        trap - ERR
        exit 0
    fi
    sleep 1
done
rollback
exit 1
