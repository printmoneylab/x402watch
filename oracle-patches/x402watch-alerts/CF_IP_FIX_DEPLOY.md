# Cloudflare 진짜 클라이언트 IP — 진단 + fix 배포

증상: `stats.jsonl`의 `mcp_call` 행 `ip` 필드가 Cloudflare edge IP
(예 `104.22.31.138`)로 찍힘. Nginx access log엔 같은 시각 진짜 IP
(`212.11.41.202`)가 보임 → **진짜 IP는 박스에 도달, `_track()`에서
우선순위 경쟁에 짐**.

코드 근거: `app/api.py`의 `_client_ip()`는 이미 `cf-connecting-ip`
최우선(정상). `app/mcp_server.py`의 `_track()`만 `x-forwarded-for[0]`
최우선(회귀). CF 뒤에서 `X-Forwarded-For[0]`는 신뢰 불가 —
Cloudflare의 계약 헤더는 `CF-Connecting-IP`.

대상: `app/mcp_server.py` 하나. `x402watch-mcp.service`만 재시작.
`api.py`는 이미 정상이라 손대지 않음.

---

## Step 1 — 진단 (읽기 전용)

### 1a. Nginx config — CF-Connecting-IP가 백엔드로 전달되나

```bash
ls -la /etc/nginx/sites-enabled/
# /mcp (port 8453) 를 처리하는 server block 찾기
grep -rlE "8453|/mcp|x402" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null

# 그 config에서 헤더 전달 + realip 설정 확인 (파일명은 위 결과로 치환)
CFG=$(grep -rlE "8453|/mcp" /etc/nginx/sites-enabled/ 2>/dev/null | head -1)
echo "config = $CFG"
grep -nE "proxy_set_header|real_ip|set_real_ip_from|cf-connecting|X-Forwarded|X-Real-IP|proxy_pass|server_name|log_format|access_log" "$CFG"
```

**판정**:
- `real_ip_header CF-Connecting-IP` + `set_real_ip_from` 존재 →
  Nginx `$remote_addr`가 이미 진짜 IP로 갱신됨. `proxy_set_header
  X-Real-IP $remote_addr` 가 있으면 백엔드는 진짜 IP를 X-Real-IP로
  받음 → **시나리오 C** (코드 우선순위만 고치면 끝).
- `proxy_set_header` 에 `CF-Connecting-IP` 줄이 없음 → Nginx가 그
  헤더를 명시적으로 세팅하진 않지만, **헤더 이름에 underscore가
  없으므로 Nginx는 기본적으로 클라이언트(CF) 헤더를 백엔드로
  pass-through함** → 백엔드는 여전히 CF-Connecting-IP를 받음 →
  역시 **시나리오 C**.
- config에 `proxy_set_header CF-Connecting-IP ""` 같이 비우는 줄이
  있거나, 헤더 화이트리스트로 차단 → **시나리오 A** (Nginx fix 필요).

### 1b. 헤더가 백엔드(FastMCP)까지 실제 도달하나

Oracle 안에서 백엔드에 직접 curl — Nginx를 우회해 헤더를 명시:

```bash
# MCP는 streamable-http 세션이 필요 → initialize로 서버 도달만 확인
curl -sS -m 15 http://127.0.0.1:8453/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -H "CF-Connecting-IP: 203.0.113.77" \
  -H "X-Forwarded-For: 104.22.31.138, 203.0.113.77" \
  -H "User-Agent: CFIPProbe/1.0" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"CFIPProbe","version":"1.0"}}}' \
  | head -c 200
echo
```
이건 서버 reachability 확인용. `_track()`은 tool 호출에서만 불리므로
`mcp_call` stats는 이 probe로 안 생김(정상).

진짜 IP 캡처 검증은 **fix 적용 후** 자연 트래픽 또는 실제 tool 호출로
(Step 4). 1b는 "백엔드 reachable + Nginx가 /mcp를 8453으로 보냄"까지.

### 1c. FastMCP / uvicorn — 추가 설정 필요 여부

```bash
grep -nE "mcp.run|transport|streamable|uvicorn|proxy_header|forwarded" \
  /home/ubuntu/x402watch/app/mcp_server.py
```

**결론(코드 분석 확정)**: uvicorn의 `proxy_headers` / `forwarded_allow_ips`
는 `request.client.host` 만 다시 씀 — **요청 헤더는 절대 추가/삭제하지
않음**. `_track()`은 `_req.headers.get("cf-connecting-ip")` 로 헤더를
직접 읽으므로 uvicorn 설정과 무관. → uvicorn/서비스 파일 변경 불필요.
이 fix는 순수 우선순위 재정렬.

### 1d. Cloudflare 측 (Moa가 CF 콘솔에서 — 선택)

