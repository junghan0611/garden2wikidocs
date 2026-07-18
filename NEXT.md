# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
릴리즈 이력은 `CHANGELOG.md`.

## NOW — garden 정본 ↔ WikiDocs 발견면 provenance 계약 구현·검증 완료

- **Policy SSOT**: garden
  [`docs/WIKIDOCS_MIRROR.md`](https://github.com/junghan0611/garden/blob/main/docs/WIKIDOCS_MIRROR.md)
  (로컬: `/home/junghan/repos/gh/notes/docs/WIKIDOCS_MIRROR.md`). garden은
  canonical/latest/authored source, WikiDocs는 discovery mirror, 이 리포는 garden을
  바꾸지 않는 read-only translation harness다. source authority/publication ordering은
  여기서 재정의하지 않는다.
- **Current**: commit/push 없이 provenance·정렬 생성물은 유지하고 재현 입력 gate를 추가.
  기존 `main...origin/main [ahead 3]` 보존 + 이번 작업은 uncommitted. push는 약 20분짜리
  전체 WikiDocs webhook을 촉발하므로 audit 이전 push 금지, GLG가 한 번만 결정한다.
- **Implementation**: garden frontmatter `title/description/date/lastmod` exact scalar 수신;
  journal 제목·정렬=`source_date`, 나머지=`source_lastmod→source_date`, 모두 newest-first.
  WikiDocs sidebar 강제 오름차순과 싸우는 불안정 번호 대신 챕터 cover 5개에 stable URL 기반
  explicit recent-first index를 생성. 모든 페이지에 abstract-first `원본·최신본` 블록;
  provenance exact source URL은 relink 보호; mapping에 `source_url/source_date/source_lastmod`
  cache 추가. 기존 `page_id/url` 2238/2238 승계. `BUILD-MANIFEST.json`은 garden full SHA,
  content/change-text clean gate, selected-input deterministic SHA256을 고정한다.
- **Generated**: 2,238 pages 전부 재생성, 2,120 authored abstract가 provenance보다 먼저,
  abstract 없는 118 pages는 provenance가 첫 본문 블록. source_lastmod 없는 60 pages는
  source_date fallback. 제목 1,278개가 folder별 source date 정책으로 갱신됨.
- **Validation**: unittest **20/20**, audit **2,238/2,238 통과**; manifest schema/source
  commit/clean/folders/pages/content hash exact match; TOC와 chapter index 5개
  source newest-first·page_id/url/path/source_url uniqueness·garden completeness·gid/source URL
  join·source metadata/title·provenance exact 1개·abstract ordering·헤딩·relref 전부 통과.
  relink 22,228 note links + 7 folder links 실화. 최종 mapping SHA256:
  `eb81393e3ad9ff8e74904044bac81bd215455ba7cdf7d09ca67e890d803c66e3`.
  garden 최종 import snapshot과 exact match(mapped/unique 2,238, unmapped 0), JSON-LD/가시 링크
  2,238/2,238 재검증 완료. garden은 `f7688814`(mirror link)·`cdaec167`(저널),
  profile llms는 `ffd9706`까지 push 완료.
- **Diff**: tracked 2,252 files `+46,881/-17,564` + new `BUILD-MANIFEST.json` 16 lines
  = worktree 2,253 files, combined `+46,897/-17,564` (prior pages 2,238 + chapter index 5 +
  mapping/TOC/README + code/docs/tests/manifest).
- **Blocker**: 없음. garden 조정 세션에 검증 결과 보고 후 추가 요청 대기.
- **Read**: garden `docs/WIKIDOCS_MIRROR.md`, `BUILD-MANIFEST.json`, `build.py`, `relink.py`,
  `audit.py`, `tests/test_build.py`, `scripts/status.py`, 이 skill.
- **Do not touch**: `~/repos/gh/notes` 원본, 민감어 하드코딩, 기존 tag 이동.
  commit/push 금지(이번 조정 요청). 특히 push=전체 웹훅 재동기화 트리거다.

## PARKED — rich chapter landing

- 현재 explicit recent-first bare index는 기능적 v1이며 `[[SubPages]]`를 의도적으로 쓰지 않는다.
- recent-20 rich card + time-group archive 형태의 챕터 대문은 후속으로 검토한다.
- WikiDocs sidebar 제목 오름차순 한계는 stable title/page_id를 깨지 않고 별도 제약으로 둔다.

## 상시 갱신 사이클

```text
existing IDs: build → relink → audit → tests/(optional gitleaks) → GLG commit/push → status
new IDs: build → relink → audit --allow-missing-page-ids → 1차 push/status
         → recover → relink → audit → 2차 commit/push/status
```

어떤 경우에도 build 직후 audit 전 push하지 않는다. 상세 명령은 SKILL의 실행 절이 SSOT다.
