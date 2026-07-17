# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
릴리즈 이력은 `CHANGELOG.md`.

## NOW — 가든 refresh 재내보내기·웹훅 반영 100%·확장문법 육안점검 완료

- **Current**: 가든 refresh(notes `aa36a538`) 재내보내기 `build→relink→audit→push`
  = `1f15570` push. 172 페이지 콘텐츠 갱신 + 신규 assets 20개, 신규 .md 0(recover 불필요).
  웹훅 반영 **2238/2238(100%), pending 0, missing 0 라이브 확인**(23:05 push→23:25 완료,
  수동 재트리거 없이 자연 수렴). status.py 로 측정.
- **New tool**: `scripts/status.py` — book get 라이브 본문 vs 로컬 pages/ 대조로
  synced/pending/missing 카운트(exit0=완료). 이미지 URL 은 위키독스 CDN 재작성 흡수 위해
  `![](IMG)` 로 중립화. 이전 세션마다 재현하던 삽질을 스킬로 고정.
- **확장문법 육안점검 완료(브라우저)**: 각주 `[^name]`→위첨자+하단 ↩(`381076`),
  `[TOC]`→번호 목차박스, 테이블→경계선 HTML 표(셀 내 인라인코드 포함, `382600`),
  콜아웃 박스·relref 파란링크 실화·사이드바 챕터인덱스 전부 정상. 잔여 검증 없음.
- **Next**: 상시 갱신 사이클만. 다음 가든 refresh 때 build→relink→audit→push→status.
- **Blocker**: 없음.
- **Read**: `scripts/status.py`, `wikidocs-user-script.js`(사이드바 보정), `tests/test_build.py`,
  `scripts/audit.py`, SKILL.md 배포·동기화 절.
- **Do not touch**: `~/repos/gh/notes/content` 원본, 민감어 하드코딩, 기존 tag 이동.
  이 리포는 push=웹훅 재동기화 트리거 — 스킬/문서만 고친 커밋은 GLG 가 push 타이밍을 정한다.

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
→ status.py --list   # 웹훅 반영 확인, pending 0 까지(멈추면 수동 재동기화)
```

새 페이지가 생겨 page_id가 비어 있을 때만 첫 동기화 뒤 `recover → relink → audit → push`를
한 번 더 수행한다.
