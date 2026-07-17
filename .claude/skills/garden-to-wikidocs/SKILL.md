---
name: garden-to-wikidocs
description: 정한의 디지털 가든(Quartz/Hugo MD, ~/repos/gh/notes/content)을 위키독스 깃허브 연동 책 형식(README.md·TOC.md·pages/·assets/)으로 변환해 이 리포(garden2wikidocs)에 담을 때 사용한다. 가든 원본은 절대 수정하지 않고, sigil 타이틀·callout·relref 링크·citeproc·이미지를 위키독스 문법으로 변환한다. push 하면 웹훅이 위키독스 책을 동기화한다.
---

# 가든 → 위키독스 깃허브 연동 책 내보내기

이 리포(`junghan0611/garden2wikidocs`)는 위키독스와 **깃허브 연동**된 책이다.
`git push` 하면 위키독스가 웹훅으로 당겨가 책을 동기화한다. 웹 UI 편집은 기준 경로가
아니다 — **이 리포가 원본**이다.

이 스킬은 가든 노트를 그 형식으로 변환해 담는다. **담당자 없음**: 스크립트와
manifest 로만 재현한다.

## 원칙

1. **가든은 read-only.** `~/repos/gh/notes/content` 는 절대 수정하지 않는다. 변환기가
   읽어서 이 리포의 `pages/`·`TOC.md`·`assets/` 만 만든다.
2. **push 는 GLG 만 결정.** 에이전트는 커밋까지만(commit 스킬), push 는 명시 요청 시에만.
   push = 위키독스 라이브 반영이다.
3. **전체 내보내기 전에 샘플로 검증.** 새 변환 규칙/스코프는 소수 노트로 먼저 확인한다.

## 위키독스 깃허브 연동 책 형식 (SSOT)

실측 검증한 규칙(ychoi-kr `wikidocs-ebook`, `skills/wikidocs-github-book` 기준):

- **`README.md`** — 첫 `#` = 책 제목, 나머지 = 책 요약. 이미지는 `./assets/...`.
- **`TOC.md`** — `# 목차` + `- [NN. 제목](pages/파일.md)` 불릿. **2칸 들여쓰기 = 계층.**
  위키독스는 제목 알파벳순 정렬이므로 **번호 접두사로 순서를 고정**한다.
- **`pages/*.md`** — **본문 맨 위에 H1(`#`) 을 쓰지 않는다.** 페이지 제목은 오로지
  `TOC.md` 가 관리한다. frontmatter 없음. 페이지 상단에 `[TOC]` 선택 삽입 가능.
  이미지는 `![](../assets/name.png)` (공백은 `%20`). 내부 페이지 링크는 `](pages/other.md)`.
- **`assets/`** — 이미지 저장. 페이지에서 `../assets/`, README 에서 `./assets/`.
- **`.gitignore`** — `.obsidian` (옵시디언으로도 열 수 있음). `.claude/` 는 위키독스가
  무시하므로 이 스킬을 리포에 두어도 동기화에 영향 없다.

### 위키독스 확장문법 (착지점)

- `[[TIP]] … [[/TIP]]` / `[[TIP("라벨")]] … [[/TIP]]` — 팁/콜아웃 박스
- `[[SubPages]]` — 하위 목차 자동 삽입 (챕터 인덱스 페이지용)
- `[TOC]` — 페이지 내 목차
- `[[MARK]]`/`[[SMARK]]` — 코드 강조/삭제 표시
- `[[용어]]` — 용어 링크(위키독스 위키 팝업). 이 변환기는 쓰지 않는다.

## 가든 → 위키독스 변환 매핑

