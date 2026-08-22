# CLAUDE.md

코딩 에이전트를 위한 최상위 지침 — 이 저장소의 규칙, 모든 문서가 어디 있는지의
지도, 그리고 모르면 어렵게 다시 알아내야 하는 실무 지식.

**읽었으면 먼저 §0을 실행한다.**

---

## §0. 매 세션 시작 시 정합성 검증 (필수)

이 문서는 시간이 지나면 실제 저장소와 어긋난다. **작업을 시작하기 전에 반드시**
아래를 실행해 이 문서의 주장이 아직 사실인지 확인한다.

```bash
cd "D:/일/개인프로젝트/PDF_to_Notion"
find . -type f -not -path "./.git/*" -not -path "*/__pycache__/*" \
     -not -path "*/.pytest_cache/*" -not -path "./cache/*" -not -path "./output/*" | sort
ls pdf2md tests 2>/dev/null || echo "구현 미시작"
grep -c '^[A-Z_]*=' .env
head -8 PLAN.md | grep -o 'v[0-9]' | tail -1
git remote -v && git branch --show-current
gh issue list --repo Dunpark/pdf2md --state all --limit 10
```

| # | 이 문서의 주장 | 기대값 |
|---|---|---|
| 1 | 파일 목록 | §5의 트리와 일치 |
| 2 | 구현 진행 단계 | §4의 "현재 단계"와 일치 |
| 3 | `.env`에 키 2개 | `2` |
| 4 | PLAN 개정 버전 | `v2` |
| 5 | 리모트 | `origin → Dunpark/pdf2md` |
| 6 | 티켓 | `#1`~`#7`이 존재하고 제목이 `TICKET-001`~`TICKET-007` |

**어긋나면 → 작업을 진행하기 전에 이 문서를 먼저 고친다.**
갱신하지 않은 채로 다음 작업에 들어가지 말 것 — 이 문서가 틀리면 다음 세션이 틀린다.

---

## §1. Quick reference

실제로 실행해 확인한 명령만 적는다.

```bash
# 기존 Notion 파서 회귀 확인 — 반드시 reference/ 안에서 실행한다.
# 루트에서 bare `python -m pytest` 를 돌리면 reference/tests/ 를 수집하다 실패한다
# (그 테스트들이 `notes.*` 를 임포트하는데 루트에는 그 경로가 없다).
python -m pdf2md "Attention is all you need.pdf"  # → Gate A OK → output/{stem}.md + images/
                                                  #   캐시 히트 시 0.4s·네트워크 없음. 실 API 검증 완료(2026-08-22)
python -m pytest tests/ -q                        # → 30 passed (루트에서. bare pytest 금지 — 아래 함정 참조)
(cd reference && python -m pytest tests/ -q)     # → 36 passed

python -m pdf2md.strict                           # → self-check passed, exit 0
python -m pdf2md.mineru_api                       # → self-check passed (MockTransport, 네트워크 안 탐)
python --version                                  # → 3.13.15
gh auth status                                    # → Dunpark, scopes: repo/workflow/gist/read:org
```

### 어기면 안 되는 것

- **커밋 메시지·PR에 AI 크레딧을 넣지 않는다.** `Co-Authored-By`, `Generated with`
  류의 트레일러 금지.
- **다 됐다고 말하기 전에 명령을 실제로 돌린다.** 돌리지 못했으면 그렇게 보고한다.
- **`main`에 제품 코드를 직접 푸시하지 않는다.**
- 이슈·브랜치·커밋·PR 규약은 [ticket.md](ticket.md)에 있다. 여기에 복사하지 않는다.

---

## §2. Language

- 설계 문서(`CLAUDE.md`, `PLAN.md`)와 코드 주석은 **한국어**로 쓴다.
- 커밋 메시지, PR 본문, GitHub 이슈, `ticket.md`는 **영어**로 쓴다.
- 사용자와의 대화는 **한국어**로 한다.
- 위임한 에이전트에게는 결과를 한국어로 돌려달라고 요구한다.

---

## §3. Project context

`pdf2md <pdf-path>` — 학술 논문·리포트 PDF를 **형식이 보존된 마크다운**으로 변환한다.
산출물은 `output/{이름}.md` + `output/images/`.

**하지만 변환 자체가 핵심이 아니다.** MinerU를 비롯한 변환기들이 이미 이 일을 한다.
문제는 **인식 실패를 조용히 삼킨다**는 것이다. 결과물은 멀쩡해 보이는데 수식과 표가
뭉개져 있고, 원본과 대조하지 않으면 알 수가 없다.

