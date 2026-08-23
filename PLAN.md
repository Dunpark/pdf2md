# pdf2md — 구현계획 (개정판)

> **개정 이력**
> - v1 (2026-08-22): PDF → Markdown → **Notion 페이지**
> - v2 (2026-08-22): PDF → **정제된 Markdown**. 최종 산출물을 마크다운으로 변경.
>   마크다운 뷰어의 가독성·편집성이 충분하다는 판단. Notion 경로는 부록에 보관.
> - **v3 (2026-08-23): Notion 출력 경로 부활 (Phase 4).** 마크다운을 대체하는 것이
>   아니라 선택지 추가 — Notion 모드에서도 `output/` 마크다운은 그대로 생성된다.
>   v1과 달리 정제된 마크다운(R1~R3의 출력)을 변환기의 입력 계약으로 삼는다.

---

## Context

**문제.** PDF를 기계로 변환하는 도구들은 인식 실패를 조용히 삼킨다. 결과물은 멀쩡해
보이는데 수식과 표가 뭉개져 있고, 원본과 대조하지 않으면 알 수가 없다.

> **틀린 수식은 없는 수식보다 나쁘다.**
> 이 프로젝트의 유일한 존재 이유는 **표현할 수 없는 것을 만나면 멈추고 보고하는 것**이다.

**목표.** `pdf2md <pdf-path>` — 학술 논문·리포트 PDF를 **형식이 보존된 마크다운**으로
변환하되, 변환 과정에서 내용이 소실되면 조용히 넘어가지 않고 멈춘다.

```
PDF ─[MinerU API v4]→ cache/{sha256}/ ─[Gate A]→ [정제]→ output/{이름}.md + images/
                       md + content_list.json      ↑           │ (--notion 선택 시)
                                            인식 실패 감지       └→ [블록 변환]→ Notion 페이지
```

---

## v1에서 무엇이 왜 사라졌는가

Gate B는 **"Notion이 표현 못 하는 것"**을 잡는 게이트였다. 출력이 마크다운이면 그
제약이 전부 사라진다. 기록으로 남긴다 — 나중에 Notion 경로를 되살릴 때 필요하다.

| 사라진 것 | 이유 |
|---|---|
| `notion_upload.py` (배치 append, 429 재시도, 500KB 검사) | 업로드 대상이 없음 |
| Notion File Upload API 2단계 | 〃 |
| rich_text 2000자 분할 / 배열 100개 상한 | 마크다운엔 길이 한도가 없음 |
| 수식 `expression` 1000자 halt | 〃 |
| 표 `colspan`/`rowspan` halt | HTML 표를 그대로 두면 됨 |
| `URL → page_id` 추출 | 대상 페이지 개념이 없음 |
| **`reference/` 전체** | HANDOFF의 전제("완성된 Notion writer 재사용")가 무효 |

**HANDOFF.md의 전제가 통째로 무효가 되었다.** `notion_parser.py`(595L)도 36개 테스트도
쓸 데가 없다. HANDOFF.md는 역사적 기록으로만 남긴다.

**규모 축소를 정직하게 인정한다.** MinerU는 이미 `.md`를 뱉는다. 우리 도구가 더하는
것은 **손실 검증(Gate A) + 정제** 두 가지뿐이고, 예상 규모는 **200~300줄**이다.
그래도 Gate A는 어떤 오픈소스에도 없으므로 남길 가치가 있다.

---

## 결정사항

| 항목 | 결정 |
|---|---|
| 최종 산출물 | `output/{stem}.md` + `output/images/` — 표준 마크다운. Obsidian·VSCode·GitHub 어디서든 렌더 |
| PDF 파서 | MinerU 공식 API v4, `model_version="vlm"`. 로컬 실행은 하지 않음 |
| 손실 검증 | **Gate A만 남는다.** Gate B는 삭제 |
| **정제 범위** | **지금 정하지 않는다.** Phase 1로 실제 출력을 본 뒤 Phase 2에서 확정 |
| Notion 경로 | **부활 (v3, Phase 4).** `--notion <page-url>`로 선택. `reference/`는 여전히 사용하지 않음 — 이미지·링크 미지원과 `content[:2000]` 잘라내기 때문 (Phase 4 참조) |
| 이미지 | MinerU의 `images/` 폴더를 그대로 동반. base64 인라인 안 함 |
| 패키지명 | `pdf2md` (저장소 폴더명 `PDF_to_Notion`은 역사적 잔재. 무해하므로 그대로 둠) |

---

## 사실 확인 결과 (MinerU)

공식 문서 원문과 직접 요청으로 확인. 추정은 맨 아래 "미확인 사항"에 분리했다.

### API v4 흐름 — 로컬 파일 업로드 3단계