`CF-Connecting-IP` 는 Cloudflare가 **항상** origin으로 보내는 기본
헤더(설정 불필요). CF 대시보드 변경은 거의 필요 없음. 1b/Step 4에서
진짜 IP가 안 잡힐 때만 CF → Network → "Add visitor IP headers" 확인.

---

## Step 2 — 시나리오 판정

| 1a 결과 | 시나리오 | fix |
|---|---|---|
| Nginx가 CF-Connecting-IP를 pass-through (대부분) | **C** | Step 3-C (패처만) |
| Nginx가 CF-Connecting-IP를 비우거나 차단 | **A + C** | Step 3-A → Step 3-C |

거의 항상 **C**. Nginx는 underscore 없는 헤더를 기본 pass-through.

---

## Step 3-C — 코드 우선순위 fix (시나리오 C, 거의 항상 필요)

```bash
cd /home/ubuntu/x402watch
# 산출물 SCP 후 (Oracle: oracle-patches-x402watch-alerts/)
cp oracle-patches-x402watch-alerts/fix_mcp_client_ip.py scripts/fix_mcp_client_ip.py

venv/bin/python scripts/fix_mcp_client_ip.py            # dry-run
venv/bin/python scripts/fix_mcp_client_ip.py --apply    # 백업 자동
sudo systemctl restart x402watch-mcp
sudo systemctl is-active x402watch-mcp                   # expect: active
```

## Step 3-A — Nginx fix (시나리오 A일 때만)

```bash
CFG=$(grep -rlE "8453|/mcp" /etc/nginx/sites-enabled/ 2>/dev/null | head -1)
sudo cp "$CFG" "$CFG.bak.cf-ip-fix-$(date +%Y%m%d-%H%M)"
# /mcp location 블록의 proxy_pass 줄 아래에 추가 (편집기로):
#   proxy_set_header CF-Connecting-IP $http_cf_connecting_ip;
#   proxy_set_header X-Real-IP        $remote_addr;
#   proxy_set_header X-Forwarded-For  $proxy_add_x_forwarded_for;
sudo nginx -t                       # 반드시 통과 확인
sudo systemctl reload nginx         # reload (무중단, restart 아님)
```
주의: 같은 `nginx.conf` 안에 KR Crypto(`api.printmoneylab.com`)와
프론트(`x402.printmoneylab.com`) server block이 있으면 **x402watch
MCP server block 안에서만** 수정. 다른 server block 미변경.

---

## Step 4 — 검증

```bash
# 4a. PR #36 v2.4 헤더 유지 (이 fix와 무관)
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep -i x-x402-rewriter
# expect: x-x402-rewriter: v2.4

# 4b. mcp_server import 정상
cd /home/ubuntu/x402watch
venv/bin/python -c "from app import mcp_server; print('mcp_server import OK')"

# 4c. MCP probe — 서버 reachable
curl -sS -m 15 https://api.x402.printmoneylab.com/mcp \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}' \
  | head -c 200; echo

# 4d. 진짜 IP 캡처 확인 — fix 적용 후 자연 트래픽 한 건 대기 후:
tail -5 /home/ubuntu/x402watch/var/stats.jsonl
# expect: mcp_call 행의 ip 가 104.22.x.x (CF edge) 가 아니라
#         Nginx access log와 같은 진짜 클라이언트 IP

# 4e. 같은 시각 Nginx access log의 진짜 IP와 대조
sudo tail -20 /var/log/nginx/access.log | grep -E "/mcp"
# stats.jsonl ip == access.log 의 진짜 IP 면 fix 성공
```

**기대 결과**: 4d의 `mcp_call.ip` 가 4e의 Nginx 진짜 IP와 일치.
CF edge IP(`104.22.x.x` / `172.6x.x.x`)는 더 이상 안 나옴.

---

## Step 5 — 롤백

```bash
# 코드 fix 롤백
cd /home/ubuntu/x402watch/app
cp "$(ls -t mcp_server.py.bak.cf-ip-fix-* | head -1)" mcp_server.py
sudo systemctl restart x402watch-mcp

# Nginx fix 롤백 (시나리오 A를 적용했을 때만)
CFG=$(grep -rlE "8453|/mcp" /etc/nginx/sites-enabled/ 2>/dev/null | head -1)
sudo cp "$CFG.bak.cf-ip-fix-"* "$CFG"
sudo nginx -t && sudo systemctl reload nginx
```

패처는 idempotent — 재적용해도 "already patched". 롤백은 fix 자체에
문제가 있을 때만 (롤백 시 CF edge IP 회귀).

---

## 영향 범위

- `app/mcp_server.py` 한 파일, `x402watch-mcp.service` 재시작만.
- `app/api.py` `_client_ip()` 는 이미 cf-connecting-ip 최우선 — 변경 없음.
- 시나리오 A 적용 시 Nginx reload(무중단). KR Crypto / 프론트 server
  block 미변경.
- PR #36 v2.4 / 알림 dedupe fix / merchant feed / 결제 경로 무관.
