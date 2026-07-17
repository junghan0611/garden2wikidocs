# NEXT — garden2wikidocs

메커니즘·불변식 SSOT는 `.claude/skills/garden-to-wikidocs/SKILL.md`.
릴리즈 이력은 `CHANGELOG.md`.

## NOW — RELREF·TOC 품질 복구를 라이브 반영할 차례

- **Current**: 전체 2238페이지 재빌드·로컬 relink 완료. 테스트 8개와 `audit.py` 통과.
  작업 트리에 코드·테스트·감사 도구와 생성물 1788페이지 복구분이 있음.
- **Next**: (1) diff/보안 훅 검토 후 커밋 → (2) GLG push → (3) 웹훅 동기화 폴링 →
  (4) 참고문헌·노트·봇로그 TOC와 복구 페이지 라이브 확인.
- **Blocker**: push는 GLG 결정. push 전 로컬 품질 블로커는 없음.
- **Read**: `tests/test_build.py`,
  `.claude/skills/garden-to-wikidocs/scripts/audit.py`, 이 파일의 검증 기준.
- **Do not touch**: `~/repos/gh/notes/content` 원본, 민감어 하드코딩, 기존 tag 이동.

## RECENT — 2026-07-17

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