```
1) POST https://mineru.net/api/v4/file-urls/batch
   Header : Authorization: Bearer {token} / Content-Type: application/json
   Body   : {"files":[{"name":"x.pdf","data_id":"…"}],
             "model_version":"vlm", "enable_formula":true,
             "enable_table":true, "language":"en"}
   → batch_id, file_urls[]

2) PUT {file_urls[0]}          바이너리 그대로. Content-Type 헤더 붙이지 말 것

3) GET https://mineru.net/api/v4/extract-results/batch/{batch_id}
   → state ∈ {pending, running, converting, done, failed}
   → done 이면 full_zip_url
```

- **`model_version: "vlm"` 명시 필수.** OmniDocBench 95.69는 VLM 백엔드 점수이고
  이게 MinerU를 고른 유일한 근거다. 생략하면 약한 백엔드로 돌 수 있다.
- **Agent API(`/api/v1/agent/parse/*`, 토큰 불필요)는 쓸 수 없다.** markdown만 주고
  JSON을 주지 않는다 → Gate A 불가.

### 계정·한도 (공식 페이지 원문 직접 수신, 2026-08)

| 항목 | 값 | 출처 |
|---|---|---|
| 과금 | **무료** — "目前暂无商业化收费计划" | [apiManage/limit](https://mineru.net/apiManage/limit) |
| 토큰 발급 | API 관리 페이지에서 **직접 생성**. 승인 대기 없음 | [apiManage/docs](https://mineru.net/apiManage/docs) |
| **토큰 유효기간** | **14일. 자동 갱신 수단 없음** | [Discussion #4412](https://github.com/opendatalab/MinerU/discussions/4412) (미해결) |
| 파일 크기 / 페이지 | ≤ 200MB / **≤ 200페이지** | [apiManage/docs](https://mineru.net/apiManage/docs) |
| 제출 빈도 | 50파일/분, 5000파일/일 | [apiManage/limit](https://mineru.net/apiManage/limit) |
| 모델 버전 | `pipeline`(기본) / **`vlm`(추천)** / `MinerU-HTML` | [apiManage/docs](https://mineru.net/apiManage/docs) |

**도달성 — 이 머신에서 직접 테스트 (2026-08-22)**
```
DNS    mineru.net → 8.222.88.164 (Alibaba Cloud 싱가포르)
HTTPS  200, 0.78s
토큰   GET /extract-results/batch/{bogus} → 200 {"code":-60012,"msg":"task not found"}
       (401이 아님 = 인증 통과)
```

### `content_list.json` 스키마 — Gate A가 여기 의존한다

**실측 기준** (2026-08-22, 이 논문의 실제 v4 VLM 응답, v1 content_list).
문서 기반이던 초판과 달랐던 곳은 굵게 표시.

| type | 필드 |
|---|---|
| 공통 | `type`, `page_idx`(int, 0부터), `bbox` |
| `text` | `text`, `text_level` (제목에만 존재, 문단엔 키 자체가 없음) |
| `image` | `img_path`, **`image_caption`, `image_footnote`** (`img_*` 아님), `content`(빈 값) |
| `table` | `table_body`(**HTML**), `table_caption`, `table_footnote`, `img_path`(**항상 존재** — 표 렌더 이미지) |
| `equation` | **`text` (LaTeX 원문) + `text_format: "latex"`. `content` 키 없음** — Gate A는 둘 다 인정 |
| **`chart`** | **실측에서 발견.** `img_path`, `content`(CSV형 텍스트), `chart_caption`, `chart_footnote` |
| **기타 실측 타입** | `ref_text`(참고문헌 줄), `page_number`, `page_footnote`, `footer`, `aside_text` — 전부 `text`만 |
| `list` / `code` | 이 논문에는 미출현 — **미검증** |

같은 ZIP에 `*_content_list_v2.json`(신형식 추정)도 동봉되나 v1만 사용한다.

**MinerU는 표를 HTML `<table>`로 낸다** — 다중 헤더·병합 셀을 마크다운이 표현하지
못하므로 의도된 선택이다. 마크다운 출력에서는 **그대로 두면 된다**(대부분의 뷰어가
HTML 표를 렌더한다). 파이프 테이블 변환은 Phase 2에서 실제 출력을 보고 판단한다.

---

## 파일 구조

```
pdf2md/
├── __init__.py
├── __main__.py       CLI. 인자 파싱, 출력 대상 선택, parse_pdf() 조립, 리포트 출력
├── strict.py         Violation / ParseResult / NotionDoc / format_report / 에러 타입
├── mineru_api.py     API 3단계 fetch_zip(). 네트워크만 — 캐시도 압축해제도 모른다
├── cache.py          cache/{sha256(pdf)}/ 관리, ZIP 해제, output/ 조립
├── gate_a.py         content_list 순회 → list[Violation]
├── refine.py         Phase 3 정제 규칙 R1~R3. markdown 문자열 → (정제본, 경고 목록)
├── notion_blocks.py  Phase 4. 정제된 md → NotionDoc. 순수 — 한도 검사 전부 여기서
└── notion_upload.py  Phase 4. HTTP만 — 이미지 2단계·배치 append·인용 링크 패치
tests/
├── test_gate_a.py          Gate A 5개 조건 + 정상 입력 오탐 여부
├── test_cache.py           ZIP glob 해제, 캐시 히트
├── test_cli.py             parse_pdf 조립 순서, Gate A halt 정책, 출력 대상 선택
├── test_refine.py          R1~R3 각각 + 변환 불가 시 원본 유지
├── test_notion_blocks.py   블록 변환·한도 검사·인용/참조 기록 (오프라인)
└── test_notion_upload.py   배치·재시도·부분 실패 보고·링크 패치 (MockTransport)
cache/              {sha256(pdf)}/ — MinerU 결과. git 추적 금지
output/             {stem}.md + images/ — 최종 산출물
```

**모듈이 4개에서 6개로 늘어난 이유.** API 호출·캐시·Gate A를 `mineru.py` 하나에
넣으면 논리적으로 독립인 세 작업이 같은 파일을 만지게 되어 병렬 진행이 불가능하다.
"파일을 최소로"보다 병렬성을 택한 의도적 양보다.

**의존 방향은 한 방향으로만 흐른다.** `strict.py`는 아무것도 임포트하지 않고,
`mineru_api`·`cache`·`gate_a`는 `strict`만 임포트하며 **서로를 임포트하지 않는다.**
캐시 히트 시 API를 건너뛰는 판단은 `cache.py`가 아니라 `__main__.py`가 한다 —
`cache.py`가 `mineru_api`를 부르는 순간 이 분리가 무너진다.

`reference/`는 건드리지 않고 방치한다. 이번 계획에서는 **한 줄도 쓰지 않는다.**

---

## Phase 1 — MinerU 연동 + Gate A + 최소 출력

**목표: 이 논문의 실제 `.md`를 손에 넣는다.** 정제는 아직 하지 않는다.

**`pdf2md/__main__.py`의 `parse_pdf()`가 아래를 조립한다.**
```python
def parse_pdf(pdf_path: Path) -> ParseResult
# ParseResult: markdown: str, content_list: list[dict], image_dir: Path
```

**`mineru_api.py` — 네트워크만**

- 위 3단계 API 흐름. 토큰은 `.env`의 `MINERU_API_TOKEN` (`python-dotenv` 사용 — 이미 설치됨).
- **401 응답 시 "토큰이 만료됐을 수 있다(유효기간 14일)"를 메시지에 넣는다.**
  자동 갱신 수단이 없어 실제로 자주 만나게 될 오류다.
- 폴링: `done`이면 진행, `failed`면 에러, 그 외 대기. 타임아웃 상한을 둔다.
- `httpx` 예외를 밖으로 새게 두지 않고 프로젝트 소유 에러로 감싼다.
- **사전 페이지 수 검사는 하지 않는다.** 설치된 의존성만으로는 PDF 페이지 수를
  신뢰성 있게 셀 수 없다 — 정규식 `/Type /Page` 카운트는 페이지 객체가 객체
  스트림에 압축된 PDF에서 과소 계산되고, 이 저장소의 논문 PDF에도 `/ObjStm`이
  33개 있다(2026-08-22 직접 확인). 대신 **API 거부 응답을 "200페이지·200MB 한도
  초과일 수 있다"는 안내로 감싼다.** 파일 크기는 `Path.stat()`으로 셀 수 있으므로
  그것만 업로드 전에 확인한다.

**`cache.py` — 디스크만**

- ZIP 다운로드 결과를 `cache/{sha256(pdf)}/`에 해제.
- **캐시 필수.** 존재하면 API를 호출하지 않는다. halt 후 재실행이 전제인 설계라
  캐시가 없으면 매번 할당량을 태우고, 토큰이 만료돼도 캐시된 문서는 계속 쓸 수 있다.
  (호출 여부의 판단은 `__main__.py`가 한다 — "파일 구조" 참조)
- **ZIP 내부 파일명은 하드코딩하지 말고 glob으로 찾는다** — `*_content_list.json`,
  `*.md`, `images/`. (정확한 파일명 미확인 — 아래 참조)

**Gate A** (`content_list.json` 1회 순회, 20~30줄)

| 조건 | 판정 |
|---|---|
| `type=="table"` 이고 `table_body` 빔 **이고** `img_path` 도 빔 | **위반** — [#4311](https://github.com/opendatalab/MinerU/issues/4311) 유형, 표 전체 소실 |
| `type=="table"` 이고 `table_body` 빔 이지만 `img_path` 있음 | 경고 — 이미지로 폴백되어 내용은 남음 |
| `type=="image"` 이고 `img_path` 빔 | **위반** |
| `type=="chart"` 이고 `img_path` 빔 **이고** `content` 도 빔 | **위반** — 실측 타입, image와 같은 손실 모드 |
| `type=="equation"` 이고 `text` 빔 **이고** `content` 도 빔 | **위반** — 실측 VLM은 `text` 키 사용 |
| `page_idx` 연속성이 끊김 | **위반** — [#3849](https://github.com/opendatalab/MinerU/issues/3849) 유형, 페이지 통째 소실 |
| 블록의 `text`가 md에 없음 (`page_number` 제외) | 경고 — MinerU의 **md 생성** 단계 손실 (#36) |
| `table_body`의 셀이 "글자+하이픈"으로 끝남 | 경고 — 단어가 셀 경계에서 잘림 (#36). 표당 1줄 |
| `type`이 실측 스키마에 없음 | 경고 — 이 타입의 손실 모드를 아무 검사도 모른다 (#36). 타입당 1줄 |
| 블록 텍스트·캡션이 서식을 가리킴(`bold`·`underlined`·`italic`·`red values`) | 경고 — 문서가 안내하는 서식을 md가 보여줄 수 없다 (#40, P6). 복원 불가 |

앞의 두 이슈는 모두 열려 있고, **md로 내려오면 원리적으로 감지 불가**하다 — md에는
페이지 경계가 없고 빈 블록을 표현하지 못한다.
`# ponytail:` 감지·보고만. 두 이슈가 닫히면 이 검사도 지운다.

**md 커버리지 검사(#36)는 위 문장과 모순되지 않는다.** 위 문장은 MinerU의 *인식*
단계 손실 이야기고, 커버리지 검사는 `content_list.json`을 정답으로 삼아 MinerU의
*md 생성* 단계 손실을 잡는다 — 서명이 `gate_a(content_list, markdown="")`인 이유다.
비교는 영숫자만 남긴 40자 프로브로 한다(이스케이프·재조판 차이 무시). 실측 두 논문에
오탐 0. 판정이 **경고**인 이유: 내용은 `cache/`에 온전히 남아 있고, MinerU가 항상
버리는 머리말·쪽번호로 매번 halt하면 도구를 쓸 수 없다.

**출력 조립 (최소)**: `cache/`의 md와 `images/`를 `output/`으로 복사. 가공 없음.

**검증**: `output/*.md`를 열어 원본 PDF와 대조한다 — Table 1/3, Figure 1,
Multi-Head Attention 수식, 2단 조판 읽기 순서.

---

## Phase 2 — 판정 결과 (2026-08-22 완료)

사용자 육안 판정 + 원본 PDF pp.4–9와 md의 직접 대조로 확정했다.
**내용 손실은 없다** — 수식 5개·표 4개의 셀 내용 전부 원본과 일치. 깨진 것은
전부 표현 계층이다.

| 점검 항목 | 판정 |
|---|---|
| 수식 온전성 | **OK** — display 5개·인라인 30개 줄 모두 충실 |
| 이미지 캡션 인접성 | **OK** — 그림 5·표 4 전부 캡션 인접 |
| 참고문헌 줄 쪼개짐 | **OK** — 40개 항목당 1줄 |
| 읽기 순서 | **OK** — 1단 조판(NIPS 서식)이라 위험 자체가 낮았음 |
| 머리말·꼬리말·쪽번호 | **OK** — 흔적 없음 (단 P4 참조) |
| HTML 표 | **깨짐 (P1)** — 사용자 확인. 뷰어가 원시 HTML을 안 그리거나, 그려도 셀 안 `$…$` 수식을 렌더하지 않음 |
| 참조 링크 | **없음 (P2)** — 사용자 확인. 본문 `[18]` ↔ References 간 이동 불가 |
| 제목 레벨 | **평탄화 (P3)** — `3.2.1`이 `3.2`와 같은 `##`. 3단 → 2단으로 뭉개짐 |

**규칙화 보류 (사용자 결정 대기):**
- **P4** — md 1행에 원본 p.1 하단의 저작권 각주가 제목보다 먼저 나옴. 삭제/이동은
  내용 처분이라 보류.
- **P5** — 부록 제목 "Attention Visualizations"가 헤딩이 아닌 평문. 일반화 가능한
  규칙이 나오지 않는 1회성 케이스라 보류.

**복원 불가로 종결 (2026-08-22):**
- **P6** — **볼드/이탤릭 강조 소실은 MinerU 한계다.** 캐시 원본 md에 `**`·`<b>`
  0개, content_list v1·v2·model.json·layout.json 전수 검색에 스타일 정보 전무 —
  인식 단계에서 이미 버려져 정제로는 근거 없는 창작만 가능하므로 하지 않는다
  (§7 "추측으로 정제 규칙을 만들지 않는다"). 잃는 것은 시각적 강조뿐(단락 리드,
  표의 최고점 표시)이고 해당 정보는 본문 산문에 존재한다. `pipeline` 백엔드 실험은
  수식·표 정확도(95.69→71.30)를 버리는 거래라 사용자와 합의하에 미수행.

  **2026-08-23 재확인 (#40, 신규 논문):** `model.json` 블록의 키는
  `angle·bbox·content·merge_prev·type`뿐이고, 4개 JSON과 md 전체에서 "Bold"·
  "underline"은 캡션 산문에만 나온다. P6은 유지된다. 다만 이 논문에서는 서식이
  **의미를 나른다** — Table 1 캡션이 "red values indicate ...", "Bold and
  underlined denote the best and second-best"라고 안내한다. 복원은 못 하므로
  Gate A가 그 사실을 경고한다.

### 논문 간 편차 — 2편째 실측 (2026-08-23, #36)

두 번째 논문(`Toward Autonomous Long-Horizon Engineering for ML Research`)을 넣자
Gate A는 `OK`인데 출력이 깨졌다. 캐시된 `content_list.json`·`full.md`를 두 논문 모두
대조해 확인한 사실:

| 편차 | 실측 | 처분 |
|---|---|---|
| **텍스트 블록 유실** | `page_footnote`·`footer`·`aside_text`·`header`가 JSON엔 있고 md엔 없다. 이 논문 4건, Attention 논문 7건(그중 각주 4·5는 본문급 산문) | Gate A 커버리지 검사 신설 |
| **셀 중간 절단** | Table 3에서 "Paper Comprehension"이 `<td>Paper sion</td><td>Comprehen-</td>`가 됐다. 격자는 직사각형·값도 비지 않아 기존 조건 전부 통과 | Gate A 하이픈 절단 검사 신설 |
| **절 번호 서식** | `## 3.1. Overview`(끝점)·`## A.1.`(부록 문자) — 구 R3 정규식이 하나도 못 잡아 24개 헤딩이 전부 `##`로 평탄화 | R3 확장 |
| **저자-연도 인용** | `(Starace et al., 2025)` 방식이라 References 항목에 번호가 없다 | R2가 정상적으로 아무것도 안 함. 저자-연도 해석은 별개 문제라 미착수 |
| **다중 행 헤더 표** | Table 1의 2행 헤더가 헤더 1행 + 데이터 1행이 되고 colspan 값이 그룹 칼럼마다 복제된다 | 보기 흉하나 무손실. `<th>`가 없는 표에서 "앞 N행이 헤더"는 추측이라 미착수 |

**기각한 검사 — 표 격자 구멍(ragged) 탐지**: 행별 colspan 합은 정당한 `rowspan`
헤더에서 두 논문 모두 어긋난다(폭 {9,10}·{12,13}). 점유 격자를 다 세워야 하는데
실제로 구멍 난 표는 한 건도 관측되지 않았다 — §7 "추측으로 규칙을 만들지 않는다".

---

## Phase 3 — 정제 구현 (규칙 확정, 2026-08-22)

Phase 2에서 실제로 깨진 것만 규칙이 됐다. `pdf2md/refine.py`가 파이프라인
상시 단계로 수행한다 (Gate A 통과 후 → output 조립 전, `__main__.py`가 조립).

| 규칙 | 내용 |
|---|---|
| **R1** 표 출력 | **병합이 있는 표만 MinerU의 렌더 이미지로 낸다 (#42).** 판정은 `table_body`의 `rowspan`/`colspan` 실값 — 추측이 아니다(실측: 두 논문 표 7개 중 5개가 병합 있음). 마크다운에는 셀 병합 문법이 아예 없고 볼드·밑줄·색도 못 그리는데 그 이미지에는 전부 살아 있다(표 7개 전부 이미 `output/images/`에 있었고 md에서 한 번도 참조되지 않았다). 짝은 `content_list`의 표 블록 순서로 맞추되 **첫 셀을 대조해 확인**하고, 어긋나면 파이프 테이블로 되돌리며 경고한다. **병합이 없으면 파이프 테이블로 남긴다** — 셀 텍스트·수식·인용 링크가 살아 있고 이미지로 바꿔서 얻는 것이 없다(실측 Attention 인용 링크: 전량 파이프 74, 전량 이미지 56, 병합 기준 66). 파이프 규칙은 #40 그대로(헤더 합치기·앵커 칸만). **대가**: 이미지가 된 표는 셀 텍스트가 md에서 빠진다 — 검색·복사 불가, Notion에도 그림으로 올라간다. 값은 `cache/`에 남으므로 규칙이 바뀌면 API 없이 되살릴 수 있다. 실행당 한 줄로 몇 개 중 몇 개가 이미지로 나갔는지 알린다 |
| **R1-fallback** 파이프 테이블 | `table_images` 없이 `refine()`을 부르면(md 직접 입력 #31) 종전대로 GFM 파이프 테이블. 병합 셀은 앵커 칸에만 값, 다중 행 헤더는 0행의 최대 `rowspan`만큼을 열별로 이어붙여 한 행으로(`Gemini-3-Flash IterAgent`). 그룹 라벨 행만 복제본을 쓰고 마지막 헤더 행은 본문과 같은 앵커 규칙. 셀 안 `\|`는 이스케이프, HTML 엔티티는 복원 |
| **R2** 참조 링크 | **서식은 References 항목이 정한다 (#40).** ① 번호형: 미니 헤딩(`###### [N]` → 슬러그 `N`), 본문 `[18]`·`[38, 2, 9]`를 `#N` 링크로. ② author-year형: (제1저자 성, 연도+접미사)로 항목을 색인하고 인용 문구를 그대로 미니 헤딩(`###### Starace et al. 2025` → `#starace-et-al-2025`)으로 세운다. 같은 성·같은 해가 둘이면 인용의 저자 수 신호(`A and B` ↔ 두 저자 항목, `A et al.` ↔ 그 외)로 가르고, **하나로 좁혀지지 않으면 평문으로 두고 센다** — 엉뚱한 참조로 뛰는 링크는 뛰지 않는 링크보다 나쁘다. References 블록은 자기 헤딩부터 다음 `## `까지이고 **그 뒤(부록)는 다시 본문이다**(실측 84개 중 49개가 부록에 있었다). 목록에 실재하는 번호만 링크하고 수식 내부는 건드리지 않는다. **메커니즘은 Orca 디폴트 뷰 실측(2026-08-22)으로 확정**: HTML `<a id>` 앵커는 점프 불가, 각주(`[^N]:`)는 파일 전체를 코드 모드로 강제, 헤딩 슬러그 링크만 동작 |
| **R3** 헤딩 깊이 | 번호 달린 `##` 헤딩의 깊이 = 2 + (끝점을 뗀 번호의 점 개수). `1 Introduction`→`##`, `3.1`→`###`, `3.2.1`→`####`. **번호 서식은 논문마다 다르다 (#36)**: 끝에 점을 찍는 `3.1.`과 부록 문자 `A.`·`A.1.`도 같은 규칙으로 처리하고 라벨은 원문 그대로 재출력한다. 번호 없는 헤딩(Abstract·References)은 그대로 |
| **R4** 위첨자 해제 | `<sup>4</sup>`→`⁴`(유니코드 위첨자 숫자), `<sup>∗</sup>`→`∗`(위첨자 자형이 없는 문자는 태그만 벗김). **마크다운에 위첨자 문법이 없고, 뷰어는 HTML이 한 줄만 있어도 파일 전체를 코드 모드로 강제한다** (#38, §11.9). 수식 바깥에만 적용. 경고는 실행당 한 줄로 모은다 |
| **R5** 잔존 HTML 경고 | 모든 규칙이 끝난 뒤에도 남은 태그를 이름별로 한 번씩 알린다. 고치지 않는다. 오늘은 `<sup>`이었고 다음은 `<br>`·`<i>`일 것이다 — 일반 경고가 없으면 같은 고장이 또 조용히 나간다 |

R2·R4·R5는 수식 처리를 `_sub_outside_math()` 하나로 공유한다 — `$$` 블록은 통째로,
인라인 `$…$`는 구간만 원본 그대로 두고 바깥 조각에만 손댄다. 실측으로 Attention 논문
79행에 `<sup>`과 `$d_k$`가 한 줄에 공존한다.

**마크다운에는 토글이 없다 (#42).** `<details>`가 유일한 수단인데 그것도 HTML이라
파일 전체가 코드 모드로 잠긴다(§11.9). "이미지 + 접힌 표"는 마크다운에서 불가능하고,
Notion에는 토글 블록이 있지만 Notion 경로는 같은 정제 md를 먹으므로(아래 Phase 4
"refine을 분기하지 않는다") 그것만 따로 주려면 별도 결정이 필요하다.

**Gate B의 잔재에 대한 판단**: halt하지 않는다. 정제기가 확신할 수 없는 구조
(예: 파싱 불가능한 표 HTML)를 만나면 **원본을 그대로 두고 경고를 출력**한다 —
내용을 잃지 않는 쪽이 항상 이긴다. 수식은 어떤 규칙으로도 건드리지 않는다.

`# ponytail:` P4·P5는 규칙화 보류 (Phase 2 참조). 사용자가 결정하면 추가한다.

---

## Phase 4 — Notion 출력 경로 (v3, 2026-08-23 구현)

`--notion <page-url>` 선택 시 정제된 마크다운을 Notion 블록으로 변환해 기존
페이지에 append한다. **md 출력은 그대로 생성된다** — Notion이 실패해도 결과물은
온전히 남도록 md를 먼저 쓴다.

### 기각한 게으른 경로 두 개

1. **Notion의 마크다운 직접 입력** — `markdown` 입력은 `POST /v1/pages`(새 페이지
   생성)에만 있고 `PATCH /v1/blocks/{id}/children`(기존 페이지 append)은 받지
   않는다. 공식 블록↔마크다운 매핑표에 인라인 수식·페이지 내 블록 링크·로컬 업로드
   이미지의 표현이 없다 — 이 문서에 각각 92·74·5개 있다.
2. **`reference/notes/notion_parser.py`(595줄) 이식** — 이미지·링크를 전혀 지원하지
   않고(리터럴 텍스트가 된다), rich_text 2000자를 분할이 아니라 `content[:2000]`으로
   잘라낸다. 조용한 데이터 소실은 이 프로젝트가 막으려는 바로 그 실패다.

### 핵심 설계 — refine을 분기하지 않는다

R2의 출력이 곧 변환기의 입력 계약이다. `###### [N]` 미니 헤딩 = 참조 항목 식별자,
`[[18](#18)]` = 파싱이 끝난 인용 마커. 변환 규칙은 두 줄: `###### [N]`+다음 줄을
paragraph 한 블록으로 병합하며 `N → 블록 인덱스` 기록(h6 40개가 heading_3으로
뭉개지는 문제도 같이 소멸), 인용은 일반 인라인 링크 파서가 자연히 처리. md 출력과
Notion 출력의 내용 동등성이 증명 대상이 아니라 구조적 사실이 된다 — 같은 문자열에서
나오므로. `content_list.json` 직접 변환은 기각 — `table_body`가 HTML이라 rowspan
전개기를 복제해야 하는 반면 R1의 파이프 표는 전개가 끝나 있다.

### 한도와 halt 정책 — 검사는 전부 네트워크 이전 (`to_blocks` 안)

| 상황 | 처분 |
|---|---|
| equation expression 1000자 초과 | **halt** — 자르면 틀린 수식 (실측 최대 332자) |
| rich_text 2000자 초과 | **분할** — 절대 자르지 않는다. 조각 join == 원문 |
| rich_text 배열 100개 초과 | **halt** — Notion이 validation_error를 내므로 침묵 손실 아님 (실측 최대 17개) |
| 요청 500KB 초과 | 배치를 반으로 분할 |
| md에 HTML `<table>` 잔존 | **halt** — 텍스트로 박히면 표가 사라진 것과 같다 |
| `$` 홀수 줄 | 전부 평문 + 경고 — 수식 경계를 추정하지 않는다 |
| `<sup>4</sup>` | `⁴` 유니코드 위첨자 + 경고. `∗ † ‡`는 자형이 없어 문자만 보존 |
| `####` 헤딩 | `heading_3` 클램프 + 경고 (3개) |
| 표 헤더 2행 (rowspan 전개 흔적) | 경고 — `has_column_header`는 불리언 하나뿐, 내용은 보존 |
| md가 참조하는 이미지 파일 부재 | **halt** — 업로드 중간 실패(부분 쓰기)를 만들지 않는다 |

**LaTeX는 절대 정규화하지 않는다** — `$`와 `$` 사이를 바이트 그대로 복사한다.

### 업로드 순서와 실패 정책

```
1) output/{stem}.md 먼저 쓰기      ← Notion이 실패해도 결과물은 온전
2) 기존 자식 수 확인 (count_children) → 1개 이상이면 중복 안내
3) 페이지 제목 설정 (#25) — 빈 제목일 때만 "[논문] {첫 h1}". 기존 제목은 절대 안 덮음
4) 이미지 2단계 File Upload        (이미지당 2 요청, id는 1시간 만료라 캐시 금지)
5) 100개씩 배치 append → 응답 results에서 블록 id 수집
6) 인용 → 참조 블록 앵커 링크 PATCH (블록당 1회, 실패는 경고 — halt 아님)
```

- **부분 실패는 롤백하지 않고 정확히 보고한다** — "appended N of M blocks before
  failing at batch i/j" + 페이지 URL + 중복 안내 후 exit 1. DELETE 롤백은 그 자체가
  N개의 새 요청이고, 사용자의 페이지에 대고 지우는 동작이다.
- 429/5xx는 `Retry-After` 존중 1회 재시도, 요청 간 0.34s (3 req/s 아래).
- 404 메시지에 "Share the page with the `Automations` integration" 포함
  (404는 "없음"과 "공유 안 됨"을 구분하지 않는다).
- 인용 패치 실패는 경고 + exit 0 — 인용은 평문 `[N]`으로 남아 읽을 수 있다.
  표 셀 안 인용은 패치 불가(2단계 블록이라 append 응답에 id가 없음) — 평문 + 경고.

### CLI (v3)

```
python -m pdf2md <pdf>                      # 대화형 — 출력 대상을 묻는다
python -m pdf2md <pdf> --md                 # 묻지 않고 output/ 만
python -m pdf2md <pdf> --notion <page-url>  # 묻지 않고 Notion + output/
python -m pdf2md <pdf> --notion             # URL만 묻는다
```

`input()`이 EOF·캡처 stdin을 만나면 traceback 대신 usage error(2).
플래그 실행은 스크립트를 막지 않는다 — 중복 경고도 한 줄 찍고 진행.

### 검증된 Notion 사실

| 항목 | 확인 결과 |
|---|---|
| 통합 | `Automations` (워크스페이스 `Home`), 토큰은 `.env`의 `NOTION_API_KEY` |
| API 버전 | `Notion-Version: 2026-03-11` |
| 검증용 페이지 | `3c402360b04780f7bcd9fe1ee0c87948` — "Attention is all you need" |
| 한도 | rich_text 2000자·배열 100개, equation 1000자, 요청 500KB·블록 1000개 |
| 파일 업로드 | 단일 파트 2단계 (`POST /v1/file_uploads` → `POST /…/send` multipart, 필드명 `file`). ≤20MB |
| 이미지 블록 | `{"type":"image","image":{"type":"file_upload","file_upload":{"id":"…"}}}` |
| 표 | `table_width`·`has_column_header`·`cells`. colspan/rowspan API 미지원 |

### TICKET-015 probe 실측 (2026-08-23, 실 API + 브라우저 육안)

프로브 블록은 DELETE로 전량 원복 (자식 수 1 → 1 확인).

| # | 질문 | 실측 답 |
|---|---|---|
| 1 | 페이지 내 블록 앵커 링크가 점프하는가 | **점프한다.** `https://www.notion.so/{page_id}#{block_id 대시 제거}` 를 rich_text `link.url`에 넣으면 클릭 시 대상 블록으로 이동 |
| 2 | 표 셀 안 equation rich_text가 살아남는가 | **살아남고 렌더된다.** 되읽기에서 expression 바이트 동일 |
| 3 | 13열 표를 받아주는가 | **받아준다.** append 200, 되읽기 13열 그대로. 셀 안 링크도 생존 |
| 4 | `\tag{1}` 이 렌더되는가 | **렌더된다.** 수식 우측에 (1) 표시 → 변환기는 `\tag`를 그대로 통과시킨다 |

---

## 테스트

`reference/`의 36개는 이번 계획에서 쓰지 않는다. 새로 만든다.

HANDOFF 승계 규칙: 프레임워크·픽스처 없이, 비자명 로직마다 검증 하나
(`assert` 기반 `demo()`/`__main__` 또는 작은 `test_*.py`).

| 대상 | 검증 |
|---|---|
| Gate A | 위 5개 조건 각각. 정상 `content_list`에 오탐하지 않는지 |
| 캐시 | 같은 PDF 재실행 시 API를 호출하지 않는지 |
| `strict.py` | `format_report` 자체 점검 (`__main__`) |
| ZIP 해제 | glob이 파일명 변형에도 견디는지 |

**API 호출은 테스트하지 않는다.** 네트워크·할당량에 의존하는 테스트는 만들지 않고,
`content_list.json` 픽스처를 손으로 만들어 Gate A를 검증한다.

---

## 검증

```bash
python -m pytest tests/ -q
python -m pdf2md "pdfs/Attention is all you need.pdf"
```

**첫 실행에서 Gate A가 halt하면 그것도 정상 동작이다.** 리포트를 보고
(a) MinerU 재시도, (b) 실제 손실이면 대응 방안 판단.

---

## 미확인 사항

1. ~~ZIP 내부 정확한 파일명~~ **실측 확인 (2026-08-22).** `auto/` 없이 평평한 구조:
   `{uuid}_content_list.json`·`_content_list_v2.json`·`_model.json`·`_origin.pdf`·
   `full.md`·`layout.json`·`images/`. uuid가 매번 달라질 것이므로 **glob 유지가 맞다.**
2. **`data_id` 필수 여부.** 문서 예시엔 있으나 선택인지 불명. 일단 넣는다.
3. **MinerU 무료의 지속성.** "目前"(현재)이라는 단서가 붙어 있다.
4. ~~MinerU가 이 PDF에서 실제로 뱉는 md의 형태~~ **실물 확보 (2026-08-22).**
   `output/Attention is all you need.md` + 이미지 14개. 품질 판정(Phase 2의 입력)은
   사용자 몫으로 남아 있다.

---

## 하지 않는 것

- 로컬 MinerU (PyTorch·모델 가중치·WSL2) — 이 머신은 Intel Arc **내장** GPU라 CUDA 없음
- MinerU 이슈 #4311/#3849의 **수정** — 감지만. 실제 발생 시 대응
- base64 이미지 인라인 — `images/` 폴더 동반 방식
- 정제 규칙의 사전 설계 — Phase 2에서 실제 출력을 보고 정함

