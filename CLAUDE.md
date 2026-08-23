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
     -not -path "*/.pytest_cache/*" -not -path "./cache/*" -not -path "./output/*" -not -path "./pdfs/*" | sort
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
| 4 | PLAN 개정 버전 | `v3` |
| 5 | 리모트 | `origin → Dunpark/pdf2md` |
| 6 | 티켓 | `#1`~`#7`·`#13`·`#15`~`#19`·`#25`·`#28`·`#30`·`#31`·`#34`·`#36`이 존재하고 제목이 `TICKET-NNN` 형식 |

**어긋나면 → 작업을 진행하기 전에 이 문서를 먼저 고친다.**
갱신하지 않은 채로 다음 작업에 들어가지 말 것 — 이 문서가 틀리면 다음 세션이 틀린다.

---

## §1. Quick reference

실제로 실행해 확인한 명령만 적는다.

```bash
python -m pdf2md "pdfs/Attention is all you need.pdf" --md     # → Gate A 경고 7건 → output/{stem}.md + images/
                                                          #   캐시 히트 시 0.4s·네트워크 없음
python -m pdf2md "pdfs/Attention is all you need.pdf" --notion <page-url>  # → 위 + Notion 페이지 append
python -m pytest tests/ -q                        # → 151 passed

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

**범위 밖**: 로컬 MinerU 실행, PDF→Markdown 변환기의 자체 구현.
(Notion 업로드는 v3에서 범위 안으로 들어왔다 — `--notion`, PLAN.md Phase 4.)

상세 설계와 근거는 [PLAN.md](PLAN.md)가 단일 출처다.

---

## §4. 진행 경과

**현재 단계: 일반화 검증 — 2편째 논문(#36)으로 Gate A·정제를 보강했다. 실전 Notion 업로드(#19·#31)의 육안 판정과 P4·P5 결정은 여전히 사용자 대기**

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
| 〃 | #7 판정: 내용 손실 0, 표현 3건 깨짐(P1 HTML표·P2 참조링크·P3 헤딩 평탄화, 사용자+PDF 대조로 확정). P4·P5 보류. PLAN Phase 2·3 확정 후 #13으로 `refine.py` 구현 — 수식 불가침·불확실 시 원본 유지+경고 |
| 〃 | Orca 실측으로 R2 재설계(HTML 앵커→References 번호 미니 헤딩+슬러그 링크, §11.9). 사용자 확인: P1 표·P2 점프 해결. P6(볼드 소실)은 MinerU 한계로 종결 — 스타일 정보가 응답 어디에도 없음(PLAN Phase 2) |
| 2026-08-23 | **Notion 출력 경로 부활 결정. PLAN v3 (Phase 4).** 마크다운 직접 입력 API는 기각(append 미지원 — §11.10), `reference/` 이식도 기각(이미지·링크 미지원, 2000자 잘라내기) |
| 〃 | #15 probe 실측 4건: 블록 앵커 점프 ✔, 표 셀 equation 바이트 동일 생존 ✔, 13열 표 수락 ✔, `\tag{1}` 렌더 ✔ (PLAN Phase 4) |
| 〃 | #16~#18을 계약 기점 커밋 공유 + worktree 병렬로 구현·머지. `notion_blocks`(순수 변환, 한도 검사 전부)·`notion_upload`(HTTP만)·CLI 대상 선택(`--md`/`--notion`/대화형). `--md` 출력은 종전과 바이트 동일 확인 |
| 〃 | #19 인용 → 참조 블록 앵커 링크 패치(블록당 1회, 실패는 경고). PLAN v3·이 문서 개정 |
| 〃 | #28 README(사용자 관점)·CLI 사용여정(usage·대화형 안내·단계 표시) 정비 |
| 〃 | #30 `reference/` 삭제 — Phase 4 자체 구현 완성으로 되살릴 가능성 소멸. bare pytest 함정도 함께 소멸 |
| 〃 | #31 md 입력 → 바로 Notion 업로드 추가 — `--md`로 뽑은 md를 편집한 뒤 재해석 없이 올리는 경로. 파싱·Gate A·정제 건너뜀. 실전 업로드 육안 판정 대기 |
| 〃 | #36 2편째 논문 투입 → Gate A는 `OK`인데 출력 깨짐. 원인 3건 확정(md 생성 단계의 블록 유실·셀 중간 절단·절 번호 서식 편차). Gate A에 커버리지·절단·미지타입 검사 신설, R3를 끝점·부록 문자까지 확장 (PLAN Phase 2 "논문 간 편차") |
| 〃 | #38 출력 md의 마지막 HTML(`<sup>`) 제거 — 뷰어가 "contains HTML"로 코드 모드를 강제해 문서 편집이 막혔다. R4(위첨자 해제)·R5(잔존 HTML 경고) 신설, 수식 회피 로직을 `_sub_outside_math`로 공유 (§11.9) |
| 〃 | #40 사용자 육안 검증 3건 — 인용 점프 불가(author-year 서식)·서식(볼드·색) 부재·병합 셀 반복. 셋 다 경고 없이 나갔다. R2에 author-year 경로(실측 84/84 해결, 부록 포함)·R1에 병합 셀 앵커 표현과 다중 행 헤더 합치기·Gate A에 서식 안내 경고를 넣었다. P6은 재확인 후 유지 |
| 〃 | #42 **병합이 있는 표만** MinerU 렌더 이미지로 출력 — 마크다운에 병합 문법이 없고 토글도 없다(`<details>`는 HTML→코드 모드). 그 이미지에 병합·볼드·밑줄·빨간색이 전부 살아 있고 이미 `output/images/`에 있었는데 참조된 적이 없었다. 병합 없는 표는 파이프 테이블로 남긴다 — 셀 텍스트·수식·인용 링크를 잃을 이유가 없다. 판정은 `rowspan`/`colspan` 실값(실측 7개 중 5개 병합) |

### v2 변경의 파급

- **Gate B 전체 삭제.** 마크다운엔 길이 한도도 병합셀 제약도 없다. 2000자 분할·
  1000자 halt·미지원 마크업 sniffer·HTML→Notion 표 변환·업로더가 전부 불필요.
- **`reference/`가 통째로 무용지물.** HANDOFF의 전제였던 "완성된 Notion writer
  재사용"이 무효. 한동안 보류로 남겨뒀다가 Phase 4가 자체 구현으로 완성된 뒤
  2026-08-23에 삭제했다(#30). 필요하면 git 히스토리에서 복원한다.
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
| — | #13 | Phase 3 정제 파이프라인 (R1~R3) |
| 5 | #15 | Notion probe — 앵커·셀 수식·13열 표·`\tag` 실측 |
| 6 | #16 · #17 · #18 | 블록 변환 · 업로드 · CLI 대상 선택. **계약 기점 커밋 공유 병렬** |
| 7 | #19 | 인용 점프 링크 + PLAN v3 (**실전 업로드의 사용자 판정 필요**) |
| — | #36 | 논문 간 편차 대응 — Gate A 커버리지·셀 절단·미지타입 검사, R3 번호 서식 확장 |
| — | #38 | 출력 md에서 HTML 제거 — R4 위첨자 해제 · R5 잔존 HTML 경고 |
| — | #40 | author-year 인용 링크 · 병합 셀 표현 · 서식 소실 경고 |
| — | #42 | 병합된 표만 렌더 이미지로 출력, 나머지는 파이프 테이블 |

**병렬 wave가 성립하는 조건은 두 가지뿐이다** — 모듈이 서로를 임포트하지 않고,
서로 다른 파일을 소유한다. 공유 타입은 병렬 시작 전에 먼저 존재해야 한다: Wave 2는
#2가 그 역할이었고, Wave 6은 `NotionDoc`을 담은 계약 기점 커밋을 세 브랜치가
공유하는 방식으로 해결했다(머지 커밋 방식이라 공유 커밋은 충돌하지 않는다).

### 다음 할 일

- **#19·#31 실전 업로드의 육안 판정 대기** — 수식 렌더·표 셀 값·이미지·인용 점프,
  그리고 md 직접 업로드(#31)의 실물 결과는 눈으로만 확인 가능하다 (§10).
- 열린 결정 두 개 **사용자 판정 대기** (PLAN.md Phase 2의 P4·P5): 저작권 각주의
  처분과 부록 제목의 헤딩화. 결정되면 규칙을 `refine.py`에 추가한다.
- **논문을 더 투입한다.** 2편째(#36)에서 편차 3종이 나왔고 전부 규칙이 됐다.
  3편째부터는 Gate A 경고 리포트가 먼저 무엇을 볼지 알려주므로 판정이 싸다 —
  새 편차가 나오면 그것이 새 티켓이 된다.

---

## §5. Architecture

계획된 전체 구조는 [PLAN.md](PLAN.md) "파일 구조"에 있고, 여기서는
현재 실재하는 디렉터리만 설명한다.

| 디렉터리 | 무엇을 위한 곳인가 |
|---|---|
| (루트) | 설계 문서와 규약 |
| `pdfs/` | 입력 PDF 모음(#34). 시료 논문 하나만 git 추적, 나머지는 `.gitignore`로 무시 — 사용자가 자유롭게 넣고 뺀다 |
| `pdf2md/` | 소스: `__main__`(CLI·조립·출력 대상 선택) · `strict`(공유 타입) · `mineru_api`(네트워크만) · `cache`(디스크만) · `gate_a`(손실 감지) · `refine`(Phase 3 정제, output에만 적용 — 캐시는 원본 유지) · `notion_blocks`(Phase 4, 정제 md→NotionDoc, 순수·한도 검사 전부) · `notion_upload`(Phase 4, HTTP만) |
| `tests/` | 루트 pytest 스위트 (`test_cache` · `test_gate_a` · `test_cli` · `test_refine` · `test_notion_blocks` · `test_notion_upload`) |
| `cache/` | MinerU 응답 캐시 `{sha256(pdf)}/`. git 추적 금지. 지워도 안전하지만 지우면 API 할당량을 다시 태운다 |
| `output/` | 최종 산출물 `{stem}.md` + `images/`. git 추적 금지. 언제든 재생성 가능 |

`cache/`와 `output/`은 첫 실행 시 생성된다.

### 진입점

| 진입점 | 담당 |
|---|---|
| `python -m pdf2md <pdf> [--md \| --notion [url]]` | 유일한 진입점. 인자 파싱 → 대상 선택(플래그 없으면 대화형) → 파싱(캐시/API) → Gate A → 정제 → output/ → (--notion 시) 블록 변환 → 업로드 |
| `python -m pdf2md <file.md> [--notion [url]]` | 같은 진입점의 md 입력 형태(#31). 파싱·Gate A·정제·output 조립을 전부 건너뛰고 파일 내용 그대로 블록 변환 → 업로드. 이미지는 md 옆 `images/`. 편집한 output md를 재업로드하는 용도 |

### 런타임 흐름

```
PDF ─[MinerU API v4]→ cache/{sha256}/ ─[Gate A]→ [정제]→ output/{이름}.md + images/
                       md + content_list.json      ↑           │ (--notion 선택 시)
                                            인식 실패 감지       └→ [블록 변환]→ Notion 페이지
