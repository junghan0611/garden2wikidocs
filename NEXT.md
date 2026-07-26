# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
정본/미러 정책은 garden `docs/WIKIDOCS_MIRROR.md`.

## NOW — 코어 판본 발행 완료, status.py만 코어를 모른다

- **Current**: 위키독스가 `TOC.md` 등록 500개 상한을 사후 도입해 07-19부터 동기화가
  막혀 있었다. 2026-07-26에 발행면을 코어로 줄여 되살렸다. 라이브 249개
  (챕터 표지 5 + 본문 244 = autholog 태그 170 ∪ botlog 폴더 80). 저널·메타·참고문헌·노트
  본문은 발행면 밖이고 표지에서 가든으로 잇는다. 리포는 2,239개 전량을 보존한다.
- **파이프라인**: `build --core --garden-links` → `audit --core --garden-links` → tests.
  relink는 현재 돌리지 않는다(링크 전부 가든). 상한 초과 TOC는 build가 쓰기 전에 실패한다.
- **Next**: (1) `status.py`에 발행면 개념을 넣는다 — 지금은 로컬 `pages/**` 전량을 분모로
  써서 코어 모드에서 `미생성 1996개`가 정상인데도 오류처럼 보인다. TOC 등록분만
  synced/pending으로 세고 나머지는 `unpublished`로 따로 보고할 것. (2) 그 다음에야
  `0 어쏠로그` 집합 표지 복원을 검토한다(신규 page_id 2단계 push 필요, 여유 251).
- **Blocker**: 없음. 07-26 12:42 push는 생성 0/삭제 0의 본문 갱신이고 웹훅이 정상 처리 중이다.
- **Verify**: `audit --core --garden-links` 통과 + `unittest` 31/31 + 같은 명령 두 번 빌드
  sha256 diff 0줄. push 전에는 라이브 gid와 새 TOC를 대조해 생성/삭제 0을 확인한다.
- **Read**: SKILL.md의 「실측으로 확정된 불변식」 상단 4개, `build.py`의 `PUBLISH_LIMIT`/
  `link_target`/`readme_meta_block`, `relink.py`의 발행면 게이트.
- **Do not touch**: `~/repos/gh/notes` 원본, 민감어 하드코딩. 발행면 밖 page_id로 링크를
  만들지 않는다(audit이 잡는다). push는 웹훅 전체를 촉발하므로 GLG의 현재 세션 명시 요청 전 금지.

## RECENT

- [2026-07-26] 500 상한의 정체를 실측 확정했다. 게이트는 `TOC.md` 등록 줄 수이고 델타
  크기와 무관하다. TOC에서 뺀 페이지는 라이브에서 삭제되며(2243→249, 빠진 주소 404)
  복구 경로가 없다. 다만 살아남은 244개는 page_id가 하나도 안 바뀌었다. 계약을 build/
  relink/audit/SKILL에 반영하고 테스트 8개를 추가했다(23→31).
- [2026-07-26] 책 대문의 '미러링한 책' 문구를 걷어 내고 '디지털가든 코어'로 바꿨다.
  발행 규모는 build가 실측해 넣는다. 근거 노트는 garden `20230706T160800`.
- [2026-07-19] 어쏠로그 집합 표지 push가 500에 막혀 실패했고, 07-26에 발행면을
  8a49fa6 상태로 되돌린 뒤 재출발했다. 표지 파일은 리포에 남아 있다.

## PARKED

- 코어끼리 위키독스 내부 순회 살리기: `--garden-links` 없이 build → `relink.py`.
  relink는 TOC 등록분만 실화하므로 죽은 링크는 안 생긴다. 발행면이 안정된 뒤에 판단한다.
- 한글·영어 페어 발행: 코어 2벌은 500 상한을 넘으므로 별도 book이 필요하다.
- rich chapter landing(recent-20 card + archive), sidebar 순번 재부여 금지.
