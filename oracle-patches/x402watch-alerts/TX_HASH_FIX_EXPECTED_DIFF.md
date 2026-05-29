# P3 fix — tx_hash on stats.jsonl payment events — 변경 전후 (EXPECTED DIFF)

`scripts/add_tx_hash_to_payment.py --apply` 가 `app/api.py` 에 만드는
변경. 실제 라인 번호는 환경마다 다르므로 anchor 본문 기준
(`_stats_write({"kind": "payment"` / `"post_settle_fail"` / `_notify_post_settle(`).

## 1. 모듈 레벨 헬퍼 추가

마지막 top-level `import ...` 줄 바로 다음 라인에 삽입.

```diff
 import asyncio
 import logging
 ...  (마지막 import 들)
 from x402.http.middleware.fastapi import PaymentMiddlewareASGI
+
+def _decode_x_payment_response(header_value: str) -> dict:
+    """Decode the x402 `X-Payment-Response` header (base64 JSON).
+
+    Returns ``{"tx_hash": ..., "network": ..., "buyer_wallet": ...}``.
+    Every field is ``None`` on any failure (empty header, malformed
+    base64, malformed JSON, ``success != True``). Defensive — never
+    raises into the request path."""
+    if not header_value:
+        return {"tx_hash": None, "network": None, "buyer_wallet": None}
+    try:
+        import base64
+        import json as _json
+        decoded = _json.loads(base64.b64decode(header_value).decode())
+        if decoded.get("success"):
+            return {
+                "tx_hash": decoded.get("transaction"),
+                "network": decoded.get("network"),
+                "buyer_wallet": decoded.get("payer"),
+            }
+    except Exception as _e:
+        log.warning("x-payment-response decode failed: %s", _e)
+    return {"tx_hash": None, "network": None, "buyer_wallet": None}
+
```

`log` 가 모듈 레벨에 없으면 `except Exception:` 가지가 자동으로
다음으로 바뀐다 (패처가 AST로 감지):

```python
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "x-payment-response decode failed", exc_info=True
        )
```

`base64` / `json` 은 함수 안 lazy import — 모듈 import 블록은 무변경.

## 2. payment `_stats_write` (api.py:~2020)

`_enrich_and_notify` 내부:

```diff
+        settle_info = _decode_x_payment_response(response.headers.get("x-payment-response", ""))
         _stats_write({
             "kind": "payment",
             "endpoint": endpoint_label,
             "amount_usd": amount,
             "ip": ip,
             "ipinfo": ipinfo,
             "total_count": stats.get("total_count"),
-            "daily_count": stats.get("daily_count"),
+            "daily_count": stats.get("daily_count"),
+            "tx_hash": settle_info["tx_hash"],
+            "network": settle_info["network"],
+            "buyer_wallet": settle_info["buyer_wallet"],
         })
```

- `settle_info = …` 줄은 `_stats_write` 호출과 같은 indent.
- 3 신규 키는 기존 마지막 key (`daily_count`) 와 같은 column 에 정렬.
- 기존 마지막 key 에 trailing comma 가 없으면 패처가 자동으로 추가.

## 3. post_settle_fail `_stats_write` + `_notify_post_settle` (api.py:~1965~1980)

`payment_notify_middleware` 의 5xx-after-X-PAYMENT 분기:

```diff
+        settle_info = _decode_x_payment_response(response.headers.get("x-payment-response", ""))
         _stats_write({
             "kind": "post_settle_fail",
             "endpoint": _endpoint_label,
             "status": response.status_code,
             "ip": _ip,
-            "amount_usd": _amount,
+            "amount_usd": _amount,
+            "tx_hash": settle_info["tx_hash"],
+            "network": settle_info["network"],
+            "buyer_wallet": settle_info["buyer_wallet"],
         })
         _asyncio_tg.create_task(_notify_post_settle(
             endpoint=_endpoint_label,
             status=response.status_code,
             ip=_ip,
-            payer_wallet=None,
-            tx_hash=None,
+            payer_wallet=settle_info["buyer_wallet"],
+            tx_hash=settle_info["tx_hash"],
             amount_usd=_amount,
         ))
```

