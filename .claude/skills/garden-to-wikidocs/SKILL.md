---
name: garden-to-wikidocs
description: 정한의 디지털 가든(Quartz/Hugo MD, ~/repos/gh/notes/content)을 위키독스 깃허브 연동 책(book_id 20676)으로 내보낼 때 사용한다. 폴더 미러 3단계 파이프라인(build 씨뿌리기 → recover 회수 → relink 링크 실화). 가든 원본은 절대 수정하지 않고, denote-id 파일명·날짜접두어 제목·callout·relref·citeproc·이미지·회사신원 난독화를 처리한다. push 하면 웹훅이 위키독스를 동기화한다.
---

# 가든 → 위키독스 깃허브 연동 책 내보내기 (v2)

이 리포(`junghan0611/garden2wikidocs`)는 위키독스 책 **20676 "Junghanacs's Digital
Garden"** 과 깃허브 연동돼 있다. `git push` → 웹훅 → 위키독스 동기화. **이 리포가 원본**이고
위키독스 웹 UI 편집은 기준 경로가 아니다. 가든 전체를 폴더 단위로 올려 위키독스 안에서
자기완결적으로 순회하게 하는 것이 목표(개별 노트가 아니라 가든 전체).

## 3단계 파이프라인

```
[1] build.py   씨뿌리기 — 가든 폴더 → pages/<folder>/<denote-id>.md + TOC.md + mapping.json
               + content/index.md → README.md(위키독스 책 '대문').
               내부 relref 는 가든 절대URL, 각 페이지에 <!-- gid:ID --> 앵커. → commit/push
[2] recover.py 회수 — book get 으로 gid<->page_id 회수해 mapping.json 채움
[3] relink.py  링크 실화 — pages/**·README 의 가든 URL 중 page_id 있는 것만
               wikidocs.net/<page_id> 로 재작성(없으면 가든 URL 유지, 하이브리드). → push
```

`pages/x.md` 같은 상대 링크는 위키독스에서 **작동하지 않는다**(메인으로 튕김). 페이지 간
링크는 반드시 `https://wikidocs.net/<page_id>` 절대 URL이어야 하고, page_id 는 페이지 생성
후에만 생기므로 3단계가 구조적으로 불가피하다.

## 실행

```bash
# 1) 씨뿌리기 (가든 read-only, 이 리포에 생성물 작성)
python3 .claude/skills/garden-to-wikidocs/scripts/build.py --folders journal
git add -A && git commit -m "..." && git push origin main   # 웹훅 동기화

# 2) 회수 (push·동기화 완료 후)
WIKIDOCS_TOKEN="$(pass personal/token/wikidocs/junghanacs)" \
  python3 .claude/skills/garden-to-wikidocs/scripts/recover.py --book-id 20676
git add mapping.json && git commit -m "chore(export): recover journal page_ids"

# 3) 링크 실화 (relink.py 구현 후)
```

- `build.py --folders journal,meta,notes` 처럼 쉼표로 여러 폴더 동시 처리.
- `--garden` 기본 `~/repos/gh/notes`, `--out` 기본은 README.md 있는 리포 루트.
- 의존성 0(Python 표준 라이브러리). 토큰은 `pass personal/token/wikidocs/junghanacs`.

## 실측으로 확정된 불변식 (깨지 말 것 — 실험으로 검증됨)

- **URL = page_id 기반, 매우 안정적.** 파일명·제목·순서를 다 바꿔도 page_id 유지됨.
  단 우리가 URL을 직접 지정할 수 없으므로 `mapping.json` 으로 회수·관리한다.
- **파일명 = denote-id** (`pages/journal/20220310T000000.md`). URL 안정·회수 앵커·편집관리.
- **제목(TOC 링크텍스트) 앞에 날짜 8자리 접두어.** 위키독스는 제목 알파벳순으로 강제
  정렬하므로(번호/접두어 없으면 뒤죽박죽), 날짜 접두어로 시간순을 만든다. 제목이 이미
  ISO 날짜로 시작하면(journal) 접두어를 생략한다.
- **pages/ 서브디렉토리 지원됨.** `pages/<folder>/...` 로 가든 폴더 구조를 미러한다.
- **폴더 = 챕터.** `pages/<folder>/_chapter.md` 에 `[[SubPages]]` 를 넣어 하위 자동 나열.
- **본문 맨 위 H1 없음, frontmatter 없음.** 제목은 TOC 가 관리.
- **회사/직장 신원 난독화 필수.** `scrub_identity` 가 가든 `change-text.sh` 의 치환 규칙을
  런타임에 읽어 적용한다. 민감어를 이 스크립트나 문서에 하드코딩하지 않는다(그 자체가
  pre-commit 훅에 걸린다). change-text.sh 가 어떤 핸들의 특정 번호 변형만 다루는 경우, build.py
  가 그 베이스를 전 변형(숫자 0개 이상)으로 일반화해 훅이 막는 모든 형태를 덮는다.

## 변환 매핑

| 가든 (Quartz/Hugo) | 위키독스 | 함수 |
|---|---|---|
| frontmatter `title` | `<날짜8> <제목>` → TOC 링크텍스트 (sigil 제거) | `subject_for`/`clean_title` |
| frontmatter 전체 | 제거 | `split_frontmatter` |
| `## 제목 {#anchor}` | `## 제목` | `HEAD_ANCHOR` |
| `<span class="timestamp-wrapper">…[날짜]…</span>` | `[날짜]` | `TIMESTAMP` |
| `> [!type] 제목` callout 11종+ | `[[TIP("라벨")]]…[[/TIP]]` | `convert_callouts` |
| `<div class="csl-bib-body">`·`<a href>` citeproc | 마크다운 텍스트/링크 | `convert_html` |
| `[텍스트]({{< relref "/x/y.md" >}})` | 가든 절대URL(씨뿌리기) → page_id URL(relink) | `relref_repl` |
| `{{< figure src=… >}}` | `![](…)` → assets 복사 | `figure_repl` |
| `![](/images/f.png)` | `![](../../assets/f.png)` + assets 복사 | `make_images` |
| 코드펜스 ```` ```/```` ```` | 원형 보존(3+ backtick 개수 매칭, 줄앵커) | `protect_code` |
| 회사/직장 신원 | change-text.sh 규칙으로 난독화 | `scrub_identity` |

## 위키독스 확장문법 착지점

`[[TIP]]`/`[[TIP("라벨")]]`…`[[/TIP]]`, `[[SubPages]]`, `[TOC]`, `[[MARK]]`/`[[SMARK]]`.

## 배포·동기화

push 하면 웹훅이 `README.md`(책 대문)·`TOC.md`·`pages/`·`assets/` 를 읽어 동기화
(`.claude/`·`AGENTS.md`·`NEXT.md`·`mapping.json` 은 무시). `README.md` 는 가든
`content/index.md` 를 변환한 책 대문이므로 index 가 바뀌면 build 가 재생성한다. 안 보이면:
push 반영 확인 → GitHub `Settings > Webhooks` → 위키독스 `책 수정 > 깃허브` 연결/웹훅 →
`지금 동기화`. 103페이지 동기화에 ~70초.

## 알려진 다듬을 거리 (기능 아님)

- citeproc 항목 앞 2칸 들여쓰기, LLM 대화 `@user`/`@assistant` 마커, `<url>` 오토링크.
- 코드펜스(````markdown 예시) 안 relref 는 literal 로 남음(코드 예시라 정상).
