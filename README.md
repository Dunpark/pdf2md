# pdf2md

학술 논문·리포트 PDF를 **형식이 보존된 마크다운**으로 변환하고, 원하면 **Notion
페이지**로도 올려주는 CLI 도구입니다. 수식(LaTeX)·표·이미지·참고문헌 점프 링크까지
원본의 구조를 유지합니다.

## 이 도구가 다른 변환기와 다른 점

PDF 변환기들은 인식에 실패해도 조용히 넘어갑니다. 결과물은 멀쩡해 보이는데 수식과
표가 뭉개져 있고, 원본과 대조하기 전에는 알 수가 없습니다.

> **틀린 수식은 없는 수식보다 나쁘다.**

pdf2md는 변환 결과(MinerU의 구조화 데이터)를 검사해서 **내용이 소실됐으면 결과물을
쓰지 않고 멈추고 보고합니다**(Gate A). 내용이 남아 있는 표현 문제(예: 표가 이미지로
폴백)는 경고만 내고 진행합니다.

## 설치와 준비

처음 한 번만 하면 됩니다. 순서대로 따라가면 5~10분 걸립니다.

### 1단계 — 내려받기와 실행 환경

Windows / Python 3.13 이상 / git이 필요합니다.

```powershell
git clone https://github.com/Dunpark/pdf2md.git
cd pdf2md
python --version                        # 3.13 이상인지 확인
pip install httpx python-dotenv pytest
```

외부 의존성은 `httpx`(HTTP)와 `python-dotenv`(`.env` 읽기) 둘뿐입니다. `pytest`는
테스트용이라 없어도 도구는 동작합니다. `requirements.txt` 같은 빌드 설정 파일은
없습니다 — 환경을 격리하고 싶으면 `python -m venv .venv`로 가상환경을 만들어
활성화한 뒤 위 `pip install`을 실행하세요.

### 2단계 — MinerU API 토큰 발급 (필수)

PDF 해석은 전부 MinerU 공식 API가 합니다. **토큰이 없으면 아무것도 변환할 수
없습니다.**

