# NEXT — garden2wikidocs

다음 세션 핸드오프. 개요·불변식은 `README.md`(=책 대문)가 아니라
`.claude/skills/garden-to-wikidocs/SKILL.md` 가 SSOT. 릴리즈 이력은 `CHANGELOG.md`.

## NOW — 어디까지 왔나

`v2026.7.17` 로 **가든 5개 폴더 전체 미러 완성**. 씨뿌리기(2238p+대문) → 회수
(page_id 2238/2238 + 챕터 5) → 링크 실화(21786+7) 까지 라이브 검증. 상세는 CHANGELOG.

- 위키독스 책 `book_id 20676`, 이 리포가 원본. push → 웹훅 동기화.
- `mapping.json`: denote-id ↔ page_id ↔ URL + `_chapters`(폴더→표지 URL) 원장.

## NEXT — 다음 한 걸음

### 갱신 사이클 (주 용도)
가든이 바뀌면 재실행: `build.py --folders journal,meta,notes,bib,botlog` → push →
`recover.py --book-id 20676` → `relink.py` → push. build 는 `pages/`·`mapping.json`
을 통째로 재생성하므로 반드시 recover→relink 를 다시 돌려 page_id·링크를 회복한다.

### 선택지 (급하지 않음)
- **챕터 순서**: 위키독스가 표지 제목을 한글 알파벳순 강제정렬(현재 노트·메타·봇로그·
  저널·참고문헌). 원하는 순서로 두려면 `CHAPTER_NAMES` 에 정렬 접두어(예: `1 저널`).
- **README `## AI visitors` 리스트 섹션**: 블록쿼트는 미러 안내로 교체했으나 아래
  H2 리스트(llms.txt·sitemap 등)는 남아있음. 위키독스에선 무의미 → 제거 검토.

## 검증 기준
- 씨뿌리기 후: 페이지 차단어 0, 코드펜스 밖 미처리 숏코드 0.
- 회수 후: `mapping.json` page_id 매칭 N/N + `_chapters` 채워짐.
- relink 후: 위키독스 내부 링크·폴더 링크 클릭이 대상으로 이동(콘텐츠 폴링 확인).

## 블록/주의
- **push 는 GLG만.** 커밋까지 에이전트, push = 위키독스 라이브 반영.
- **가든 read-only.** `~/repos/gh/notes/content` 수정 금지.
- **민감어 하드코딩 금지.** 난독화는 가든 `change-text.sh` 런타임 로드.
- **대량 push 규모**: 2238p·assets 267M. 웹훅 동기화 ~19분(2243 노드). 첫 씨뿌리기
  검증됨. 더 큰 확장 시 폴더 분할 고려.

## 알려진 데이터 결함 (가든 원본, read-only)
- 깨진 코드펜스로 일부 영역이 거대 코드블록화(예: journal 20250630, 20260406).
- bib 20250327: relref 가 링크 텍스트 위치에 잘못 들어간 원본 오류 1건.

## 다듬을 거리 (기능 아님)
citeproc 2칸 들여쓰기, LLM 대화 `@user`/`@assistant` 마커, `<url>` 오토링크.

## 보안 메모 (GLG 결정 대기)
가든 `change-text.sh` 가 어떤 회사 핸들의 특정 번호 변형만 난독화하는데 훅은 전 변형을
막는다. export 는 전 변형을 일반화 처리했다. 가든 change-text.sh 도 베이스 형태로
고치면 공개 가든 잔여 노출이 사라진다 — 여기서는 가든 미수정.
