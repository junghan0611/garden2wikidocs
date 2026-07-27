# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
정본/미러 정책은 garden `docs/WIKIDOCS_MIRROR.md`.

## NOW — 발행면 신규 진입 자동 처리 (커밋 완료, push 대기)

- **Current**: 죽은 page_id 승계를 `build.py` 에서 막았다. 덮어쓰기 전 `TOC.md` 를 읽어
  발행면에 새로 들어오는 항목의 page_id 를 승계하지 않는다. 발행면 밖에 머무는 항목은
  건드리지 않는다. 회수 이력이 있는데 직전 판 TOC 를 못 읽으면 생성물을 쓰기 전에 멈춘다
  (fail-closed). 생성물은 바이트 동일(no-op)이다.
- **Next**: GLG 타이밍에 push. **콘텐츠 변경이 아니라 스킬 수선 커밋이므로 push 하면 웹훅
  전체 재동기화가 돈다** — 다음 가든 export 와 묶어 한 번에 내보내는 편이 싸다.
- **Blocker**: 없음.
- **Verify**: `audit --core` 경고 0, unittest 83/83, build→relink 후 생성물 diff 0줄
  (스킬/테스트 파일만 변경), 라이브 247/247 100%.
- **Read**: SKILL.md 「삭제된 페이지의 page_id 는 부활하지 않는다」 + 그 뒤 두 불변식
  (fail-closed 경계, warning 두 층), `build.py` 의 `previous_publish_surface`/
  `has_recovered_ids`/`inherit_remote_id`.
- **Do not touch**: `~/repos/gh/notes` 또는 `pages/` 생성물을 손편집하지 않는다. 항상 정본
  export를 입력으로 전체 재생성한다.

## DONE — 가든 증분 미러 + 죽은 page_id 차단 (2026-07-27 push 완료)

- 가든 `8fe0ff7a8 → 2af482c98`(수정 103, 신규 주간저널 1). 라이브 **252개**, 247/247 100%.
- `autholog` 170→172 로 발행면이 244→246 이 됐는데, 새로 들어온 두 노트가 하필 500 컷 때
  삭제된 페이지였다. mapping 의 옛 page_id 는 죽은 값이었고 링크 20개(13개 파일)가 404 로
  나갈 뻔했다. `status.py` 의 `미생성` 이 유일한 신호였다.
- 2단계 push: `3cee8c7`(1차, 죽은 id 를 비운 채) → recover(**387071/387072** 신규 발급 확인,
  옛 381403/381716 은 부활하지 않음) → `d9e68bc`(2차, 링크 20개 실화).
- 이전 판: 2단계 push `75af479` → 어쏠로그 표지 page_id **386464** → `af09168`.
  GLG 가 `wikidocs-user-script.js` 를 책 설정에 붙여넣어 반영 확인(`CH[0]`=386464).
- GitHub 이슈 #1·#2·#3 전부 CLOSED.

### 상시 유지 규칙 (이 리포에서 계속 지킬 것)

- **파이프라인**: `build --core` → `relink` → `audit --core`. `--garden-links` 는 기본이
  아니라 발행면을 갈아엎을 때만 켜는 안전판이다. build 가 `pages/` 를 rmtree 하므로
  **build 를 돌렸으면 relink 도 반드시 다시 돌린다.**
- **Verify**: `audit --core` 통과 + `unittest` 83/83 + 같은 명령 두 번 빌드 sha256 diff 0줄
  + relink 재실행 시 바뀐 파일 0 + `status.py` 가 발행면 기준 100%/exit 0. push 전에는
  라이브 gid와 새 TOC 를 대조해 생성/삭제 수를 먼저 확인한다.
- **신규 page_id 가 생기면 2단계 push**: `audit --core --allow-missing-page-ids` → 1차 push
  → status → `recover` → build/relink → `audit --core` → 2차 push. 표지가 새로 생겼다면
  회수한 page_id 로 `wikidocs-user-script.js` 의 `CH` 를 고치고 **위키독스 책 설정에 다시
  붙여넣는다**(웹훅이 안 나르는 파일이다).
- **어쏠로그 태그를 붙이면 그게 신규 page_id 다.** 새 노트가 없어도 기존 노트가 발행면에
  들어오면 컷 때 삭제된 페이지라 옛 id 가 죽어 있다. build 의 `[warn] 발행면 page_id
  미회수 N개` 가 절차 트리거이고, 뒤따르는 `그중 M개는 발행면 신규 진입` 은 안전장치가
  발동했다는 부분집합 신호다(0 이어도 회수는 필요할 수 있다). push 전 `status.py --list`
  의 `미생성` 으로 라이브를 한 번 재는 것이 유일한 실측 확인이다.
- **Read**: SKILL.md의 「실측으로 확정된 불변식」 — 특히 relink 양방향 게이트, 어쏠로그
  0순위 챕터, 사용자 스크립트 항목. `build.py`의 `PUBLISH_LIMIT`/`is_core_member`/
  `link_target`, `relink.py`의 `relink_targets`, `audit.py`의 `user_script_findings`.
- **Do not touch**: `~/repos/gh/notes` 원본, 민감어 하드코딩. 발행면 밖 page_id로 링크를
  만들지 않는다(audit이 잡는다). push는 웹훅 전체를 촉발하므로 GLG의 현재 세션 명시 요청 전 금지.

## RECENT

- [2026-07-27] 삭제된 페이지의 page_id 가 부활하지 않는다는 걸 실측하고, 그 죽은 값이
  발행면에 되들어올 때 조용히 실리는 경로를 `build.py` 에서 닫았다. 게이트 셋(`link_target`
  ·`relink`·`audit`)이 전부 TOC 멤버십만 보고 라이브 존재를 안 봐서 아무도 안 울렸다.
  지피티 교차검수에서 2건을 더 잡았다 — 내 fresh-clone 가드가 "TOC 없음"과 "TOC 손상"을
  뭉개 정작 위험한 상태에서 fail-open 했고(회수 이력 있으면 abort 로 정정), warning 이
  죽은 id 를 비운 항목만 세서 처음 올라가는 페이지를 놓쳤다(미회수/보류 두 층으로 분리).
  테스트 72→83.
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
