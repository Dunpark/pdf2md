# pdf2md — 구현계획 (개정판)

> **개정 이력**
> - v1 (2026-08-22): PDF → Markdown → **Notion 페이지**
> - **v2 (2026-08-22): PDF → **정제된 Markdown**. 최종 산출물을 마크다운으로 변경.**
>   마크다운 뷰어의 가독성·편집성이 충분하다는 판단. Notion 경로는 부록에 보관.

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
                       md + content_list.json      ↑
                                            인식 실패 감지
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
| Notion 경로 | **보관.** `reference/`는 방치하고 계획·구현에서 사용하지 않음. `.env`의 `NOTION_API_KEY`도 남겨둠 |
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

| type | 필드 |
|---|---|
| 공통 | `type`, `page_idx`, `bbox` |
| `text` | `text`, `text_level` (0=문단, 1=H1, 2=H2 …) |
| `image` | `img_path`, `img_caption`, `img_footnote` |
| `table` | `table_body`(**HTML**), `table_caption`, `table_footnote`, `img_path`(**표 인식 실패 시 폴백 이미지**) |
| `equation` | `content` (LaTeX 원문) |
| `list` / `code` | `content` / `code_body`, `guess_lang` (VLM 전용) |

**MinerU는 표를 HTML `<table>`로 낸다** — 다중 헤더·병합 셀을 마크다운이 표현하지
못하므로 의도된 선택이다. 마크다운 출력에서는 **그대로 두면 된다**(대부분의 뷰어가
HTML 표를 렌더한다). 파이프 테이블 변환은 Phase 2에서 실제 출력을 보고 판단한다.

---

## 파일 구조

```
pdf2md/
├── __init__.py
├── __main__.py     CLI. 인자 파싱, parse_pdf() 조립, 리포트 출력
├── strict.py       Violation / ParseResult / format_report / 프로젝트 소유 에러 타입
├── mineru_api.py   API 3단계 fetch_zip(). 네트워크만 — 캐시도 압축해제도 모른다
├── cache.py        cache/{sha256(pdf)}/ 관리, ZIP 해제, output/ 조립
└── gate_a.py       content_list 순회 → list[Violation]
tests/
├── test_gate_a.py  Gate A 5개 조건 + 정상 입력 오탐 여부
└── test_cache.py   ZIP glob 해제, 캐시 히트
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
| `type=="equation"` 이고 `content` 빔 | **위반** |
| `page_idx` 연속성이 끊김 | **위반** — [#3849](https://github.com/opendatalab/MinerU/issues/3849) 유형, 페이지 통째 소실 |

두 이슈 모두 열려 있고, **md로 내려오면 원리적으로 감지 불가**하다 — md에는 페이지
경계가 없고 빈 블록을 표현하지 못한다.
`# ponytail:` 감지·보고만. 두 이슈가 닫히면 이 검사도 지운다.

**출력 조립 (최소)**: `cache/`의 md와 `images/`를 `output/`으로 복사. 가공 없음.

**검증**: `output/*.md`를 열어 원본 PDF와 대조한다 — Table 1/3, Figure 1,
Multi-Head Attention 수식, 2단 조판 읽기 순서.

---

## Phase 2 — 실제 출력을 보고 정제 범위 확정 (설계 단계, 코드 없음)

**추측으로 정제 규칙을 짜지 않는다.** Phase 1의 결과물을 원본과 대조해
**실제로 깨진 것만** 목록화하고, 그 목록으로 이 PLAN.md를 갱신한다.

점검 항목 (실제로 문제가 있을 때만 규칙이 된다):

- 제목 레벨이 논문 구조와 맞는가 (`text_level` → `#` 개수)
- 수식이 `$$…$$` / `$…$`로 온전히 나오는가, 인라인 수식이 평문으로 새지 않는가
- HTML 표를 그대로 둘 것인가, 파이프 테이블로 바꿀 것인가 (병합 셀 있으면 불가)
- 이미지 캡션이 이미지와 붙어 있는가
- 참고문헌이 줄 단위로 쪼개졌는가
- 2단 조판 읽기 순서가 꼬였는가
- 머리말·꼬리말·쪽번호가 남았는가 (MinerU가 `discarded_blocks`로 빼주지만 확인)