1. [mineru.net](https://mineru.net) 접속 → 우측 상단 **Login**. 계정이 없으면
   **Sign Up**으로 가입합니다.
2. 로그인 후 상단 내비게이션의 **API** → API 관리 페이지
   ([mineru.net/apiManage/token](https://mineru.net/apiManage/token)).
3. 계정에 따라 **API 사용 신청 폼**이 먼저 뜹니다. 뜨면 용도를 적어 제출하고 승인을
   기다립니다. 신청 단계 없이 바로 토큰 생성 화면이 나오는 계정도 있습니다.
4. 토큰을 생성하고 **문자열 전체를 복사**합니다. 4단계에서 씁니다.

알아둘 것:

- **유효기간 14일, 자동 갱신 없음.** 만료되면 같은 페이지에서 재발급합니다.
- 실행 중 `HTTP 401`이 뜨면 십중팔구 만료입니다 — 도구가 그렇게 안내합니다.
- **무료**입니다(공식 안내: 상업화 과금 계획 없음). 계정당 하루 1000페이지까지
  최우선 순위로 처리되고, 넘으면 우선순위가 내려갑니다.
- 파일 한도: **200MB / 200페이지**.
- **PDF 원본이 MinerU 서버(싱가포르 리전)로 전송됩니다.** 외부 반출이 곤란한
  문서는 넣지 마세요.

### 3단계 — Notion 통합 키 발급 (Notion 모드를 쓸 때만)

마크다운만 쓸 거면 **건너뛰어도 됩니다.** `--md`는 이 키 없이 동작합니다.

Notion은 이 화면의 명칭을 자주 바꿉니다("통합 / Integration" ↔ "연결 /
Connection"). 아래는 현재 이름 기준이며, 못 찾겠으면 Notion **설정 → 연결**
안을 보면 있습니다.

1. [notion.so/my-integrations](https://www.notion.so/my-integrations) 접속
   (또는 Notion 앱 **설정 → 연결 → 개발자 모드**).
2. **+ 새 통합 / New integration(연결)** 을 누릅니다.
3. **이름**을 정합니다 — 무엇이든 상관없습니다. 이 도구는 통합 이름을 검사하지
   않습니다. 그리고 연결할 **워크스페이스**를 고릅니다.
4. 권한(Capabilities)에서 **콘텐츠 읽기 · 삽입 · 업데이트** 셋을 켭니다. 사용자
   정보 권한은 필요 없습니다.

   | 권한 | 이 도구가 쓰는 곳 |
   |---|---|
   | 읽기 | 페이지 제목·기존 블록 수 확인 (중복 업로드 경고) |
   | 삽입 | 본문 블록 append, 이미지 파일 업로드 |
   | 업데이트 | 빈 페이지 제목 설정, 인용 → References 점프 링크 패치 |

5. 저장한 뒤 **Internal Integration Secret(내부 통합 토큰)** 을 **표시(Show) →
   복사**합니다. `ntn_`으로 시작합니다. 생성 직후 한 번만 보여주는 화면도 있으니
   **지금 복사해 두세요.**

> 회사·학교 워크스페이스라면 관리자가 통합 생성을 막아 뒀을 수 있습니다
> (Business/Enterprise 플랜). 그러면 개인 워크스페이스를 하나 만들어 쓰거나
> 관리자에게 허용을 요청하세요.

키를 만든 것만으로는 아직 아무 페이지에도 접근할 수 없습니다 — 업로드할 페이지를
이 통합에 **공유**해야 합니다. 그 절차는 아래 [Notion 모드 여정](#notion-모드-여정)에
있습니다.

### 4단계 — `.env` 만들기

프로젝트 루트(이 README가 있는 폴더)에 `.env` 파일을 만들고 다음 두 줄을 넣습니다.

```
MINERU_API_TOKEN=2단계에서_복사한_토큰
NOTION_API_KEY=ntn_3단계에서_복사한_토큰
```

PowerShell로 한 번에 만들려면:

```powershell
@"
MINERU_API_TOKEN=붙여넣기
NOTION_API_KEY=붙여넣기
"@ | Set-Content -Encoding utf8 .env
```

- 값을 **따옴표로 감싸지 마세요.** `=` 앞뒤에 공백도 넣지 마세요.
- Notion을 안 쓸 거면 `NOTION_API_KEY` 줄은 빼도 됩니다.
- 메모장으로 만들면 파일명이 `.env.txt`가 되기 쉽습니다. 확장자 표시를 켜고
  확인하세요.
- `.env`는 `.gitignore`에 있습니다. **토큰을 커밋·공유·캡처에 노출하지 마세요.**
  저장소를 남에게 줄 때도 `.env`는 주지 않습니다 — 받는 사람이 자기 토큰을
  발급합니다.

### 5단계 — 동작 확인

먼저 네트워크 없이 도는 검사부터:

```powershell
python -m pytest tests/ -q     # 전체 테스트
python -m pdf2md.strict        # 공유 타입 자체 점검
```

그리고 실제 변환을 한 번 돌려 봅니다 (저장소에 시료 논문이 들어 있습니다):

```powershell
python -m pdf2md "pdfs/Attention is all you need.pdf" --md
```

첫 실행은 MinerU 해석 때문에 수 분 걸립니다. 끝나면
`output/Attention is all you need.md`와 `output/images/`가 생깁니다. 같은 PDF를
다시 돌리면 `cache/`에 결과가 있어 즉시 끝나고 API 할당량도 쓰지 않습니다.

### 막혔을 때

| 증상 | 원인과 조치 |
|---|---|
| `MINERU_API_TOKEN이 없다` | `.env`가 없거나 위치가 틀림. 프로젝트 루트인지, 파일명이 `.env.txt`가 아닌지 확인 |
| MinerU `HTTP 401` | 토큰 만료(14일). 재발급해서 `.env` 값을 교체 |
| `NOTION_API_KEY is missing` | 3·4단계를 안 했거나 키 이름 오타 |
| Notion `404` | 페이지가 없거나 **통합에 공유가 안 됨**. Notion API는 둘을 구분하지 않습니다. URL이 맞는지 확인하고 [Notion 모드 여정](#notion-모드-여정)의 공유 단계를 다시 하세요 |
| `Gate A: N violation(s)` + `halt:` | 오류가 아니라 **의도된 동작**입니다. 아래 [메시지 읽는 법](#메시지-읽는-법) 참조 |

## 사용법

```
python -m pdf2md <pdf-path>                      # 대화형 — 출력 대상을 물어봄
python -m pdf2md <pdf-path> --md                 # 묻지 않고 마크다운만
python -m pdf2md <pdf-path> --notion <page-url>  # 묻지 않고 Notion + 마크다운
python -m pdf2md <pdf-path> --notion             # 페이지 URL만 물어봄
python -m pdf2md <file.md>  --notion <page-url>  # 이미 변환된(·편집한) md를 그대로 업로드
```

실행 흐름: **PDF 해석**(첫 실행은 수 분, 결과는 `cache/`에 저장되어 재실행 시 즉시)
→ **Gate A 손실 검사** → **정제**(HTML 표→파이프 표, 참조 링크, 헤딩 깊이) →
`output/<이름>.md` + `output/images/` 생성 → (Notion 모드면) 업로드.

### Notion 모드 여정

1. Notion에서 **빈 페이지**를 하나 만든다.
2. 페이지 우측 상단 `…` → 맨 아래 **연결 추가(Add connections)** → 3단계에서 만든
   통합을 검색해 고른다. (공유하지 않으면 404가 난다 — 에러 메시지가 알려준다.
   메시지에 나오는 `Automations`는 개발 환경에서 쓰던 통합 이름일 뿐이고, 통합
   이름은 무엇이든 상관없다.)
3. 페이지 링크를 복사해서 `--notion <page-url>`로 실행한다.
4. 도구가 알아서: 빈 페이지의 제목을 **`[논문] {논문 제목}`**으로 설정하고, 수식·표·
   이미지를 포함한 전체 문서를 올린 뒤, 본문의 인용 `[18]`에 References 항목으로
   점프하는 링크를 단다.

마크다운은 Notion 업로드와 무관하게 항상 먼저 생성됩니다 — 업로드가 실패해도
`output/`의 결과물은 온전합니다.

### 변환 결과를 고쳐서 올리기 (md → Notion)

`--md`로 변환한 뒤 `output/<이름>.md`를 손보고(요약 추가, 문단 정리 등) 그 파일을
그대로 입력으로 주면, PDF 재해석 없이 **편집본이 그대로** Notion에 올라갑니다:

```
python -m pdf2md output/<이름>.md --notion <page-url>
```

이미지는 md 파일 옆의 `images/` 폴더에서 찾으므로, `output/` 밖으로 옮겼다면
`images/`도 함께 옮기세요. 이 모드는 변환·검사 단계를 거치지 않습니다 — 파일
내용에 대한 책임은 편집한 사람에게 있습니다.

### 메시지 읽는 법

| 메시지 | 의미 |
|---|---|
| `Gate A: OK — no violations` | 내용 손실 없음. 진행 |
| `Gate A: N violation(s)` + `halt:` | **내용이 소실됨.** 결과물을 쓰지 않고 중단 — 의도된 동작. 리포트의 페이지·블록을 원본 PDF에서 확인 |
| `refine: …` / `notion: …` (stderr) | 표현 계층의 경고. 내용은 보존됨 — 어떤 처리를 했는지 알려주는 것 |
| `appended N of M blocks …` | Notion 업로드가 중간에 실패. 페이지에 올라간 블록을 지우고 재실행하거나, 중복을 감수하고 재실행 |

## 한계와 주의

- **PDF가 MinerU 서버(싱가포르 리전)로 전송됩니다.** 외부 반출이 곤란한 문서는 넣지
  마세요. 한도: 200MB / 200페이지.
- 같은 페이지에 재실행하면 문서가 **뒤에 이어 붙습니다**(중복). 실행 전에 경고를
  띄워 줍니다.
- 표 **셀 안**의 인용은 링크가 아닌 평문으로 남습니다 (Notion API 제약, 경고로 보고).
- 볼드/이탤릭 강조는 살아나지 않습니다 — MinerU가 스타일 정보를 주지 않는 한계.
- 이미 제목이 있는 Notion 페이지의 제목은 덮어쓰지 않습니다.
- `cache/`를 지우면 다음 실행이 API 할당량을 다시 사용합니다. `output/`은 언제든
  재생성 가능합니다.

## 개발자용

```
python -m pytest tests/ -q          # 전체 테스트 (네트워크 없음)
python -m pdf2md.strict             # 공유 타입 자체 점검
```

설계·규약 문서: [CLAUDE.md](CLAUDE.md)(현재 상태·규칙·함정) ·
[PLAN.md](PLAN.md)(구현 계획과 근거) · [ticket.md](ticket.md)(이슈·PR 규약)