| 가든 (Quartz/Hugo) | 위키독스 | 처리 위치 |
|---|---|---|
| frontmatter `title` | TOC.md 링크 텍스트 (sigil 제거) | `clean_title` |
| frontmatter 전체 | 제거 | `split_frontmatter` |
| `## 제목 {#anchor}` | `## 제목` | `HEAD_ANCHOR` |
| `<span class="timestamp-wrapper">…[날짜]…</span>` | `[날짜]` (HTML 제거, 날짜 유지) | `TIMESTAMP` |
| `> [!type] 제목` callout (11종+) | `[[TIP("라벨")]] … [[/TIP]]` | `convert_callouts` |
| `<div class="csl-bib-body">…` citeproc | 마크다운 텍스트/링크 | `convert_html` |
| `<a href="#citeproc…">텍스트</a>` | `텍스트` | `convert_html` |
| `<a href="url">텍스트</a>` | `[텍스트](url)` | `convert_html` |
| `[텍스트]({{< relref "/x/y.md" >}})` | **하이브리드**(아래) | `make_relref` |
| `![](/images/f.png)` | `![](../assets/f.png)` + assets 복사 | `make_images` |
| 외부 URL 이미지 `![](http…)` | 그대로 | `make_images` |
| 코드블록 ```` ``` ```` | 원형 보존(변환 제외) | `protect_code` |

### relref 링크 정책 — 하이브리드

- 대상 노트가 **이번 내보내기 집합 안**이면 → `](pages/NN-slug.md)` 내부 링크.
- 밖이면 → `](https://notes.junghanacs.com/<path>/)` 절대 URL (가든으로 되돌려보냄).

부분 내보내기여도 링크가 깨지지 않고, 스코프가 커질수록 내부 링크가 자동으로 늘어난다.
"가든에서 나가되 뿌리는 가든" — 위키독스 책이 가든의 위성이 된다.

### sigil 청소 규칙 (조정 가능)

`# @ § ¤ † ‡ © ※ ¶ ‣ ∷` 문자를 제거하고 공백/선두 구두점을 정리한다.
`힣:`·`이력서:`·`번역기:` 같은 네임스페이스 콜론 접두어는 **읽을 만해서 유지**한다.
denote 시퀀스 코드(예: `0zw`)는 현재 남는다 — 필요하면 `SIGILS`/`clean_title` 을 조정.

## 실행

```bash
# 가든은 건드리지 않고 이 리포에 TOC.md·pages/·assets/ 생성
python3 .claude/skills/garden-to-wikidocs/scripts/build.py \
  --manifest .claude/skills/garden-to-wikidocs/sample.json
```

- `--garden <path>` : 가든 루트 (기본 `~/repos/gh/notes`)
- `--out <path>` : 책 리포 루트 (기본: manifest 위로 올라가며 `README.md` 있는 곳)
- `--toc-threshold N` : h2 헤딩 N개 이상이면 페이지 상단에 `[TOC]` 삽입 (기본 3)

의존성 0 (Python 표준 라이브러리만). CLI `wikidocs-cli`/`wikidocs-mcp` 는 참고만 했고
이 파이프라인에는 쓰지 않는다 (깃허브 연동은 순수 `git push`, 토큰 불필요).

### manifest 스키마

```json
{
  "book_title": "…",
  "garden_root": "~/repos/gh/notes",
  "entries": [
    {"num": "01",   "src": "content/notes/2025….md"},
    {"num": "05",   "src": "content/meta/2022….md"},
    {"num": "05-1", "src": "content/notes/2025….md", "title": "제목 덮어쓰기(선택)"}
  ]
}
```

- `num` 의 `-` 개수 = TOC 계층 깊이. `05` 는 depth 0, `05-1` 은 depth 1.
- `src` 는 `garden_root` 기준 상대 경로.
- **전체 책의 목차(TOC 트리)는 곧 manifest 설계다.** 스코프를 넓힐 때는 챕터 뼈대
  (섹션 기반 / meta 기반 / 큐레이션)를 정해 entries 를 생성하면 된다.

## 배포 흐름

1. `build.py` 로 `TOC.md`·`pages/`·`assets/` 생성.
2. 상대 링크·이미지 경로 육안 점검.
3. commit (commit 스킬).
4. **GLG 요청 시** `git push origin main`.
5. 위키독스가 웹훅으로 동기화. 안 보이면: push 반영 확인 → GitHub `Settings > Webhooks`
   → 위키독스 `책 수정 > 깃허브` 연결/웹훅 URL → `지금 동기화` 수동 재시도.

## 알려진 다듬을 거리 (기능 아님, 미관)

- citeproc 항목 앞 2칸 들여쓰기가 남는다 (`  "제목."`). 마크다운상 문단이라 렌더는 정상.
- LLM 대화 노트의 `@user`/`@assistant` 마커는 그대로 나간다. 필요하면 굵은 소제목으로 매핑.
- `<https://…>` 오토링크는 유효한 마크다운이라 그대로 둔다.

## 참고

- 위키독스 확장문법·형식: 로그인 게이트(`wikidocs.net/321336`, `/289752`) → 실측한
  `wikidocs-ebook` 리포가 실질 SSOT.
- 형식 원 스킬: ychoi-kr `skills/wikidocs-github-book`.
- API 방식(대안, 미사용): base `https://wikidocs.net/napi`, `Authorization: Token <token>`,
  토큰은 `pass personal/token/wikidocs/junghanacs`.
