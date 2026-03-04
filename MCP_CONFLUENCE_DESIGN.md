# Confluence MCP 설계서 (In-house Confluence)

## 1. 목적과 범위
- 목적: 인하우스 Confluence(Data Center/Server) 지식을 LLM이 안전하고 일관되게 활용하도록 MCP 서버를 구축한다.
- 1차 목표: 읽기/검색 중심 고신뢰 도구를 우선 제공한다.
- 2차 목표: 인덱싱(하이브리드 검색)과 제한적 쓰기 자동화를 단계적으로 확장한다.
- 원칙: 공식 REST API(`/rest/api`)를 기본 축으로 하고, 비공식 API(예: likes)는 선택 기능으로 격리한다.

## 2. 핵심 설계 원칙
- 안정성 우선: 공식 문서 기반 API를 우선 지원한다.
- 권한 정합성: 호출 주체의 Confluence 권한과 MCP 노출 범위를 정합하게 맞춘다.
- 최소 권한: 스페이스/작업 단위 allowlist를 기본값으로 한다.
- 관측 가능성: 모든 툴 호출에 감사 로그/추적 ID를 부여한다.
- 점진적 확장: Read-only -> Hybrid Index -> Write 순으로 단계 확장한다.

## 3. 목표 아키텍처

### 3.1 컴포넌트
- MCP Server
  - Tool Router: MCP tool name -> Confluence endpoint 매핑
  - Policy Engine: space allowlist, operation allowlist, payload limits
  - Auth Layer: PAT 또는 OAuth2 토큰 관리
  - Response Normalizer: 공통 출력 JSON 스키마 변환
  - Audit Logger: 요청자, contentId, action, 결과코드 기록
- Confluence Connector
  - REST client, pagination, retry/backoff, rate-limit 대응
- Optional Indexer (Phase 2)
  - `content/scan` 기반 증분 수집
  - 검색 인덱스(키워드/벡터) + ACL 메타데이터 저장

### 3.2 호출 흐름 (Read Tool)
1. LLM Host -> MCP `confluence_search_cql`
2. MCP Policy 검사(스페이스/파라미터 제한)
3. Confluence REST 호출
4. 응답 정규화 + 민감정보 마스킹
5. 결과 + source 링크 + traceId 반환

### 3.3 호출 흐름 (Write Tool)
1. LLM Host -> MCP `confluence_update_page`
2. 강한 정책 검사(대상 스페이스/템플릿/최대 길이)
3. 최신 version 조회
4. `version.number + 1` 적용하여 PUT
5. 변경 감사 로그 기록 및 결과 반환

## 4. 인증/권한 모델

### 4.1 옵션 A: 서비스 계정 + PAT (PoC 기본)
- 장점: 구현 단순, 빠른 도입
- 단점: 서비스 계정 권한이 곧 LLM 권한
- 필수 통제
  - LLM 전용 스페이스 분리
  - Tool별 space allowlist 강제
  - 민감 스페이스 denylist 하드코딩

### 4.2 옵션 B: 사용자별 OAuth2 (운영 권장)
- 장점: 사용자 권한 정합성 최고
- 단점: 토큰 발급/갱신/세션 연계 복잡
- 적용 시점: 사내 전사 확대 또는 민감 데이터 포함 시

### 4.3 비권장
- Basic Auth 상시 자동화 사용은 지양한다.

## 5. MCP Tool 카탈로그 (최대 활용 기준)

### 5.1 Read/Search Core
1. `confluence_search_cql`
- 목적: CQL 기반 검색
- 매핑: `GET /rest/api/content/search?cql=...`
- 입력
  - `cql` (string, required)
  - `limit` (int, default 25, max 100)
  - `cursor` or `start` (optional)
  - `expand` (array, optional; allowlist 기반)
  - `spaces` (array, optional; 정책상 허용 범위 내)
- 출력
  - `items[]`: id, title, type, spaceKey, url, lastModified
  - `pageInfo`: nextCursor/hasMore
  - `traceId`

2. `confluence_get_content`
- 목적: 단일 페이지/블로그 상세 조회
- 매핑: `GET /rest/api/content/{id}?expand=...`
- 입력: `id`, `expand[]`, `includeRestrictedMetadata`(default false)
- 출력: id, title, body(storage/view), version, labels, space, url, traceId

