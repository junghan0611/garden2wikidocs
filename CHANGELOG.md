# CHANGELOG

정한(Junghan Kim)의 디지털 가든 <https://notes.junghanacs.com> → 위키독스 책
(`book_id 20676`) 미러링 파이프라인 변경 이력. CalVer 스냅샷.

## Unreleased

## v2026.7.17 — 가든 전체 폴더 미러 완성

첫 릴리즈. 폴더 미러 3단계 파이프라인으로 가든 전체를 위키독스 책으로 내보내고
내부 순회를 자기완결화했다.

### 파이프라인 (build → recover → relink, stdlib only)
- `build.py` 씨뿌리기: 가든 폴더를 위키독스 챕터로 미러. denote-id 파일명, 날짜
  접두어 제목(알파벳 강제정렬 대응), callout·relref·citeproc·figure·이미지 변환,
  회사신원 scrub(가든 `change-text.sh` 런타임 로드), 코드펜스 보호.
- `recover.py` 회수: `<!-- gid:ID -->` 앵커로 denote-id↔page_id 매칭해 `mapping.json`
  을 채우고, 챕터 표지(폴더) page_id 를 `_chapters` 로 회수.
- `relink.py` 링크 실화: 내부 가든 URL 중 page_id 있는 것만 `wikidocs.net/<id>` 로
  재작성(하이브리드), 폴더 인덱스 링크는 챕터 표지 URL 로. 코드펜스 보호, idempotent.

### 내보내기 결과 (라이브 검증됨)
- 5개 폴더 씨뿌리기: journal 103 · meta 538 · notes 837 · bib 680 · botlog 80 =
  **2238 페이지**, assets 773개.
- 회수: **page_id 2238/2238**, 챕터 표지 5개.
- 링크 실화: 내부 노트 링크 21786개 + 폴더 링크 7개 → 위키독스 안 자기완결 순회.
- 웹훅 동기화(2243 노드)·relink 콘텐츠 반영을 API 폴링으로 확인.

### 대문 (README = 위키독스 책 대문)
- 가든 `content/index.md` 를 변환해 `README.md`(책 대문)로 빌드마다 재생성.
- 대문 상단 가든 크롤러용 'AI visitors' 블록쿼트를 위키독스 미러 안내로 교체.
- README 의 `folder: journal/meta/notes/bib/botlog` 링크를 챕터 표지 URL 로 실화.

### 불변식 (실험 A~D 로 검증)
- URL = page_id 기반, 매우 안정적(파일명·제목·순서를 바꿔도 유지).
- 파일명 = denote-id, 제목은 TOC 가 관리, 페이지 간 링크는 page_id 절대 URL만 작동.

### 리포
- `.pi/settings.json` 추적, `.claude/settings.local.json`·`__pycache__/` 이그노어.
- 메커니즘·불변식 SSOT: `.claude/skills/garden-to-wikidocs/SKILL.md`.
