# MCP 알림 이중 발사 fix — 배포

`_track()`의 경로 B(`_tg_notify` 레거시 알림) 제거. 2026-05-21 KST에
단일 Tier-0 UA burst가 경로 B로 200+ 텔레그램 알림을 발사한 원인.

경로 A(`_notify_mcp_tool`, tier-aware, Tier-0은 24h dedupe)는 유지.

대상: `app/mcp_server.py` 단 한 파일. `x402watch-mcp.service`만 재시작.

---

## Step 1 — 진단 (apply 전, 읽기 전용)

```bash
cd /home/ubuntu/x402watch

# 1a. 경로 B 심볼 사용처 — _track() 안에만 있어야 정상
grep -nE "_tg_notify|_last_notified|_NOTIFY_COOLDOWN_SECONDS" app/mcp_server.py

# 1b. 다른 모듈이 이 심볼을 import/참조하나 (없어야 정의도 같이 제거 가능)
grep -rnE "_last_notified|_NOTIFY_COOLDOWN_SECONDS" app/ --include='*.py' | grep -v mcp_server.py

# 1c. _track() 함수 전체 (백업 anchor 눈으로 확인)
sed -n '/^def _track/,/^mcp = /p' app/mcp_server.py

# 1d. time 모듈이 _track() 밖에서 쓰이나 (import 정리 판단)
grep -nE "\btime\." app/mcp_server.py
```

**기대 (정상)**: 1a는 `_tg_notify` 정의 1줄 + `_track()` 내부 경로 B
줄들 + `_tg_notify` 정의. 1b는 비어 있음(다른 모듈 미참조). 1d는
`time.monotonic()` 한 줄(경로 B 내부)만.

**분기**:
- 1b가 비어있지 않음 → 패처가 `_last_notified`/`_NOTIFY_COOLDOWN_SECONDS`
  정의를 자동 보존(self-verify). 그대로 진행 OK.
- 1d에 `time.` 가 경로 B 밖에도 있음 → 패처가 `import time` 보존. OK.
- 1a에 `_tg_notify`가 mcp_server.py에 아예 없음 → 알림 코드가 예상과
  다름. 패처가 ANCHOR DRIFTED로 멈춤 → `_track()` 본문 paste 요청.

## Step 2 — 패처 적용

```bash
cd /home/ubuntu/x402watch
git fetch origin && git pull --ff-only origin main
cp oracle-patches/x402watch-alerts/remove_legacy_mcp_alert_path.py \
   scripts/remove_legacy_mcp_alert_path.py

# dry-run — 무엇이 바뀌는지 먼저
venv/bin/python scripts/remove_legacy_mcp_alert_path.py

# 적용 (백업 자동: mcp_server.py.bak.dedupe-fix-YYYYMMDD-HHMM)
venv/bin/python scripts/remove_legacy_mcp_alert_path.py --apply

# 재시작
sudo systemctl restart x402watch-mcp
sudo systemctl is-active x402watch-mcp        # expect: active
sudo journalctl -u x402watch-mcp -n 20 --no-pager | grep -E "ERROR|Traceback|startup"
```

dry-run 기대 출력:
```
✓ path B removed from _track()
✓ removed now-unused `_last_notified` definition
✓ removed now-unused `_NOTIFY_COOLDOWN_SECONDS` definition
✓ removed now-unused `import time`
✓ ast.parse OK
```
(1b/1d 결과에 따라 일부는 `◌ ... kept`로 나올 수 있음 — 정상.)

## Step 3 — 회귀 검증

```bash
# 3a. mcp_server import 정상
cd /home/ubuntu/x402watch
venv/bin/python -c "from app import mcp_server; print('mcp_server import OK')"

# 3b. PR #36 v2.4 헤더 유지 (이 fix와 무관해야 함)
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep -i x-x402-rewriter
# expect: x-x402-rewriter: v2.4

# 3c. MCP probe — initialize 1회 (결제 없음), 서버 reachability
curl -sS -m 15 https://api.x402.printmoneylab.com/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "User-Agent: ClaudeCodeProbe/1.0" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ClaudeCodeProbe","version":"1.0"}}}' \
  | head -c 300
echo

# 3d. _tg_notify 함수 정의는 보존됐는지 (payment 알림이 쓸 수 있음)
grep -n "async def _tg_notify\|def _tg_notify" app/mcp_server.py
# expect: 정의 1줄 존재 (호출만 제거, 정의는 유지)

# 3e. _track() 안에 _tg_notify 호출이 사라졌는지
sed -n '/^def _track/,/^mcp = /p' app/mcp_server.py | grep -c "_tg_notify"
# expect: 0  (경로 B 제거 — _track() 안에서 _tg_notify 호출 없음)
```

**Tier별 알림 동작 (재시작 후 자연 트래픽 기준)**:
- Tier 0 (UA 없음/미상) → 경로 A의 `unknown:{ua}` 24h dedupe → 하루 1발
- Tier 2 (Cursor 등) → `{tool}|{ip}` 5분 dedupe → tool·IP당 5분 1발
- Tier 4/5 (Smithery/curl) → `notify_mcp_tool`이 즉시 return → 알림 0
- 경로 B(tool당 5분, tier·IP 무시)는 **완전 제거**

## Step 4 — 롤백

```bash
cd /home/ubuntu/x402watch/app
ls -t mcp_server.py.bak.dedupe-fix-* | head -1     # 최신 백업 확인
cp "$(ls -t mcp_server.py.bak.dedupe-fix-* | head -1)" mcp_server.py
sudo systemctl restart x402watch-mcp
```

패처는 idempotent — 재적용해도 "already patched"로 무해. 롤백은
경로 B를 되살리므로(과다 알림 복귀) fix 자체에 문제가 있을 때만.

## 예상 효과

오늘(2026-05-21)과 같은 트래픽 — 단일 Tier-0 UA가 7시간 burst —
이 다시 와도: 경로 B 제거 → 경로 A의 24h dedupe만 적용 → **하루 1발**.
오늘 200+ → 1.