3. `confluence_get_labels`
- 목적: 문서 라벨 조회
- 매핑: `GET /rest/api/content/{id}/label`

4. `confluence_get_children`
- 목적: 트리 탐색
- 매핑: `GET /rest/api/content/{id}/child/page`

5. `confluence_get_attachments`
- 목적: 첨부 목록 조회
- 매핑: `GET /rest/api/content/{id}/child/attachment`

6. `confluence_get_comments`
- 목적: 댓글 조회
- 매핑: `GET /rest/api/content/{id}/child/comment`

7. `confluence_scan_content` (Phase 2)
- 목적: 대량 동기화/인덱싱
- 매핑: `GET /rest/api/content/scan`

8. `confluence_get_likes` (Optional/Experimental)
- 목적: 인기 신호 보조
- 매핑: `GET /rest/likes/1.0/content/{id}/likes`
- 주의: 비공식/비문서화 가능성으로 feature flag 기본 OFF

### 5.2 Write/Automation (Phase 3 이후)
1. `confluence_create_page`
- 매핑: `POST /rest/api/content`
- 정책
  - 허용 스페이스 제한
  - 허용 부모 페이지 제한(optional)
  - 허용 템플릿 제한

2. `confluence_update_page`
- 매핑: `PUT /rest/api/content/{id}`
- 정책
  - 현재 version 조회 후 +1 강제
  - max content length 제한
  - dry-run 모드 지원

3. `confluence_add_label`
- 매핑: 라벨 관련 REST endpoint

4. `confluence_add_comment`
- 매핑: 댓글 생성 endpoint

## 6. 보안/가드레일 설계

### 6.1 데이터 경계
- `ALLOWED_SPACES`: 운영 필수
- `DENIED_SPACES`: 민감 영역 강제 차단
- 첨부파일 다운로드 제한
  - MIME allowlist
  - 파일 크기 제한
  - 개수 제한

### 6.2 툴 실행 통제
- read/write 툴 분리 및 write 기본 비활성화
- write 툴은 환경변수 + 정책 파일 모두 충족 시만 활성화
- 위험 파라미터(광범위 CQL, 대량 limit) 자동 축소

### 6.3 프롬프트 인젝션 대응
- 문서 본문 내 tool-call 유도 텍스트를 신뢰하지 않음
- MCP 정책 레이어에서 최종 허용 여부 결정
- 고위험 작업은 2단계 확인 플래그(운영 옵션)

### 6.4 감사/모니터링
- 필수 로그 필드
  - timestamp, userId(or service principal), tool, contentId, spaceKey, status, latencyMs, traceId
- 보안 이벤트
  - 정책 차단 건수
  - denied space 접근 시도
  - write 실패/충돌(version conflict)

## 7. 데이터/응답 표준
- 모든 툴 응답 공통 필드
  - `traceId`, `sourceSystem`="confluence", `fetchedAt`
- 에러 공통 포맷
  - `error.code`, `error.message`, `error.retryable`, `traceId`
- 링크 표준화
  - `webUrl`, `apiUrl` 분리 제공

## 8. 성능 및 신뢰성
- Pagination 기본 적용
- Retry 정책
  - 429/5xx 지수 백오프
- Timeout
  - search/read: 5~10s
  - write: 10~20s
- Cache
  - read-through TTL 캐시(짧은 TTL)
  - 민감 콘텐츠는 캐시 제외 가능

## 9. 단계별 실행 로드맵

### Phase 0: 준비
- Confluence 버전/인증 방식 확인
- 대상 스페이스 분류(허용/차단)
- 서비스 계정 또는 OAuth 클라이언트 준비

### Phase 1: Read-only PoC (2~3주)
- 구현 툴
  - `search_cql`, `get_content`, `get_labels`, `get_children`
- 산출물
  - MCP 서버 기본 골격
  - 정책 엔진 v1
  - 감사 로그 v1
- 완료 기준
  - 상위 20개 대표 질의 성공률 >= 95%
  - 민감 스페이스 차단 100%

