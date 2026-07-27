# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
정본/미러 정책은 garden `docs/WIKIDOCS_MIRROR.md`.

## NOW — 가든 재export 뒤 AEO 판본 갱신

- **Current**: 챕터 표지 6개를 `## 제목 / source 날짜·태그 / description / 읽기 링크`의
  AEO 구조로 전환했다. 2,239개 폴더 항목 + autholog 170개를 exact regeneration과 독립
  구조 게이트로 검증하며, 원본 노트나 생성물을 손편집하지 않는다.
- **Next**: 다음 텀에 org 원문을 garden markdown으로 export·commit → 이 리포에서
  `build --core` → `relink` → `audit --core` → 테스트 → 승인 push. 신규 page_id가 없으면
  1단계로 끝난다.
- **Blocker**: 없음. 이번 AEO 판본은 현재 garden commit 기준으로 push하고, 원문 추가 갱신은
  다음 텀으로 분리한다.
- **Verify**: `audit --core` 경고 0, unittest 72/72, build→relink 2회 sha256 diff 0,
  relink 재실행 변경 0, TOC 250노드·죽은 page_id 링크 0.
- **Read**: `.claude/skills/garden-to-wikidocs/SKILL.md`의 recent-first AEO 표지·mapping cache.
- **Do not touch**: `~/repos/gh/notes` 또는 `pages/` 생성물을 손편집하지 않는다. 항상 정본
  export를 입력으로 전체 재생성한다.

## DONE — 코어 내부 순회 살림 + 어쏠로그 표지 발행 (2026-07-27 push 완료)

- 라이브 **250개**(챕터 표지 6 + 본문 244), 245/245 100% 동기화 확인.
- 2단계 push 완료: `75af479`(1차) → recover(어쏠로그 표지 page_id **386464**) →
  `af09168`(2차). `audit --core` 가 `--allow-missing-page-ids` 없이 경고 0으로 통과한다.
- GLG 가 `wikidocs-user-script.js` 를 위키독스 책 설정에 붙여넣어 반영 확인했다
  (`CH[0]` = 386464, DOM 폴백 0).
- GitHub 이슈 #1·#2·#3 전부 CLOSED.

### 상시 유지 규칙 (이 리포에서 계속 지킬 것)

- **파이프라인**: `build --core` → `relink` → `audit --core`. `--garden-links` 는 기본이
  아니라 발행면을 갈아엎을 때만 켜는 안전판이다. build 가 `pages/` 를 rmtree 하므로
  **build 를 돌렸으면 relink 도 반드시 다시 돌린다.**
- **Verify**: `audit --core` 통과 + `unittest` 72/72 + 같은 명령 두 번 빌드 sha256 diff 0줄
  + relink 재실행 시 바뀐 파일 0 + `status.py` 가 발행면 기준 100%/exit 0. push 전에는
  라이브 gid와 새 TOC 를 대조해 생성/삭제 수를 먼저 확인한다.
- **신규 page_id 가 생기면 2단계 push**: `audit --core --allow-missing-page-ids` → 1차 push
  → status → `recover` → build/relink → `audit --core` → 2차 push. 표지가 새로 생겼다면
  회수한 page_id 로 `wikidocs-user-script.js` 의 `CH` 를 고치고 **위키독스 책 설정에 다시
  붙여넣는다**(웹훅이 안 나르는 파일이다).
- **Read**: SKILL.md의 「실측으로 확정된 불변식」 — 특히 relink 양방향 게이트, 어쏠로그
  0순위 챕터, 사용자 스크립트 항목. `build.py`의 `PUBLISH_LIMIT`/`is_core_member`/
  `link_target`, `relink.py`의 `relink_targets`, `audit.py`의 `user_script_findings`.
- **Do not touch**: `~/repos/gh/notes` 원본, 민감어 하드코딩. 발행면 밖 page_id로 링크를
  만들지 않는다(audit이 잡는다). push는 웹훅 전체를 촉발하므로 GLG의 현재 세션 명시 요청 전 금지.

## RECENT

- [2026-07-27] 챕터 표지 6개를 AEO 구조로 바꿨다. 폴더 2,239개 항목과 autholog 170개가
  깨끗한 `##` 제목, 작성·수정일·태그, description, 목적지 명시 링크를 가진다. mapping은
  scrub된 description/tags를 cache하고 audit은 exact match + heading 유일성 + 링크 수·순서를
  독립 검증한다. 빈 description 1건은 요약만 생략한다. 테스트 72/72, 표지 합계 870,766B,
  재현성·relink 멱등성·교차검수 통과.
- [2026-07-27] 코어 안에서 위키독스 내부 순회를 살렸다(내부 순회율 33%, 나머지는 코어
  밖으로 나가는 링크라 가든이 맞다). relink에 **쓰기 게이트**를 추가한 게 핵심 — 대상만
  막고 파일은 안 막아서 발행면 밖 639개를 흔들고 있었다(826→185개). `TOC.md` 부재 시
  fail-open도 exit 1로 닫았다. 어쏠로그 집합 표지를 코어에 발행(249→250). 사용자 스크립트는
  1000노드 캡 전제가 무너진 걸 주석에 반영하고, CH 배열↔TOC↔mapping 대조를 audit 게이트로
  못 박았다. 테스트 32→64. 별동대 검수 2라운드(지적 2건 반영 후 통과).
- [2026-07-26] 별동대 검수 이슈 3건을 반영했다. #1 status.py가 TOC 발행면을 분모로
  쓰고 미발행을 따로 보고한다. #2 발행 예산을 생성물 삭제·재생성 전에 검사한다
  (입력을 먼저 읽고 `is_core_member` 한 규칙으로 사전·사후 계산을 맞춘다). #3 대문
  분모를 '미러 대상 5개 폴더 2,239개'로 명시했다. 테스트 31→32.
- [2026-07-26] 500 상한의 정체를 실측 확정했다. 게이트는 `TOC.md` 등록 줄 수이고 델타
  크기와 무관하다. TOC에서 뺀 페이지는 라이브에서 삭제되며(2243→249, 빠진 주소 404)
  복구 경로가 없다. 다만 살아남은 244개는 page_id가 하나도 안 바뀌었다. 계약을 build/
  relink/audit/SKILL에 반영하고 테스트 8개를 추가했다(23→31).
- [2026-07-26] 책 대문의 '미러링한 책' 문구를 걷어 내고 '디지털가든 코어'로 바꿨다.
  발행 규모는 build가 실측해 넣는다. 근거 노트는 garden `20230706T160800`.
- [2026-07-19] 어쏠로그 집합 표지 push가 500에 막혀 실패했고, 07-26에 발행면을
  8a49fa6 상태로 되돌린 뒤 재출발했다. 표지 파일은 리포에 남아 있다.

## PARKED

- 저널·참고문헌·메타 표지의 링크 이탈: 이 셋은 위키독스 안에서 내부 링크가 0~1개고
  1,322개 항목이 전부 가든으로 나가는 문이다(저널 0/104, 참고문헌 0/680, 메타 1/538).
  GLG 판단으로 현재는 그대로 둔다 — 코어에 담은 노트 링크만 살리는 게 이번 목표였다.
  코어 판본에서 이 표지들을 어떻게 다룰지는 따로 정한다.
- 한글·영어 페어 발행: 코어 2벌은 500 상한을 넘으므로 별도 book이 필요하다.
- sidebar 순번 재부여 금지(stable title/page_id 를 깨뜨린다).
- rich chapter landing(recent-N card + archive)은 NOW 의 AEO 재설계로 흡수됐다.
