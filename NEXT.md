# NEXT — garden2wikidocs

다음 세션(Opus)이 이어갈 핸드오프. 프로젝트 개요·불변식은 `README.md`,
변환 메커니즘은 `.claude/skills/garden-to-wikidocs/SKILL.md` 가 SSOT.

## NOW — 어디까지 왔나

- 위키독스 책 **`book_id 20676`** 깃허브 연동. 이 리포가 원본.
- **journal 폴더 한 사이클 완료**: 씨뿌리기(103페이지 + 챕터표지) → push → 회수.
  - `mapping.json`: journal 103/103 에 `page_id`·`url` 채워짐.
  - 폴더=챕터, denote-id 파일명, 날짜접두어 정렬, `[[SubPages]]`, 서브디렉토리, 이미지
    자동 업로드까지 라이브 검증됨.
- 진행률: 5개 폴더(journal/meta/notes/bib/botlog) 중 journal 1개가 seed+recover 단계.

## NEXT — 다음 한 걸음

### 1) relink.py (3단계) 구현 — 우선순위 높음
내부 링크를 실제로 살리는 마지막 조각. 현재 모든 내부 링크는 가든 절대 URL이라 위키독스
안에서 순회가 안 된다.

- `pages/**/*.md` 를 훑어 `https://notes.junghanacs.com/<folder>/<denote-id>/` 형태 링크를 찾고,
  그 denote-id 가 `mapping.json` 에 `page_id` 와 함께 있으면 `https://wikidocs.net/<page_id>` 로
  치환. mapping 에 없으면(아직 안 올린 폴더) 가든 URL 그대로 둔다(하이브리드).
- 치환 후 commit → push → 웹훅. 검증: 위키독스에서 journal→journal 링크 클릭이 해당 페이지로
  가는지(메인 안 튕기고). `wikidocs.net/380372` 로 실화한 링크가 동작함은 이미 실험 C에서 확인.
- 스크립트 위치: `.claude/skills/garden-to-wikidocs/scripts/relink.py`.

### 2) 나머지 폴더 씨뿌리기
`build.py --folders meta` → push → `recover.py --book-id 20676` → 반복(notes/bib/botlog).
폴더가 늘수록 relink 가 내부 링크를 더 많이 실화한다(하이브리드).

- **규모 주의**: notes 836·bib 680·meta 538 은 한 폴더도 큼. 웹훅이 대량 push 를 어떻게 버티는지
  아직 미검증 → 한 폴더씩, 필요하면 폴더 내 분할.
- **챕터 정렬**: 폴더가 여러 개면 위키독스가 챕터 표지 제목(저널/메타/…)도 알파벳순 정렬한다.
  챕터 순서를 원하는 대로 두려면 `CHAPTER_NAMES` 값에 정렬용 접두어를 붙이는 방법 검토.

## 실행 요약

```bash
cd ~/repos/gh/garden2wikidocs
# 1) 씨뿌리기
python3 .claude/skills/garden-to-wikidocs/scripts/build.py --folders <folder>
git add -A && git commit -m "..."          # push 는 GLG 요청 시에만
# 2) 회수 (push·동기화 후)
WIKIDOCS_TOKEN="$(pass personal/token/wikidocs/junghanacs)" \
  python3 .claude/skills/garden-to-wikidocs/scripts/recover.py --book-id 20676
```

## 검증 기준

- 씨뿌리기 후: 페이지에 차단어 0건(회사신원 스크럽), 코드펜스 밖 미처리 숏코드 0건.
- 회수 후: `mapping.json` 의 해당 폴더 항목이 전부 `page_id` 채워짐(매칭 N/N).
- relink 후: 위키독스에서 같은 폴더 내부 링크 클릭이 대상 페이지로 이동.

## 블록/주의

- **push 는 GLG만.** 커밋까지가 에이전트 몫. push = 위키독스 라이브 반영.
- **가든 read-only.** `~/repos/gh/notes/content` 절대 수정 금지.
- **민감어 하드코딩 금지.** 코드·문서에 회사/직장 핸들을 literal 로 쓰면 pre-commit 훅이
  막는다. 난독화 규칙은 가든 `change-text.sh` 에서 런타임에만 읽는다.
- **보안 메모(GLG 결정 대기)**: 가든 `change-text.sh` 가 어떤 회사 핸들의 특정 번호 변형
  하나만 난독화하는데, 훅은 그 핸들의 전 변형을 막는다. journal 에 미난독화 변형(회사
  자체호스팅 URL)이 실재해 export 는 전 변형을 일반화 처리했다. 가든 change-text.sh 도 베이스
  형태로 고치면 공개 가든의 잔여 노출이 사라진다 — 여기서는 가든을 안 건드림.

## 다듬을 거리 (기능 아님, 차차)

citeproc 항목 2칸 들여쓰기, LLM 대화 `@user`/`@assistant` 마커, `<url>` 오토링크,
코드펜스 안 relref literal(코드 예시라 정상).
