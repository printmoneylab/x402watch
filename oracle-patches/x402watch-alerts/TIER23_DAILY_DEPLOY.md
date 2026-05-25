# Tier 2/3 → daily 전환 (2-b) — 배포

`client_classifier.py`의 Tier 2 (Cursor / Claude Code / Claude Desktop /
Anthropic SDK 등) + Tier 3 (LangChain / AutoGen / CrewAI 등)의 alert
action을 `immediate` → `daily`로 변경. 실시간 텔레그램 알림은 침묵,
KST 09:00 일일 요약의 "tier breakdown" 줄에는 그대로 카운트.

대상: `app/client_classifier.py` 단 한 파일. `x402watch-api.service` +
`x402watch-mcp.service` 양쪽 재시작 (분류기는 두 곳에서 import).

| 보존 | 영향 |
|---|---|
| Tier 1 (paid x402) — `immediate` | Tier 2 — `immediate` → **`daily`** |
| Tier 6 (suspect) — `immediate`   | Tier 3 — `immediate` → **`daily`** |
| Tier 0 (unknown UA) — `first_only` 24h |  |
| payment 알림 (`notify_payment`, no action gate) |  |
| stats.jsonl mcp_call 로깅 (`_track`의 `_stats_write` 호출) |  |
| daily_summary tier_breakdown (ua → classify 재분류) |  |

전제: 이전 fix 두 개가 이미 들어가 있어야 한다 — `_track()` 경로 B
제거([[remove-legacy-mcp-alert-path]]) + Cloudflare 클라이언트 IP
순서 수정([[fix-mcp-client-ip]]).

---

## Step 1 — 진단 (apply 전, 읽기 전용)

```bash
cd /home/ubuntu/x402watch

# 1a. Tier 2/3 현재 action 값
grep -n -A1 'tier=2, label=label, emoji="🔵"' app/client_classifier.py
grep -n -A1 'tier=3, label=label, emoji="🟡"' app/client_classifier.py
# expect: 두 블록 모두 action="immediate"

# 1b. 다른 tier의 action 값 (Tier 1/4/5/6/0 보존 확인용 baseline)
grep -nE 'action="(immediate|daily|first_only)"' app/client_classifier.py

# 1c. telegram_notify.py 의 action="daily" early-return 가지
grep -n -B1 -A1 'classification.action == "daily"' app/telegram_notify.py
# expect: notify_mcp_tool 안에서 `return` (즉 알림 발사 안 함)

# 1d. daily_summary.py 가 stats.jsonl 에서 tier별로 어떻게 집계하는지
grep -nE 'classify\(|tier_counter|c\.tier' app/daily_summary.py
# expect: classify(ua, ...) → tier_counter[c.tier] += 1
#         (action 으로 필터하지 않음 — 모든 mcp_call 을 재분류)

# 1e. stats.jsonl mcp_call 레코드는 tier 없는지 확인 (재분류 의존)
tail -50 /home/ubuntu/x402watch/var/stats.jsonl 2>/dev/null \
  | grep '"mcp_call"' | head -3 | python3 -m json.tool 2>/dev/null \
  | grep -E '"(tier|ua|kind)"'
# expect: ua 있음, tier 없음, kind=mcp_call
```

**기대 (정상)**: 1a 두 블록 모두 `action="immediate"`. 1b는 Tier 1/2/3
가 `immediate`, Tier 4/5 가 `daily`, Tier 0 가 `first_only`. 1c는
`notify_mcp_tool` 안에서 `if classification.action == "daily": return`
한 줄이 보임. 1d는 `classify(ua, …)` + `tier_counter[c.tier]`. 1e는
ua/kind만, tier 키 없음 — daily_summary가 ua 기반 재분류로 동작.

**분기**:
- 1a에 한쪽만 `action="immediate"`고 다른 쪽이 이미 `"daily"` → 부분
  적용 상태. 패처가 "mid-state" 로 거부하고 멈춤. 백업 복구 후 재시작.
- 1d에 `classify(ua` 가 없거나 `tier_counter` 가 다른 키 (e.g. action
  기반) 로 집계 → **STOP**, daily_summary도 같이 패치 필요 (Path B).
  현재 인수인계 기준 v2.1에서는 ua 기반 재분류 확인됨.
- 1e에 mcp_call 줄이 안 보임 → 로그가 아직 안 쌓였거나 경로 다름.
  배포 자체는 진행 OK; 검증 Step 3c는 24h 이후 의미 있음.

## Step 2 — 패처 적용

```bash
cd /home/ubuntu/x402watch
# (Oracle은 git repo 아님 — SCP 운영)
# 로컬에서 SCP로 패처 올린 직후:
cp oracle-patches-x402watch-alerts/tier23_to_daily.py \
   scripts/tier23_to_daily.py

# dry-run — 무엇이 바뀌는지 먼저
venv/bin/python scripts/tier23_to_daily.py

# 적용 (백업 자동: client_classifier.py.bak.tier23-daily-YYYYMMDD-HHMM)
venv/bin/python scripts/tier23_to_daily.py --apply

# 두 서비스 재시작 (client_classifier는 api + mcp 양쪽에서 import)
sudo systemctl restart x402watch-api x402watch-mcp
sudo systemctl is-active x402watch-api x402watch-mcp
# expect: active / active

sudo journalctl -u x402watch-api -n 20 --no-pager | grep -E "ERROR|Traceback|startup"
sudo journalctl -u x402watch-mcp -n 20 --no-pager | grep -E "ERROR|Traceback|startup"
```

