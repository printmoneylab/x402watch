# Cloudflare 클라이언트 IP fix — 변경 전후 (EXPECTED DIFF)

`scripts/fix_mcp_client_ip.py --apply` 가 `app/mcp_server.py`
`_track()` 에 만드는 변경.

## 코드 diff — `_track()` 의 IP 우선순위 블록

```diff
             xff = _req.headers.get("x-forwarded-for", "")
+            # CF client-IP fix — cf-connecting-ip is Cloudflare's
+            # contractual real-visitor header; trust it first.
+            # x-forwarded-for[0] is NOT trustworthy behind CF.
+            # Order matches app/api.py _client_ip().
             ip = (
-                xff.split(",")[0].strip()
-                or _req.headers.get("x-real-ip", "").strip()
-                or _req.headers.get("cf-connecting-ip", "").strip()
+                _req.headers.get("cf-connecting-ip", "").strip()
+                or _req.headers.get("x-real-ip", "").strip()
+                or xff.split(",")[0].strip()
                 or (_req.client.host if _req.client else "")
             )
```

순서: `cf-connecting-ip` → `x-real-ip` → `x-forwarded-for[0]` → `client.host`.
`app/api.py` 의 `_client_ip()` 와 동일한 우선순위.

## IP 캡처 동작 표

| 헤더 상황 (CF 뒤) | fix 전 (`xff[0]` 최우선) | fix 후 (`cf-connecting-ip` 최우선) |
|---|---|---|
| `XFF: 104.22.31.138, 212.11.41.202` + `CF-Connecting-IP: 212.11.41.202` | **104.22.31.138** (CF edge — 버그) | **212.11.41.202** (진짜) |
| `XFF: 212.11.41.202` + `CF-Connecting-IP: 212.11.41.202` | 212.11.41.202 (우연히 맞음) | 212.11.41.202 |
| `CF-Connecting-IP` 만 있음 (XFF 없음) | x-real-ip→cf-connecting-ip로 fallback | cf-connecting-ip 즉시 |
| 클라이언트가 `XFF` 위조 시도 | 위조값 채택 (취약) | CF가 보장한 `cf-connecting-ip` 채택 (안전) |
| 헤더 전무 (로컬 직접 호출) | `client.host` (127.0.0.1) | `client.host` (127.0.0.1) — 동일 |

## 검증된 동작 (self-test)

패처 self-test 시뮬:
- `XFF[0]=104.22.31.138`(CF edge), `cf-connecting-ip=212.11.41.202`
  → fix 후 `ip = 212.11.41.202` ✓
- `cf-connecting-ip` 부재 + `x-real-ip=212.11.41.202` → `212.11.41.202` ✓
- 헤더 전무 → `client.host` ✓

## 보존 (변경 없음)

- `_track()` 의 UA 추출, `_stats_write`, 경로 A(`_notify_mcp_tool`).
- `_get_http_request` import, `try/except RuntimeError` 가드.
- uvicorn / 서비스 파일 / FastMCP transport 설정 — 변경 불필요
  (uvicorn `proxy_headers` 는 `client.host` 만 다시 쓰고 헤더는
  건드리지 않음 — `_track()` 은 헤더를 직접 읽음).
- `app/api.py` `_client_ip()` — 이미 정상, 미변경.

## 전제

이 패치는 **Nginx가 `CF-Connecting-IP` 헤더를 백엔드로 전달**할 때
즉시 효과. Nginx는 underscore 없는 헤더를 기본 pass-through하므로
대부분 그대로 동작. CF_IP_FIX_DEPLOY.md Step 1a에서 Nginx가 그
헤더를 비우거나 차단하는 게 확인되면 (드묾) Step 3-A의 Nginx
`proxy_set_header` 도 함께 적용.
