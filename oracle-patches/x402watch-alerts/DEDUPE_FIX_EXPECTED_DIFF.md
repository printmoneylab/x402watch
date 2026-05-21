# MCP 알림 이중 발사 fix — 변경 전후 (EXPECTED DIFF)

`scripts/remove_legacy_mcp_alert_path.py --apply` 가 `app/mcp_server.py`
에 만드는 변경. 실제 라인 번호는 환경마다 다르므로 anchor 본문 기준.

## 1. `_track()` 함수 끝 — 경로 B 제거

```diff
     # Tier-aware alert.
     asyncio.create_task(_notify_mcp_tool(
         tool_name=tool_name,
         classification=_classify(ua),
         ip=ip, user_agent=ua,
         is_paid_tool=False,
     ))
-    # Existing cooldown-gated alert preserved verbatim.
-    now = time.monotonic()
-    if now - _last_notified.get(tool_name, 0) < _NOTIFY_COOLDOWN_SECONDS:
-        return
-    _last_notified[tool_name] = now
-    asyncio.create_task(_tg_notify(f"x402watch MCP: {tool_name}"))
```

`_track()`은 이제 경로 A(`_notify_mcp_tool`) 호출로 끝난다.

## 2. 모듈 레벨 변수 정의 제거 (self-verify 조건부)

경로 B가 유일 사용처일 때만 — 패처가 제거 후 잔존 카운트로 판정:

```diff
-_last_notified: dict[str, float] = {}
-_NOTIFY_COOLDOWN_SECONDS = 300
```

다른 모듈/함수가 이 심볼을 참조하면 정의는 **보존**되고 패처가
`◌ ... still used — kept` 를 출력한다.

## 3. `import time` 제거 (self-verify 조건부)

경로 B의 `time.monotonic()` 가 `time.` 의 유일 사용처일 때만:

```diff
 import asyncio
 import logging
 import os
-import time
 from typing import Any
```

`time.` 가 다른 곳에 있으면 import 보존.

## 보존되는 것 (변경 없음)

- `async def _tg_notify(...)` **함수 정의** — payment 알림 등 다른
  코드가 호출할 수 있어 유지. 이번 fix는 `_track()` 안의 **호출**만 제거.
- 경로 A 전체: `_classify`, `_notify_mcp_tool`, `_stats_write`,
  `_get_http_request` UA/IP 추출 블록.
- `_stats_write({"kind": "mcp_call", ...})` — stats.jsonl 로깅 그대로.
- 5개 `@mcp.tool` 함수, FastMCP 서버 설정.

## 결과 동작

| 상황 | fix 전 | fix 후 |
|---|---|---|
| Tier 0 단일 UA 7h burst (오늘 2026-05-21) | 경로 B로 200+ 발 | 경로 A 24h dedupe → **1발** |
| Tier 2 (Cursor), 한 IP, tool 1개 반복 | 경로 A 1발 + 경로 B 5분당 1발 | 경로 A `{tool}\|{ip}` 5분당 1발 |
| Tier 4/5 (Smithery/curl) | 경로 A는 무시(daily), 경로 B 5분당 1발 | 알림 0 (경로 A daily-only, 경로 B 없음) |

핵심: tool 호출당 텔레그램 발사 경로가 **2개 → 1개**. 남은 경로 A는
tier-aware + dedupe가 제대로 걸린다.
