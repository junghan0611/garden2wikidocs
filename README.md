# Junghanacs's Digital Garden — WikiDocs 미러

정한(Junghan Kim)의 디지털 가든 <https://notes.junghanacs.com> 을 위키독스(wikidocs.net)
책으로 미러링하는 저장소입니다. 개별 노트가 아니라 **가든 전체를 폴더 단위로** 위키독스에
올려, 위키독스 안에서 자기완결적으로 순회할 수 있게 하는 것이 목표입니다.

이 저장소는 위키독스 책 **`book_id 20676`** 과 깃허브 연동돼 있습니다. `git push` 하면 웹훅이
`TOC.md`·`pages/`·`assets/` 를 읽어 위키독스를 동기화합니다. **이 저장소가 원본**이고
위키독스 웹 편집은 기준 경로가 아닙니다. 가든(`~/repos/gh/notes`)과는 별개이며, 여기 push 는
위키독스 웹훅만 트리거하고 가든의 Netlify 빌드와 무관합니다.

## 저장소 구조

```
TOC.md                       폴더=챕터 계층 (위키독스 목차)
pages/<folder>/<id>.md       각 노트 (denote-id 파일명, H1·frontmatter 없음)
pages/<folder>/_chapter.md   챕터 표지 ([[SubPages]] 로 하위 자동 나열)
assets/                      로컬 이미지 (웹훅이 위키독스로 자동 업로드)
mapping.json                 denote-id ↔ page_id ↔ 위키독스 URL 원장 (편집관리 SSOT)
.claude/skills/garden-to-wikidocs/   변환 스킬 + scripts (build/recover/relink)
```

## 파이프라인 (3단계)

```
[1] build.py   씨뿌리기 — 가든 폴더 → pages + TOC + mapping(page_id 빈칸). push → 웹훅 생성
[2] recover.py 회수 — book get 으로 gid↔page_id 회수해 mapping.json 채움
[3] relink.py  링크 실화(미구현) — 내부 링크를 wikidocs.net/<page_id> 로 재작성 → push
```

`pages/x.md` 상대 링크는 위키독스에서 작동하지 않습니다(메인으로 튕김). 페이지 간 링크는
`https://wikidocs.net/<page_id>` 절대 URL이어야 하고, page_id 는 페이지 생성 후에만 생기므로
3단계가 구조적으로 필요합니다.

메커니즘·변환 매핑·실행법은 **`.claude/skills/garden-to-wikidocs/SKILL.md` 가 SSOT**,
현재 진행 상황과 다음 한 걸음은 **`NEXT.md`** 를 보세요.

## 핵심 불변식 (실험으로 검증)

- **URL = page_id 기반.** 파일명·제목·순서를 바꿔도 page_id 유지. 직접 지정은 불가하므로
  `mapping.json` 으로 회수·관리합니다.
- **파일명 = denote-id.** 제목은 TOC 가 관리(제목이 바뀌어도 URL 무관).
- **위키독스는 제목 알파벳순으로 강제 정렬** → 제목 앞 날짜 8자리 접두어로 시간순 유지.
- **페이지 간 링크는 page_id 절대 URL만 작동.**
- **회사/직장 신원 난독화 필수** — 가든 `change-text.sh` 규칙을 런타임에 읽어 적용.
  민감어를 코드·문서에 하드코딩하지 않습니다(pre-commit 훅이 막습니다).

## 규칙

- 가든(`~/repos/gh/notes/content`)은 read-only. 절대 수정하지 않습니다.
- push 는 GLG 결정. 에이전트는 커밋까지, push 는 명시 요청 시에만(= 위키독스 라이브 반영).
- 담당자 없이 스크립트 + `mapping.json` + 문서로 재현·관리합니다.
