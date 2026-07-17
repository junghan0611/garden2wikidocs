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

## RECENT — 2026-07-17

- 웹훅 대량 동기화 2238/2238(100%) 라이브 확인. 챕터 순서·노드 2243·botlog
  `20260407T093255`(page 382592) 172줄 복구·mapping 2238/2238 모두 충족.
- 사이드바에 챕터 4·5 누락 원인 규명: 위키독스 리더 TOC가 서버측에서 **1000노드
  하드캡**(raw HTML `data-id` 정확히 1000). 2243노드라 참고문헌 중간에서 잘려 노트·
  봇로그 헤더가 emit 안 됨. 접기(open_yn/localStorage)로는 복구 불가.
- 책 설정 `user_script`(JS)로 사이드바 최상단에 전체 챕터 인덱스 주입 → 5개 챕터
  전부 표시. 원본은 `wikidocs-user-script.js`. GitHub 콘텐츠 동기화가 안 건드려 유지됨.
- RELREF가 일반 `[대괄호]`부터 뒤 링크까지 줄바꿈을 넘어 삼키던 결함 수정.
  전수 조사상 1788/2238페이지, 횡단 매치 2984건, 약 80759줄 손실 범위였음.
- RELREF 치환 전후 줄바꿈 수가 달라지면 build가 즉시 실패하는 런타임 게이트 추가.
- TOC 중단의 직접 구조 원인은 기존 1413행 제목의 중첩 `[클로드데스크톱]`.
  그 뒤 참고문헌·봇로그가 누락되는 관찰과 일치.
- 노트 입력용 유니코드와 중첩 `[]`를 TOC 제목에서 평문화. TOC 위험문자 0건.
- TOC 순서를 `1 저널·2 메타·3 참고문헌·4 노트·5 봇로그`로 코드에서 고정.
- 기존 mapping의 page_id 2238개와 챕터 5개를 build가 승계. 갱신은
  `build → relink → audit → push` 한 번으로 가능.
- 원본의 상대 relref 오류 1건은 깨진 URL 대신 평문으로 안전하게 내보냄.
- `audit.py`: TOC·mapping·gid·page_id·미처리 relref·원본/미러 헤딩 보존 검증.
- 같은 파이프라인 재실행 전후 diff 해시가 동일하여 결정성 확인.
- 양 끝이 같은 따옴표만 벗겨 내부 `'제목'`·`"제목"`의 닫는 문자를 보존.
- citeproc 참고문헌 1123파일·3545항목을 들여쓰기 문단이 아닌 `- ` 목록으로 변환.

## 라이브 검증 기준

1. 위키독스 최상위 챕터 5개가 숫자 순서로 모두 보임.
2. `3 참고문헌` 하위 680페이지와 그 뒤 `4 노트`, `5 봇로그`가 목록에 보임.
3. 노드 총수 2243(페이지 2238 + 챕터 5), 중복 챕터 없음.
4. `pages/botlog/20260407T093255.md` 대응 라이브 페이지에서 헤딩·표·문단 복구.
5. `mapping.json`: page_id 2238/2238, `_chapters` 5/5.

## 이후 선택지

- 위키독스 확장문법 정합성: 정상 테이블 렌더, 각주 `[^name]`, `[TOC]` 실화 확인.
- 라이브 검증 뒤 follow-up 태그 `v2026.7.17-fix.1` 검토.

## 상시 갱신 사이클

```text
build.py --folders journal,meta,bib,notes,botlog
→ relink.py
→ audit.py
→ GLG push
```

새 페이지가 생겨 page_id가 비어 있을 때만 첫 동기화 뒤 `recover → relink → audit → push`를
한 번 더 수행한다.
