# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
정본/미러 정책은 garden `docs/WIKIDOCS_MIRROR.md`.

## NOW — 코어 내부 순회 살림 + 어쏠로그 표지 발행, 미커밋

- **Current**: 라이브는 아직 07-26 판본(249개)이다. 워킹트리에는 검수까지 끝낸 다음
  판본이 있다 — 챕터 표지 6 + 본문 244 = **250개**. `0 어쏠로그` 집합 표지를 코어
  발행면에 넣었고(코어 정의의 절반인 autholog를 커버하는 표지가 없었다), 코어 안에서는
  링크를 위키독스로 실화한다. 리포는 2,239개 전량 보존.
- **파이프라인**: `build --core` → `relink` → `audit --core`. **`--garden-links` 는 더 이상
  기본이 아니다**(발행면 갈아엎을 때만 켜는 안전판). build가 `pages/`를 rmtree하므로
  build를 돌렸으면 relink도 반드시 다시 돌린다.
- **Next**: ① GLG 승인 후 커밋. ② 가든 org 원문(`20230706T160800`)이 07-26 12:45까지
  갱신됐는데 markdown export는 07-22 판본 — org export → garden commit → 위 3단계 재실행.
  ③ 신규 page_id 2단계 push: `audit --core --allow-missing-page-ids` → 1차 push → status →
  `recover` → build/relink → `audit --core` → 2차 push. ④ 1차 push 후 회수한 어쏠로그
  page_id로 `wikidocs-user-script.js` 의 `CH[0]` 을 채우고 **위키독스 책 설정에 다시
  붙여넣는다**(웹훅이 안 나르는 파일이다).
- **Blocker**: 없음. 미커밋 상태만 유지 중.
- **Verify**: `audit --core --allow-missing-page-ids` 통과(warn 1 = 어쏠로그 표지 미회수는
  2차 push 전까지 정상) + `unittest` 64/64 + 같은 명령 두 번 빌드 sha256 diff 0줄 +
  relink 재실행 시 바뀐 파일 0 + `status.py` 가 발행면 기준 100%/exit 0. push 전에는
  라이브 gid와 새 TOC를 대조해 생성/삭제 수를 먼저 확인한다.
- **Read**: SKILL.md의 「실측으로 확정된 불변식」 — 특히 relink 양방향 게이트, 어쏠로그
  0순위 챕터, 사용자 스크립트 항목. `build.py`의 `PUBLISH_LIMIT`/`is_core_member`/
  `link_target`, `relink.py`의 `relink_targets`, `audit.py`의 `user_script_findings`.
- **Do not touch**: `~/repos/gh/notes` 원본, 민감어 하드코딩. 발행면 밖 page_id로 링크를
  만들지 않는다(audit이 잡는다). push는 웹훅 전체를 촉발하므로 GLG의 현재 세션 명시 요청 전 금지.

## RECENT

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
- rich chapter landing(recent-20 card + archive), sidebar 순번 재부여 금지.