### Phase 2: Hybrid Search (2~4주)
- `scan_content` 기반 증분 ETL
- 인덱스 질의 + 원문 재검증 결합
- 완료 기준
  - 응답 지연 30% 이상 개선
  - 검색 재현율/정확도 기준치 달성

### Phase 3: Controlled Write (2~3주)
- `create_page`, `update_page`, `add_comment` 제한 오픈
- version conflict 처리/재시도 구현
- 완료 기준
  - 승인된 스페이스 외 write 0건
  - 감사 추적 누락 0건

### Phase 4: User-context Auth (선택)
- OAuth2 전환/병행
- 사용자별 ACL 정합성 검증

## 10. 개발 백로그 (우선순위)
1. MCP tool interface 및 공통 response schema 정의
2. Confluence REST client (auth, retry, pagination)
3. Policy engine (space/tool/size restrictions)
4. `search_cql` 구현
5. `get_content` + expand allowlist 구현
6. 감사 로깅 + traceId 상관관계
7. 통합 테스트(권한/차단/에러/대량 페이지)
8. `scan_content` + 인덱서 연동
9. write tool 제한 오픈

## 11. 테스트 전략
- 단위 테스트
  - endpoint builder, policy evaluator, error mapper
- 통합 테스트
  - 실제/스테이징 Confluence 대상 smoke test
- 보안 테스트
  - deny space 접근 시도
  - 과도한 limit/cql 인젝션성 입력
  - write 툴 비활성 상태 강제 검증
- 회귀 테스트
  - Confluence 버전 업 시 API 호환성 점검

## 12. 운영 정책 (초안)
- 기본 모드: Read-only
- 실험 기능: likes API는 `EXPERIMENTAL_LIKES=true`일 때만
- 변경 관리
  - write tool 활성화는 변경 승인 절차 필수
- 비밀 관리
  - PAT/OAuth secret은 vault 사용
  - 로그에 토큰/본문 민감값 저장 금지

## 13. 권장 기본 설정값
- `DEFAULT_LIMIT=25`
- `MAX_LIMIT=100`
- `MAX_BODY_CHARS=20000`
- `REQUEST_TIMEOUT_MS=10000`
- `WRITE_ENABLED=false`
- `ALLOWED_EXPANDS=body.storage,body.view,version,space,history,lastUpdated`

## 14. 리스크와 대응
- 비공식 endpoint 변경 리스크(likes)
  - 대응: feature flag + graceful fallback
- 과권한 서비스 계정 리스크
  - 대응: 스페이스 분리 + 최소권한 재검토 주기
- 프롬프트 인젝션 유도 리스크
  - 대응: 정책 기반 최종 통제, 고위험 write 기본 차단

## 15. 즉시 실행 To-do (이번 주)
1. PoC 스코프 확정(Read 4개 툴)
2. 대상 스페이스 allowlist 확정
3. 인증 방식 1차 결정(PAT 시작 여부)
4. MCP tool JSON schema 작성
5. staging Confluence 연결 테스트

---

## 부록 A. 추천 MCP Tool I/O 예시

### A-1. `confluence_search_cql` request
```json
{
  "cql": "space=DEVOPS and type=page order by lastmodified desc",
  "limit": 25,
  "expand": ["space", "version"]
}
```

### A-2. `confluence_search_cql` response
```json
{
  "traceId": "cfx-20260304-001",
  "sourceSystem": "confluence",
  "fetchedAt": "2026-03-04T10:00:00Z",
  "items": [
    {
      "id": "123456",
      "title": "Deploy Runbook",
      "type": "page",
      "spaceKey": "DEVOPS",
      "webUrl": "https://confluence.example.com/pages/viewpage.action?pageId=123456",
      "lastModified": "2026-02-28T09:11:00Z"
    }
  ],
  "pageInfo": { "hasMore": false }
}
```

### A-3. `confluence_update_page` request
```json
{
  "id": "123456",
  "title": "Deploy Runbook",
  "bodyStorage": "<p>updated</p>",
  "expectedVersion": 42,
  "minorEdit": true
}
```

### A-4. `confluence_update_page` 처리 규칙
- 서버는 최신 version을 조회한 뒤 불일치 시 `409 conflict`를 반환한다.
- 일치 시 `version.number = latest + 1`로 강제 업데이트한다.