```

**Gate A가 `content_list.json`을 보는 이유** — 손실은 JSON에만 흔적이 남는다.
md에는 페이지 경계도 빈 블록도 없어서 "3페이지짜리 표가 통째로 증발"이 md에서는
그냥 매끄러운 문서로 보인다. **md로 내려오면 원리적으로 감지가 불가능하다.**

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
  | `NOTION_API_KEY` | Phase 4 Notion 업로드 (`--notion`). `Automations` 통합의 토큰 |

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
python -m pytest tests/ -q                       # 루트 스위트 — 151 passed
python -m pdf2md "pdfs/Attention is all you need.pdf" --md      # 끝까지 — 경고 7건, halt 없이 output/ 조립
python -m pdf2md "pdfs/Toward Autonomous Long-Horizon Engineering for ML Research.pdf" --md  # 2편째 — 경고 5건
python -m pdf2md "pdfs/Attention is all you need.pdf" --notion <page-url>  # 위 + Notion append (실 API)
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

1. **Bash의 `/tmp`와 Windows Python의 `/tmp`는 다른 경로다.** 파이프라인 중간값을
   `/tmp`로 넘기면 조용히 실패한다. 임시파일은 지정된 스크래치패드 경로를 쓴다.
   (이것 때문에 Notion 검증 블록이 안 지워지고 페이지에 남은 적 있음)
2. **Notion 404 = "없음"과 "공유 안 됨"을 구분하지 않는다.** 통합 연결 문제로
   단정하기 전에 `POST /v1/search`로 제목 검색을 해본다. 실제로 URL의 ID가 틀렸던
   적이 있다.
3. **HANDOFF.md는 더 이상 지침이 아니다.** 전제("Markdown→Notion은 완성됐으니
   재사용")가 v2에서 무효화됐다. 역사적 기록으로만 읽고 지침은 PLAN.md를 따른다.
4. **MinerU는 표를 HTML `<table>`로 낸다.** 마크다운 출력에서는 그대로 두면 되지만
   (뷰어가 렌더함), 파이프 테이블로 바꿀지는 Phase 2에서 실제 출력을 보고 정한다.
5. **MinerU Agent API는 쓸 수 없다.** 토큰이 필요 없어 편해 보이지만 markdown만 주고
   `content_list.json`을 주지 않아 Gate A가 불가능하다. v4 Precise API + 토큰 필수.
6. **로컬 폴더명(`PDF_to_Notion`)과 원격 저장소명(`pdf2md`)이 다르다.** 의도된
   것이며 git 동작에 영향 없다.
7. **Windows 콘솔(cp949)에서 유니코드 출력이 `UnicodeEncodeError`로 죽는다.**
   리포트의 em-dash로 실제 크래시가 났다. `__main__.py`가 stdout/stderr를
   `errors="replace"`로 재구성해 막는다 — 새 출력 경로를 만들면 같은 함정을 조심.
8. **PLAN의 API 스키마는 문서 기반 초판이 실측과 달랐다** (equation이 `content`가
   아니라 `text` 키, `chart` 등 미기재 타입 존재 → Gate A 오탐 5건). 현재 표는
   실측(2026-08-22) 기준으로 개정됨. 새 필드에 의존하기 전에 캐시의 실물
   `content_list.json`을 먼저 본다.
9. **사용자의 뷰어는 Orca(디폴트 뷰)다.** 실측: HTML `<a id>` 앵커로는 점프가
   안 되고, GitHub식 헤딩 슬러그 링크만 문서 내 점프가 된다. 그리고 **파일을 코드
   모드로 강제하는 원인이 둘이다** — 각주 문법(`[^N]:`)이 한 줄이라도 있을 때, 그리고
   **HTML 태그가 하나라도 있을 때**("Editable only in code mode because this file
   contains HTML, JSX, or MDX" — #38에서 `<sup>` 하나로 확인). 코드 모드가 되면
   문서로 편집할 수 없다. md 출력 규칙을 바꿀 때 이 전제 위에서 판단한다
   (PLAN.md Phase 3 R2·R4·R5).
10. **Notion의 마크다운 직접 입력은 append를 지원하지 않는다.** `markdown` 입력은
    `POST /v1/pages`(새 페이지 생성) 전용이고 `PATCH /v1/blocks/{id}/children`은
    받지 않는다. 매핑표에 인라인 수식·블록 링크·로컬 이미지도 없다 — 그래서
    `notion_blocks.py`가 존재한다 (PLAN.md Phase 4).
11. **`table_row`의 id는 append 응답에 없다.** 응답 `results`는 1단계 자식만 준다.
    표 셀 안 인용은 그래서 링크 패치가 불가능하다 — 평문 + 경고로 남긴다.
12. **Notion은 LaTeX를 서버에서 검증하지 않는다.** 깨진 수식도 200을 받고
    클라이언트에서만 빨간 에러로 뜬다. 업로드 후 렌더 확인은 눈으로만 가능하다.
13. **Notion API 404는 "없음"과 "통합에 공유 안 됨"을 구분하지 않는다** (함정 2와
    같은 원인). 에러 메시지가 `Automations` 통합 공유를 안내하게 해뒀다.
14. **MinerU의 md는 `content_list.json`의 블록을 소리 없이 버린다.** `page_footnote`·
    `footer`·`aside_text`·`header`가 JSON엔 멀쩡히 있는데 `full.md`엔 없다 — 두 논문
    모두. 각주는 본문급 내용일 수 있다(Attention 논문의 각주 4는 `√d_k` 설명). 그래서
    `gate_a(content_list, markdown)`가 존재한다. **md만 보고 판정하지 말 것.**
15. **표가 비어 있지 않아도 깨져 있을 수 있다.** MinerU가 줄바꿈 하이픈을 셀 경계로
    오인해 "Paper Comprehension"을 `<td>Paper sion</td><td>Comprehen-</td>`로 쪼갠
    실측이 있다. 격자는 직사각형이고 값도 비지 않아 빈값 검사로는 원리적으로 못 잡는다.
16. **인용·참조 서식도 논문마다 다르다.** 숫자형 `[18]`만 있는 게 아니라
    author-year `(Starace et al., 2025)`가 있고, **부록이 References 뒤에 오는
    논문이 있다** — 본문 범위를 "References 앞"으로 잡으면 부록 인용을 통째로
    놓친다(실측 84개 중 49개). 같은 성·같은 해 항목이 둘인 경우도 실재하므로
    (`Schmidgall 2025`) 좁혀지지 않으면 링크하지 않는다 (#40).
17. **마크다운에는 셀 병합도 토글도 없다.** 병합은 문법 자체가 없고, 접기는
    `<details>`뿐인데 그것도 HTML이라 §11.9로 잠긴다. 대신 **MinerU가 표마다 원본
    렌더 이미지를 준다** — 병합·볼드·밑줄·색이 전부 살아 있고 `img_path`로 온다.
    #42 전까지 이 이미지들은 `output/images/`에 있으면서 md에서 한 번도 참조되지
    않았다. **응답에 이미 있는 것을 먼저 확인할 것.**
18. **표를 이미지로 내면 셀 텍스트가 md에서 사라진다** — 검색·복사 불가, 표 안의
    인용 링크도 함께 사라진다. 그래서 **병합이 있는 표만** 이미지로 낸다(#42):
    Attention 논문 인용 링크가 전량 파이프일 때 74, 전량 이미지일 때 56,
    병합 기준으로 가르면 66이다. 값은 `cache/`에 남지만, 이 사실을 모르고 md만
    grep하면 이미지가 된 표의 내용을 못 찾는다.
19. **병합 판정은 추측이 아니다** — `table_body` HTML의 `rowspan`/`colspan` 실값을
    본다(실측: 두 논문 표 7개 중 5개가 병합 있음). 다만 **서식은 판정할 수 없다** —
    병합 없이 색으로만 의미를 나르는 표는 파이프로 나가고 색은 사라진다. 그건
    Gate A의 `styling not preserved` 경고가 잡는다 (#40).
20. **파이프 테이블 경로는 두 곳에서 살아 있다** — 병합 없는 표(#42), 그리고 md
    직접 입력(#31). 거기서는 병합 값을 범위 전체에 복제하면 각 열이 그 값을 가진
    것처럼 읽히므로 앵커 칸에만 두고, 다중 행 헤더는 한 행으로 합친다 (#40).
    파이프 규칙을 고칠 때 "이제 표는 이미지니까 상관없다"고 넘기지 말 것.
21. **문서가 자기 서식을 설명하는 일이 있다** — "red values indicate ...",
    "Bold and underlined denote ...". MinerU는 서식을 안 주므로(P6) 독자는 파일이
    보여줄 수 없는 것을 찾게 된다. 이 안내는 대개 **표 캡션**에 있어서
    `text` 키만 봐서는 안 잡힌다 (#40).
22. **절 번호 서식은 논문마다 다르다.** `3.1`·`3.1.`(끝점)·`A.1.`(부록 문자)가 전부
    나온다. 헤딩 정규식을 좁게 쓰면 조용히 아무것도 안 하고 문서가 통째로 평탄화된다 —
    실제로 #36에서 그렇게 됐다. 새 규칙은 두 캐시 논문 모두에 돌려보고 확정한다.

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
| [README.md](README.md) | 사용자 관점의 소개·사용법 (한국어) | 사용법이 궁금할 때. 에이전트 지침은 아니다 |