**산출물: 이 문서의 Phase 3 섹션.**

---

## Phase 3 — 정제 구현

Phase 2에서 확정된 규칙만 구현한다. 현재는 **의도적으로 비어 있다.**

`# ponytail:` 실제로 깨진 것만 고친다. MinerU 출력이 이미 충분하면 이 Phase는
통째로 생략한다 — 그것도 정당한 결론이다.

**Gate B의 잔재**: 정제기가 처리할 줄 모르는 구조를 만나면 halt할지 여부는
정제 규칙이 정해진 뒤에 판단한다. 규칙이 없으면 halt 대상도 없다.

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
python -m pdf2md "Attention is all you need.pdf"
```

**첫 실행에서 Gate A가 halt하면 그것도 정상 동작이다.** 리포트를 보고
(a) MinerU 재시도, (b) 실제 손실이면 대응 방안 판단.

---

## 미확인 사항

1. **ZIP 내부 정확한 파일명.** `auto/`에 md·JSON이, `images/`에 이미지가 들어간다는
   것까지 확인. md 파일명이 1차 출처로 확정되지 않았다 → **glob으로 찾는다.**
2. **`data_id` 필수 여부.** 문서 예시엔 있으나 선택인지 불명. 일단 넣는다.
3. **MinerU 무료의 지속성.** "目前"(현재)이라는 단서가 붙어 있다.
4. **MinerU가 이 PDF에서 실제로 뱉는 md의 형태.** 벤치마크는 대리 지표다.
   Phase 1이 이걸 확인하기 위한 단계이고, Phase 2·3은 그 결과에 전적으로 의존한다.

---

## 하지 않는 것

- 로컬 MinerU (PyTorch·모델 가중치·WSL2) — 이 머신은 Intel Arc **내장** GPU라 CUDA 없음
- MinerU 이슈 #4311/#3849의 **수정** — 감지만. 실제 발생 시 대응
- base64 이미지 인라인 — `images/` 폴더 동반 방식
- 정제 규칙의 사전 설계 — Phase 2에서 실제 출력을 보고 정함
- Notion 업로드 (부록 참조)

---

## 부록 — 보류된 Notion 경로

되살릴 경우를 위해 **검증 완료된 사실만** 남긴다. `reference/`는 방치 상태로 보존됨.

| 항목 | 확인 결과 (2026-08-22) |
|---|---|
| 통합 | `Automations` (워크스페이스 `Home`), 토큰은 `.env`의 `NOTION_API_KEY` |
| API 버전 | `Notion-Version: 2026-03-11` 동작 확인 |
| 대상 페이지 | `3c402360b04780f7bcd9fe1ee0c87948` — "Attention is all you need", 자식 블록 0건 |
| 쓰기 권한 | `PATCH /blocks/{id}/children` 성공, `DELETE /blocks/{id}` 성공 (검증 후 원상복구) |
| 한도 | rich_text 2000자·배열 100개, equation 1000자, 요청 500KB·블록 1000개 |
| 파일 업로드 | 단일 파트 **2단계** (`POST /v1/file_uploads` → `POST /…/send` multipart, 필드명 `file`). ≤20MB |
| 이미지 블록 | `{"type":"image","image":{"type":"file_upload","file_upload":{"id":"…"}}}` |
| 표 | `table_width`·`has_column_header`·`cells`. **colspan/rowspan API 미지원** |
| `reference/` 상태 | 36 passed. `notion_parser.py` 595L 재사용 가능 |

되살릴 때 필요한 작업: Gate B(2000자 분할·1000자 halt·미지원 마크업 sniffer·
HTML→Notion 표 변환·이미지 블록), `notion_upload.py`, `URL→page_id`.
상세는 이 문서 v1 (git 이력 또는 `~/.claude/plans/`) 참조.