dry-run 기대 출력:
```
✓ Tier 2 action: "immediate" → "daily"
✓ Tier 3 action: "immediate" → "daily"
✓ ast.parse OK
(dry-run — re-run with --apply to write)
```

이미 한 번 적용된 환경에서 재실행:
```
◌ already patched (Tier 2 + Tier 3 both daily) — no-op
```

## Step 3 — 회귀 검증

```bash
# 3a. 분류기 import + Tier 2/3 action 확인
cd /home/ubuntu/x402watch
venv/bin/python -c "
from app.client_classifier import classify
for ua in [
    'Cursor/0.42',
    'claude-code/1.0',
    'anthropic-ai/0.30',
    'langchain/0.1',
    'autogen/0.2',
    'crewai/0.5',
]:
    c = classify(ua)
    print(f'{c.tier} {c.action:<10} {c.label:<30} {ua}')
"
# expect: Tier 2/3 둘 다 'daily'
#         Tier 2: Cursor IDE / Claude Code / Anthropic SDK
#         Tier 3: LangChain / AutoGen / CrewAI

# 3b. Tier 1/4/5/6/0 보존 확인
venv/bin/python -c "
from app.client_classifier import classify, promote_to_suspect
print('Tier 1:', classify('Cursor/0.42', has_x_payment=True).action)  # immediate
print('Tier 4:', classify('Smithery/1.0').action)                      # daily
print('Tier 5:', classify('python-requests/2.31').action)              # daily
print('Tier 6:', promote_to_suspect(classify('weird-bot/0.1')).action) # immediate
print('Tier 0:', classify('').action)                                  # first_only
"

# 3c. telegram_notify.notify_mcp_tool 의 daily 가지 (dry, send_text 가로채기)
venv/bin/python -c "
import asyncio
from app import telegram_notify as tn
from app.client_classifier import classify
sent = []
async def fake(text, **kw): sent.append((text[:40], kw))
tn.send_text = fake
async def main():
    await tn.notify_mcp_tool(
        tool_name='x402_get_categories',
        classification=classify('Cursor/0.42'),
        ip='1.2.3.4', user_agent='Cursor/0.42', is_paid_tool=False,
    )
asyncio.run(main())
print('sent:', sent)  # expect: []  (Tier 2 daily — early return)
"

# 3d. 결제 알림 경로는 무관 (notify_payment는 action 게이트 없음)
grep -n "classification.action" app/telegram_notify.py
# expect: notify_mcp_tool 안에서만 1번 (daily 가지)
#         notify_payment 에는 등장하지 않음
```

## Step 4 — 24h 후 일일 요약 검증

```bash
# 다음 09:00 KST 요약이 발사된 직후:
sudo journalctl -u x402watch-api --since "today 08:55" --until "today 09:10" \
  | grep -E "daily summary sent"
# expect: payments=N mcp=M 5xx=K  (M에 Tier 2/3 호출이 누락되지 않음)

# 텔레그램 일일 메시지의 "tier breakdown" 줄에
#   🔵 AI client: <N>
#   🟡 agent framework: <N>
# 이 0이 아닌 경우 — Tier 2/3 호출이 발생했고, 실시간 알림은
# 침묵했지만 daily 집계에는 정상 반영된다는 의미.
```

## Step 5 — 롤백

```bash
cd /home/ubuntu/x402watch/app
ls -t client_classifier.py.bak.tier23-daily-* | head -1
cp "$(ls -t client_classifier.py.bak.tier23-daily-* | head -1)" client_classifier.py
sudo systemctl restart x402watch-api x402watch-mcp
```

롤백은 Tier 2/3 실시간 알림을 되살린다 — Cursor/Claude Code/LangChain
사용자가 5분당 1발씩(`{tool}|{ip}` 키) 다시 흐른다. 이번 fix 자체에
오작동이 있을 때만 사용. 부분 노이즈 조정이 필요하면 롤백 대신
`client_classifier.py` 의 Tier 4/5 패턴 목록에 특정 UA를 추가하는 쪽이
더 외과적.

## 예상 효과

오늘(2026-05-25)과 같은 트래픽 — Claude Code / Cursor 같은 Tier 2
클라이언트가 5개의 free MCP 도구를 반복 호출 — 에서:
- fix 전: tool×IP 조합당 5분에 1발 → 시간당 수~수십 발
- fix 후: 실시간 알림 **0발**, 일일 요약 "🔵 AI client: <N>" 한 줄로
  N건 집계
- Tier 1 결제 / Tier 6 burst 의심 / Tier 0 첫 등장 UA 는 **그대로 발사**
