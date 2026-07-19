# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
정본/미러 정책은 garden `docs/WIKIDOCS_MIRROR.md`.

## NOW — autholog 가상 챕터 1차 동기화 대기

- **Current**: 가든 원본은 무수정/read-only로 두고, 전 canonical folder의 frontmatter
  `tags`에서 `autholog` 160건을 골라 `pages/autholog/_chapter.md`에 `lastmod` 역순으로
  모았다. TOC에는 authored folder보다 앞선 standalone `0 어쏠로그`로 추가했다. 원본 페이지를 복제하지 않고 기존
  WikiDocs URL만 잇는다.
- **Link contract**: 집합 표지는 `<!-- collection:autholog -->` marker로 회수하고
  `mapping.json`의 `_chapters.autholog`에 page_id를 둔다. recover 뒤 relink가 README의
  `/tags/autholog/` 두 링크를 새 WikiDocs 표지로 바꾼다. 집합 표지 자체의 provenance
  가든 URL은 보호한다.
- **Validation**: unittest 23/23, py_compile, diff-check 통과. audit은 authored page
  2,238/2,238 + folder index 5 + autholog collection 160건을 통과했고, 신규 집합 표지의
  page_id 1개만 의도적으로 missing이라 `--allow-missing-page-ids`를 사용했다.
- **Next**: 1차 push로 새 표지를 생성한 뒤 (1) status에서 `collection:autholog` 확인,
  (2) `recover → relink → audit → tests`, (3) 실제 page_id를 사용자 스크립트에 고정,
  (4) GLG 승인 후 2차 commit/push/status.
- **Blocker**: WikiDocs가 새 표지에 page_id를 부여하기 전에는 README autholog 링크가 가든
  fallback인 것이 정상이다.
- **User script**: `wikidocs-user-script.js`의 챕터 탐색면에도 `0 어쏠로그`를 맨 앞에
  추가했다. page_id 회수 전에는 `null` entry가 서버 TOC의 0번 링크를 DOM에서 자동 탐색하며,
  회수 후 실제 ID로 교체할 수 있다.
- **Read**: `pages/autholog/_chapter.md`, `wikidocs-user-script.js`, `build.py`의
  `COLLECTIONS/collection_index`, `recover.py`, `relink.py`, `audit.py`.
- **Do not touch**: `~/repos/gh/notes` 원본, 민감어 하드코딩, 기존 태그. push는 전체
  webhook을 촉발하므로 GLG의 현재 세션 명시 요청 전 금지.

## RECENT

- [2026-07-19] README의 가든 태그 링크가 WikiDocs 안에서 self-contained 탐색면으로
  착지하도록 build/recover/relink/audit/status/tests 전 단계를 확장했다.
- [2026-07-18] source provenance·folder별 source date 정렬·재현 manifest·5개 폴더
  recent-first index를 2,238페이지에 적용해 배포 완료했다.

## PARKED — rich chapter landing

- bare recent-first index를 recent-20 card + time-group archive로 꾸미는 일은 별도 검토한다.
- stable title/page_id를 깨는 sidebar 순번 재부여는 하지 않는다.