`settle_info` 는 두 호출에서 공유. `_stats_write` 가 먼저든 `_notify_post_settle`
가 먼저든 같은 enclosing function 안이면 둘 다 참조 가능 — 패처가
enclosing function 일치 여부를 AST 로 강제 검증.

## 보존되는 것 (변경 없음)

- 모듈 import 블록 (base64/json/anything) — 헬퍼 안 lazy import.
- `payment_notify_middleware` 시그니처 / `call_next` 흐름 / 다른 분기
  (정상 200, 비결제 요청 등) — 손대지 않음.
- `_enrich_and_notify` 의 dedupe / owner_test / redis_client / `_format_alert`
  텔레그램 포맷 로직 — 손대지 않음.
- 기존 7/5 dict 필드 (kind/endpoint/amount_usd/ip/ipinfo/total_count/daily_count
  + kind/endpoint/status/ip/amount_usd) — 위치/값/순서 그대로.
- `_notify_post_settle` 의 `endpoint`/`status`/`ip`/`amount_usd` kwarg — 그대로.
- PR #36 v2.4 `X402ResourceRewriter` ASGI 래핑 — 무관.
- merchant feed indexer / dispute API / MCP server / Tier 2/3 daily / CF IP
  fix — 모두 다른 파일이라 무관.

## 결과 스키마

`stats.jsonl` 의 새 `payment` 이벤트 (예시):

```json
{
  "ts": "2026-05-29T13:42:11+09:00",
  "kind": "payment",
  "endpoint": "/api/v1/services/833049/wash-detail",
  "amount_usd": 0.01,
  "ip": "1.2.3.4",
  "ipinfo": {"city": "Tokyo", "country": "JP"},
  "total_count": 42,
  "daily_count": 3,
  "tx_hash": "0x8f3d1a2b4c5e6f7a...",
  "network": "base",
  "buyer_wallet": "0x1234..."
}
```

디코드 실패 시 (헤더 없음 / 형식 깨짐 / `success: false`):

```json
{
  "ts": "...",
  "kind": "payment",
  "endpoint": "...",
  "...": "...",
  "tx_hash": null,
  "network": null,
  "buyer_wallet": null
}
```

기존 7 필드는 그대로, 신규 3 필드만 null. 텔레그램 알림은 무영향.

## 결과 동작

| 상황 | fix 전 | fix 후 |
|---|---|---|
| 정상 결제 (X-Payment-Response 헤더 있음) | tx_hash 미기록 | tx_hash/network/buyer_wallet 실값 기록 |
| 헤더 없음 (구버전 x402, 비정상 settle) | (그대로 기록) | 신규 3 필드 null, 나머지 정상 |
| 헤더 base64 깨짐 | (그대로 기록) | 신규 3 필드 null + log.warning 1줄 |
| 헤더 JSON 깨짐 | (그대로 기록) | 신규 3 필드 null + log.warning 1줄 |
| `success: false` (settle 실패) | (그대로 기록) | 신규 3 필드 null |
| post_settle_fail (5xx after X-PAYMENT) | tx_hash=None, payer_wallet=None 텔레그램 | settle_info 의 실값으로 알림 |
| stats.jsonl ↔ DB transactions 교차 | 불가 (공통 키 없음) | tx_hash 로 정확 매칭 가능 |
| 5월 6건 vs DB 1건 누락 추적 | 불가 | 5건 각각의 tx_hash + network 로 식별 |

핵심: payment 알림 / 결제 settle / DB 적재 자체는 변하지 않음. stats.jsonl
이 DB 와 같은 식별자 (`tx_hash`) 를 들고 다니게 되어 둘 사이의 일치 검증
이 가능해진다.