> **틀린 수식은 없는 수식보다 나쁘다.**
> 이 프로젝트의 유일한 존재 이유는 **표현할 수 없는 것을 만나면 멈추고 보고하는 것**이다.
> 어떤 설계 판단이든 이 원칙과 충돌하면 이 원칙이 이긴다.

**범위 밖**: Notion 업로드(보류, [PLAN.md](PLAN.md) 부록), 로컬 MinerU 실행,
PDF→Markdown 변환기의 자체 구현.

상세 설계와 근거는 [PLAN.md](PLAN.md)가 단일 출처다.

---

## §4. 진행 경과

**현재 단계: Phase 1 완료(#6까지) — 실물 `output/{stem}.md` 확보. 다음은 #7(출력 품질 판정, 사용자 몫)**

| 시점 | 내용 |
|---|---|
| 2026-08-22 | HANDOFF.md 분석. 오픈소스 사전조사 → PDF→MD는 자체 구현하지 않기로 결정 |
| 〃 | 파서 후보 비교. Marker 후보였다가 **MinerU로 변경** (OmniDocBench 95.69 vs 71.30) |
| 〃 | 로컬 실행 불가 확인 — Intel Arc 140T는 **내장 GPU**라 CUDA 없음 → **MinerU 공식 API** |
| 〃 | PLAN v1 작성 → 사실 검증 → 오류 3건·누락 2건 수정 후 확정 |
| 〃 | 이식 시범 진행 후 **전량 롤백**. 백지 재시작 |
| 〃 | MinerU 토큰 인증 확인 / Notion 토큰·페이지·쓰기 권한 검증 완료 |
| 〃 | **최종 산출물을 Notion → 마크다운으로 변경. PLAN v2 개정** |
| 〃 | 티켓주도개발 규격 도입. `ticket.md` 신설, GitHub 저장소 연결 |
| 〃 | `notion_blank_quiz.py` 삭제 (용도 종료, 평문 토큰 제거) |
| 〃 | PLAN v2를 티켓 7개로 분해해 GitHub 이슈 #1~#7 발행. 마일스톤 3개·`wave-*` 라벨 5개 |
| 〃 | 병렬 워크플로우를 위해 PLAN의 파일 구조를 4모듈 → 6모듈로 분리 (근거는 PLAN.md "파일 구조") |
| 〃 | 첫 커밋 — `origin/main` 생성 (#1) |
| 〃 | #2 완료·머지 (PR #8) — `strict.py` 공유 타입 고정. `Violation`에 severity(위반/경고 2단계)·detail 추가 |
| 〃 | Wave 2를 worktree 격리 에이전트 3개로 병렬 수행 → PR #9(#4)·#10(#3)·#11(#5) 전부 머지. 22 tests. 실 API·실 ZIP은 여전히 미검증(#6 몫) |
| 〃 | #6 CLI 통합. 첫 실 API 실행에서 Gate A가 수식 5건 오탐 → 실측 스키마(equation은 `text` 키)로 gate_a 수정, `chart` 타입 추가. PLAN 스키마 표 실측 기준으로 개정. 재실행 Gate A OK → 실물 md 확보 |

### v2 변경의 파급

- **Gate B 전체 삭제.** 마크다운엔 길이 한도도 병합셀 제약도 없다. 2000자 분할·
  1000자 halt·미지원 마크업 sniffer·HTML→Notion 표 변환·업로더가 전부 불필요.
- **`reference/`가 통째로 무용지물.** HANDOFF의 전제였던 "완성된 Notion writer
  재사용"이 무효. 방치하되 삭제하지 않는다(되살릴 가능성 보존).
- **규모 축소.** 우리 도구가 더하는 것은 **Gate A + 정제** 둘뿐. 예상 200~300줄.

### 검증 완료된 사실 (재확인 불필요)

| 항목 | 결과 |
|---|---|
| MinerU API 과금 | **무료** — 공식 "目前暂无商业化收费计划" |
| MinerU 토큰 | 인증 확인. **유효기간 14일, 자동 갱신 없음** → 401 시 만료부터 의심 |
| MinerU 도달성 | `8.222.88.164` (Alibaba Cloud 싱가포르), HTTPS 200, 0.78s |
| MinerU 한도 | ≤200MB / **≤200페이지**, 50파일/분 |
| Notion (보류) | 통합·페이지·쓰기 권한 전부 검증 완료 — PLAN.md 부록에 보관 |

### 티켓 지도 (GitHub Issues, `Dunpark/pdf2md`)

**진행 상태의 단일 출처는 GitHub Issues다.** 여기 있는 것은 지도일 뿐이므로
상태를 여기에 적지 않는다 — `gh issue list --repo Dunpark/pdf2md`로 본다.

| Wave | 이슈 | 무엇 |
|---|---|---|
| 0 | #1 | Repo bootstrap |
| 1 | #2 | 공유 타입 · strict 리포트. **단독으로 먼저 끝내야 한다** |
| 2 | #3 · #4 · #5 | MinerU API · 캐시/출력 조립 · Gate A. **완전 병렬** |
| 3 | #6 | CLI 통합 (수렴점) |
| 4 | #7 | 실제 출력 평가 → 정제 범위 확정 (**사용자 판정 필요**) |

**Wave 2의 3중 병렬이 성립하는 조건은 두 가지뿐이다** — 세 모듈이 서로를 임포트하지
않고, 서로 다른 파일을 소유한다. 둘 다 PLAN.md "파일 구조"가 고정한다. #2를 건너뛰고
Wave 2를 시작하면 세 갈래가 각자 다른 데이터 모양을 가정해 #6에서 세 번 충돌한다.

정제 구현 티켓은 **아직 발행하지 않았다.** #7이 끝나기 전에는 범위를 알 수 없어
`ticket.md`가 요구하는 다섯 섹션을 채울 수 없다. 시작할 준비가 안 된 것이다.

### 다음 할 일

**#7 — 출력 품질 판정.** `output/Attention is all you need.md`를 원본 PDF와
눈으로 대조한다 — 이것은 **사용자 판정**이다(§10). 코딩 에이전트가 할 일은
체크리스트(수식·표·그림·읽기 순서·제목 레벨, PLAN.md Phase 2)를 정리해 넘기고
기다리는 것. 그 결과가 Phase 2(정제 범위 확정)의 입력이 된다. 정제 구현 티켓은
#7이 끝나기 전에는 발행할 수 없다.

---

## §5. Architecture

계획된 전체 구조는 [PLAN.md](PLAN.md) "파일 구조"에 있고, 여기서는
현재 실재하는 디렉터리만 설명한다.

| 디렉터리 | 무엇을 위한 곳인가 |
|---|---|
| (루트) | 설계 문서와 규약 |
| `pdf2md/` | 소스 6모듈 전부 존재: `__main__`(CLI·조립) · `strict`(공유 타입) · `mineru_api`(네트워크만) · `cache`(디스크만) · `gate_a`(손실 감지) |
| `tests/` | 루트 pytest 스위트 (`test_cache` · `test_gate_a`). `reference/tests/`와 절대 섞어 돌리지 않는다 |
| `reference/` | **보류된 Notion 경로의 원본.** 외부 프로젝트에서 복사해 온 읽기 전용 자료. 이번 계획에서 한 줄도 쓰지 않는다. 자체 pytest 스위트를 가지며 **반드시 이 디렉터리 안에서 실행**해야 한다(§1) |
| `cache/` | MinerU 응답 캐시 `{sha256(pdf)}/`. git 추적 금지. 지워도 안전하지만 지우면 API 할당량을 다시 태운다 |
| `output/` | 최종 산출물 `{stem}.md` + `images/`. git 추적 금지. 언제든 재생성 가능 |

`cache/`와 `output/`은 첫 실행 시 생성된다.

### 진입점

| 진입점 | 담당 |
|---|---|
| `python -m pdf2md <pdf>` | 유일한 진입점. 인자 파싱 → 파싱(캐시/API) → Gate A → 출력. 정제 단계는 Phase 3에서 추가 |

### 런타임 흐름

```
PDF ─[MinerU API v4]→ cache/{sha256}/ ─[Gate A]→ [정제]→ output/{이름}.md + images/
                       md + content_list.json      ↑
                                            인식 실패 감지
```

**Gate A가 `content_list.json`을 보는 이유** — 손실은 JSON에만 흔적이 남는다.
md에는 페이지 경계도 빈 블록도 없어서 "3페이지짜리 표가 통째로 증발"이 md에서는
그냥 매끄러운 문서로 보인다. **md로 내려오면 원리적으로 감지가 불가능하다.**

### 테스트

`tests/`는 루트 pytest로 돌린다. `reference/tests/`는 **별도 스위트**이며
경로 문제로 루트에서 수집되면 실패한다(§1). 두 스위트를 한 번에 돌리지 않는다.

---

## §6. Workflow

- evaluate → issue → branch → test-first implementation → verification →
  review → PR 순서를 따른다.
- 제품 코드를 바꾸기 전에 이슈를 만든다. 규약은 [ticket.md](ticket.md).
- `main`에 제품 코드를 직접 푸시하지 않는다.
- 변경을 좁게 유지한다. 관련 없는 파일을 다시 쓰지 않는다.
- 수정 전에 기존 파일을 읽는다.
- 사용자의 변경이나 무관한 워크트리 변경을 되돌리지 않는다.
- 동작 변경에는 RED → GREEN → REFACTOR를 쓴다.

---

## §7. Engineering principles

- 단일 책임과 명시적 모듈 경계를 지킨다.
- 모듈 간 데이터는 타입·태그드 유니온·인터페이스로 모델링한다.
- **모든 외부 입력을 경계에서 검증한다.** MinerU 응답, PDF 파일, `.env` 값은
  전부 신뢰할 수 없는 입력이다.
- 플랫폼·SDK 에러를 프로젝트 소유 에러 타입으로 감싼 뒤 호출자에게 넘긴다.
  하위 코드가 `httpx` 예외 형태를 들여다보게 두지 않는다.
- **현재 쓰임이 없는 추상화를 만들지 않는다.**
- **새 의존성을 추가하지 않는다.** 이미 설치된 것으로 해결한다(§8).
- 의도적 단순화는 `# ponytail:` 주석으로 표시하고 한계와 업그레이드 경로를 적는다.
- **정제 규칙을 추측으로 만들지 않는다.** 실제 출력에서 깨진 것만 고친다.

**테스트**

- 제품 로직보다 실패하는 동작 테스트를 먼저 쓴다.
- 목(mock)보다 실제 상태 전이를 선호한다.
- 테스트는 내부 구현이 아니라 사용자에게 보이는 동작을 검증한다.
- 프레임워크·픽스처 없이. `assert` 기반 `__main__` 자체 점검이나 작은 `test_*.py`.
- **API 호출은 테스트하지 않는다.** `content_list.json` 픽스처를 손으로 만들어 검증한다.

---

## §8. 환경

```
OS      Windows 11 / PowerShell (Bash 도구도 사용 가능)
Python  3.13.15
설치됨  httpx 0.28.1 · pytest 9.1.1 · python-dotenv 1.2.2 · requests 2.34.2
```

빌드 설정 파일(`pyproject.toml`, `requirements.txt` 등)이 **없다.** 의존성은
전역 환경에 이미 설치되어 있고, 락파일도 툴체인 고정도 없다. 린터·타입체커·CI 없음.

---

## §9. Security and privacy

이 저장소에서 실제로 위험한 것만 적는다.

- **`.env`에 살아있는 API 토큰 2개가 평문으로 있다.** `.gitignore`에 있으나
  `git add -f` 로 우회하지 않는다. 값을 코드·문서·커밋 메시지·이슈에 복사하지 않는다.

  | 키 | 용도 |
  |---|---|
  | `MINERU_API_TOKEN` | MinerU 정밀 해석 API v4. **14일 만료**, 재발급 mineru.net/apiManage/token |
  | `NOTION_API_KEY` | 보류 중인 Notion 경로용. 현재 미사용 |

- **소스에 자격증명을 하드코딩하지 않는다.** 토큰은 `.env`에서만 읽는다. (외부에서
  가져온 참고 파일 `notion_blank_quiz.py`에 Notion 토큰이 평문으로 박혀 있었고,
  용도를 다해 2026-08-22에 삭제했다. 토큰 값은 `.env`에 보존되어 있다.)
- **PDF가 MinerU 서버(중국 기업의 싱가포르 리전)로 전송된다.** 공개 논문은 무관하나
  사외 반출이 곤란한 문서는 이 파이프라인에 넣지 않는다.
- `cache/`에는 원본 문서의 전체 텍스트가 남는다. git 추적 금지.

---

## §10. Verification

좁은 것부터 넓은 것 순서로, 실제로 돌려본 것만.

```bash
python -m pdf2md.strict                          # strict.py 자체 점검 — passed, exit 0
python -m pdf2md.mineru_api                      # API 클라이언트 자체 점검 (MockTransport) — passed
python -m pytest tests/ -q                       # 루트 스위트 — 30 passed
(cd reference && python -m pytest tests/ -q)     # 보류된 참조 코드 회귀 — 36 passed
python -m pdf2md "Attention is all you need.pdf" # 끝까지 — Gate A OK → output/ 조립 (실 API 검증 완료)
```

CI가 없다. 모든 검증은 로컬에서 수동으로 이뤄진다.

**검증하지 못한 것은 검증하지 못했다고 분명히 말한다. 하지 않은 검사를 한 것처럼
암시하지 않는다.**

### 테스트로 검증되지 않는 영역

**변환 품질**은 테스트로 판정할 수 없다. 마크다운이 원본 논문을 충실히 담았는지는
원본 PDF와 눈으로 대조해야만 알 수 있고, 이는 **사용자의 판정 몫이다.**

직접 판단하지 말고, 확인할 항목을 체크리스트 하나로 정리해서 넘기고 기다린다
(수식·표·그림·읽기 순서·제목 레벨 등 — [PLAN.md](PLAN.md) Phase 2 참조).

---

## §11. 함정 (겪은 것만 적는다)

1. **루트에서 bare `python -m pytest` 를 돌리면 실패한다.** `reference/tests/` 를
   수집하는데 그 테스트들은 `notes.*` 를 임포트한다. 항상 경로를 명시하거나
   `reference/` 안에서 실행한다.
2. **Bash의 `/tmp`와 Windows Python의 `/tmp`는 다른 경로다.** 파이프라인 중간값을
   `/tmp`로 넘기면 조용히 실패한다. 임시파일은 지정된 스크래치패드 경로를 쓴다.
   (이것 때문에 Notion 검증 블록이 안 지워지고 페이지에 남은 적 있음)
3. **Notion 404 = "없음"과 "공유 안 됨"을 구분하지 않는다.** 통합 연결 문제로
   단정하기 전에 `POST /v1/search`로 제목 검색을 해본다. 실제로 URL의 ID가 틀렸던
   적이 있다.
4. **HANDOFF.md는 더 이상 지침이 아니다.** 전제("Markdown→Notion은 완성됐으니
   재사용")가 v2에서 무효화됐다. 역사적 기록으로만 읽고 지침은 PLAN.md를 따른다.
5. **MinerU는 표를 HTML `<table>`로 낸다.** 마크다운 출력에서는 그대로 두면 되지만
   (뷰어가 렌더함), 파이프 테이블로 바꿀지는 Phase 2에서 실제 출력을 보고 정한다.
6. **MinerU Agent API는 쓸 수 없다.** 토큰이 필요 없어 편해 보이지만 markdown만 주고
   `content_list.json`을 주지 않아 Gate A가 불가능하다. v4 Precise API + 토큰 필수.
7. **로컬 폴더명(`PDF_to_Notion`)과 원격 저장소명(`pdf2md`)이 다르다.** 의도된
   것이며 git 동작에 영향 없다.
8. **Windows 콘솔(cp949)에서 유니코드 출력이 `UnicodeEncodeError`로 죽는다.**
   리포트의 em-dash로 실제 크래시가 났다. `__main__.py`가 stdout/stderr를
   `errors="replace"`로 재구성해 막는다 — 새 출력 경로를 만들면 같은 함정을 조심.
9. **PLAN의 API 스키마는 문서 기반 초판이 실측과 달랐다** (equation이 `content`가
   아니라 `text` 키, `chart` 등 미기재 타입 존재 → Gate A 오탐 5건). 현재 표는
   실측(2026-08-22) 기준으로 개정됨. 새 필드에 의존하기 전에 캐시의 실물
   `content_list.json`을 먼저 본다.

---

## §12. Writing things down

- **사실이 바뀌면 사실을 고친다.** 옛 문장을 남겨두고 위에 정정을 덧붙이지 않는다.
  읽는 사람이 화해시키지 않고 읽기만 해도 현재 답에 도달해야 한다.
- **같은 규칙을 두 문서에 쓰지 않는다.** 두 벌은 반드시 어긋나고 어느 쪽이 최신인지
  알 수 없다. 링크한다.
- **이 파일은 디렉터리를 설명하지 파일을 설명하지 않는다.** 소스 파일이 하나
  늘었다고 이 파일을 고칠 일은 없다. **디렉터리**가 늘면 고친다.

---

## §13. Document map

| 문서 | 무엇을 위한 문서인가 | 언제 읽는가 |
|---|---|---|
| [CLAUDE.md](CLAUDE.md) | 현재 상태·규칙·함정 | 세션 시작 시 (§0 실행) |
| [PLAN.md](PLAN.md) | 확정 구현계획 v2, 사실 검증 근거, Notion 부록 | 코드를 쓰기 전 항상 |
| [ticket.md](ticket.md) | 이슈·브랜치·커밋·PR 규약 | 이슈를 만들거나 PR을 열 때 |
| [HANDOFF.md](HANDOFF.md) | 원 프로젝트 인수인계. **전제 무효, 역사적 기록** | 배경이 궁금할 때만 |

README는 아직 없다.
