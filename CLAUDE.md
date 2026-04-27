# x402watch

## Project Overview
- **Wash-filtered intelligence layer for the x402 ecosystem**
- 4축 차별화: 워시 필터 / 공공 데이터 / 시계열 / AI 네이티브
- 도메인: x402.printmoneylab.com
- GitHub: printmoneylab/x402watch

## Tech Stack
- **Frontend**: Next.js 16 (App Router) + TypeScript + Tailwind v4
- **Backend**: FastAPI + FastMCP (Python, Oracle 서버 168.138.195.65)
- **DB**: PostgreSQL + TimescaleDB + Redis
- **AI**: Claude Haiku 4.5
- **RPC**: Alchemy (EVM) + Helius (Solana)
- **Payment**: x402 SDK 2.8.0
- **Chains**: Base, Solana, Polygon, Arbitrum

## Coding Style
- TypeScript strict mode
- Functional components + hooks
- shadcn/ui for components
- Server Components 우선, Client는 필요 시만
- 환경변수 `.env.local` (절대 commit 금지)

## KR Crypto 학습 사항 (반드시 적용)
1. MCP transport는 항상 `/mcp` (절대 `/sse` 금지)
2. FastMCP 도구 정의는 메인 블록 안 (`if __name__` 뒤 금지)
3. FastMCP는 명시적 파라미터만 (`*args`/`**kwargs` 비허용)
4. mcp-publisher 설명 100자 제한
5. systemd는 `-u` 플래그 (stdout 버퍼링 끄기)
6. 알림 6시간 시간 기반 쿨다운
7. tenacity retry + `asyncio.Lock` 적용
8. Redis 1시간 캐시
9. API 키 코드 commit 절대 금지
10. `.env`, `.env.local`은 `.gitignore`에
11. 환율은 exchangerate-api.com (USD/KRW)
12. 결제 IP 자동 분석 (데이터센터 식별)
13. Bazaar는 v2 extensions 사용
14. Smithery transport `/mcp`
15. 도구 정의 위치 메인 블록 안

## Brand Policy
- PrintMoneyLab 브랜드만 노출
- Moa 실명/얼굴 비공개
- 콘텐츠 톤: 방법론 공개, 직접 폭로 금지

## Payment Model
- 암호화폐만 (Stripe 미사용)
- Pro Tier: USDC Prepaid Credits (Base/Solana/Polygon)
- API: x402 직접 결제
