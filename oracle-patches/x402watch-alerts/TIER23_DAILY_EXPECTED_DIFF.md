# Tier 2/3 → daily 전환 — 변경 전후 (EXPECTED DIFF)

`scripts/tier23_to_daily.py --apply` 가 `app/client_classifier.py` 에
만드는 변경. 라인 번호는 인수인계 기준 (실제 환경마다 다를 수 있음 —
anchor 본문 기준으로 매칭).

## 변경 — Tier 2 / Tier 3 return문의 action 리터럴

```diff
     for label, rx in _T2:
         if rx.search(ua):
             return Classification(tier=2, label=label, emoji="🔵",
-                                  action="immediate", pattern=rx.pattern)
+                                  action="daily", pattern=rx.pattern)
     for label, rx in _T3:
         if rx.search(ua):
             return Classification(tier=3, label=label, emoji="🟡",
-                                  action="immediate", pattern=rx.pattern)
+                                  action="daily", pattern=rx.pattern)
     for label, rx in _T4:
         if rx.search(ua):
             return Classification(tier=4, label=label, emoji="⚪",
                                   action="daily", pattern=rx.pattern)
```

두 줄만. 다른 tier 의 return문은 손대지 않음.

## 변경 없음 (보존)

- `TIER2_AI_CLIENT_PATTERNS` / `TIER3_AGENT_FRAMEWORK_PATTERNS` 목록
  — Cursor / Claude Code / Claude Desktop / Anthropic SDK / LangChain /
  AutoGen / CrewAI 등 패턴 자체 그대로.
- `Classification` dataclass 정의 — 필드 4개 (`tier`, `label`, `emoji`,
  `action`, `pattern`) 변경 없음.
- Tier 1 (paid x402, `has_x_payment` 단락) → `action="immediate"`
- Tier 4 (DIRECTORY_BOT)                  → `action="daily"` (원래부터)
- Tier 5 (GENERIC_HTTP)                   → `action="daily"` (원래부터)
- Tier 6 (`promote_to_suspect`)           → `action="immediate"`
- Tier 0 (unknown UA / empty UA)          → `action="first_only"`
- `short_summary()`, `__all__` export 목록 변경 없음.

## 다른 파일 — 변경 없음

| 파일 | 이유 |
|---|---|
| `app/telegram_notify.py` | `if classification.action == "daily": return` 이미 존재 — Tier 4/5 가 쓰던 가지. Tier 2/3 도 같은 가지로 자연 합류. |
| `app/daily_summary.py`   | `rollup()` 이 `classify(ua, …)` 로 매 mcp_call 을 재분류하고 `tier_counter[c.tier]` 로 집계 — action 으로 필터하지 않으므로 Tier 2/3 카운트 보존. |
| `app/mcp_server.py`      | `_track()` 의 `_stats_write({"kind":"mcp_call", …})` 로깅 호출 자체는 무관 — 모든 호출 그대로 디스크에 기록됨. |
| `app/api.py`             | x402 결제 알림은 `notify_payment` 직접 호출, classification action 무관. |

## 결과 동작

| 상황 | fix 전 | fix 후 |
|---|---|---|
| Cursor / Claude Code (Tier 2), free tool 반복 | 5분당 `{tool}\|{ip}` 1발 (수~수십/시간) | 실시간 **0발**, daily "🔵 AI client: N" |
| LangChain / AutoGen / CrewAI (Tier 3) | 5분당 `{tool}\|{ip}` 1발 | 실시간 **0발**, daily "🟡 agent framework: N" |
| Anthropic SDK / OpenAI SDK (Tier 2) | 5분당 1발 | 실시간 **0발**, daily 집계 |
| 결제 (Tier 1, `X-PAYMENT` 헤더) | `notify_payment` 1발/결제 | **그대로 1발/결제** |
| 의심 burst (Tier 6, promote_to_suspect) | 5분당 1발 | **그대로 5분당 1발** |
| 첫 등장 unknown UA (Tier 0) | UA당 24h 1발 | **그대로 24h 1발** |
| Smithery / Glama / curl (Tier 4/5) | 실시간 0발, daily 집계 | **그대로** 0발 / daily 집계 |
| `stats.jsonl` mcp_call 라인 | 모든 호출 기록 | **그대로** 모든 호출 기록 |

핵심: Tier 2/3 알림 경로가 **실시간 → 일일 요약**으로 한 단계 이동.
시그널(결제·의심·첫 등장)은 즉시성을 유지, 정상 AI client/agent
사용은 하루치 묶음으로 받음. 사용자 자체는 사라지지 않음(daily 집계
+ stats.jsonl 원본 보존).
