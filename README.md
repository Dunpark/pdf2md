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

## 준비물

- Windows / Python 3.13 (의존성: `httpx`, `python-dotenv` — 테스트는 `pytest`)
- 프로젝트 루트에 `.env` 파일:

  | 키 | 용도 | 발급 |
  |---|---|---|
  | `MINERU_API_TOKEN` | PDF 해석 (필수) | [mineru.net/apiManage/token](https://mineru.net/apiManage/token) — **유효기간 14일**, 만료되면 재발급 |
  | `NOTION_API_KEY` | Notion 업로드 (Notion 모드만) | [notion.so/my-integrations](https://notion.so/my-integrations)의 통합 토큰 |

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
2. 페이지 우측 상단 `…` → 연결 → **`Automations` 통합에 공유**한다. (공유하지 않으면
   404가 난다 — 에러 메시지가 알려준다.)
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
