# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
릴리즈 이력은 `CHANGELOG.md`.

## NOW — 라이브 반영·사이드바 보정 완료, 확장문법 육안점검만 남음

- **Current**: RELREF·TOC 복구(`6ce35a2`)+따옴표·CSL(`6130954`) push, 웹훅 동기화
  **2238/2238(100%) 라이브 확인**(botlog 382592 = 172줄 복구). 사이드바 챕터 4·5
  누락은 위키독스 서버측 TOC 1000노드 하드캡이 원인 → 책 설정 `user_script`로 보정 완료.
- **Next**: 위키독스 확장문법 육안점검(정상 테이블 렌더, 각주 `[^name]`, `[TOC]` 실화).
- **Blocker**: 없음.
- **Read**: `wikidocs-user-script.js`(사이드바 보정 원본), `tests/test_build.py`,
  `.claude/skills/garden-to-wikidocs/scripts/audit.py`, 이 파일의 검증 기준.
- **Do not touch**: `~/repos/gh/notes/content` 원본, 민감어 하드코딩, 기존 tag 이동.

## 이후 선택지

- 위키독스 확장문법 정합성 육안점검: 정상 테이블 렌더, 각주 `[^name]`, `[TOC]` 실화.
- 사이드바 챕터 인덱스는 헤더만 노출한다. 노트·봇로그 하위 목록까지 사이드바에서
  펼치려면 `wikidocs-user-script.js`에 mapping.json 기반 전체 트리를 임베드하는
  확장을 검토(현재는 챕터 커버의 `[[SubPages]]` 목록으로 하위 진입).

## 상시 갱신 사이클

```text
build.py --folders journal,meta,bib,notes,botlog
→ relink.py
→ audit.py
→ GLG push
```

새 페이지가 생겨 page_id가 비어 있을 때만 첫 동기화 뒤 `recover → relink → audit → push`를
한 번 더 수행한다.
