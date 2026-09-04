# Agent Instructions — garden2wikidocs

## 이 리포가 하는 일

정한의 디지털가든(`~/repos/gh/notes`, Quartz/Hugo Markdown)을 위키독스 깃허브 연동 책
(book_id 20676)으로 내보내는 **read-only translation harness**다. `git push` → 웹훅 →
위키독스 동기화. 가든 원본은 절대 수정하지 않는다 — 이 리포가 만드는 것은 미러
생성물(`pages/`, `TOC.md`, `README.md`, `mapping.json`)뿐이다.

## SSOT 포인터 — 먼저 읽어라

- **메커니즘·불변식(실측으로 확정된 것들)**: `.claude/skills/garden-to-wikidocs/SKILL.md`.
  500페이지 상한, page_id 부활 안 됨, TOC=발행 목록(뺀 페이지는 라이브에서 삭제됨) 등
  전부 사고로 확정된 규칙이다. 재발견하지 말고 읽는다.
- **정본/미러 정책**(garden이 canonical, WikiDocs는 discovery mirror): garden
  `docs/WIKIDOCS_MIRROR.md` (로컬: `~/repos/gh/notes/docs/WIKIDOCS_MIRROR.md`).
- **현재 좌표·직전 판 이력**: `NEXT.md`.

## 안전 규칙

- **audit 이전 push 금지.** push 한 번이 최대 20분짜리 전체 WikiDocs 웹훅을 촉발한다.
  `build → relink → audit → unittest` 게이트를 전부 통과한 뒤에만 commit한다.
- **build 직후 반드시 relink를 다시 돌린다.** build는 `pages/`를 통째로 다시 쓰므로
  relink 결과가 지워진다. audit은 relink 뒤에 돌려야 발행면 밖 참조까지 검사한다.
- **신규 page_id가 있는 갱신은 2단계 push다.** build가 `발행면 page_id 미회수 N개`를
  찍으면: 1차 push(`--allow-missing-page-ids`) → `status.py`로 웹훅 반영 확인 →
  `recover.py` → build/relink/audit 재실행 → 2차 push. 새 노트뿐 아니라 기존 노트에
  `autholog` 태그를 붙이는 것만으로도 이 경로를 탄다.
- **commit은 이 스킬의 gate(빌드·relink·audit·unittest) 통과 후에만.** push는 GLG가
  현재 세션에서 명시적으로 요청할 때만 실행한다 — 콘텐츠 변경이 아닌 커밋(문서·스킬만
  고친 경우)도 push하면 전체 재동기화가 돌므로 타이밍은 GLG가 정한다.
- **가든 worktree가 dirty/untracked면 build가 실패한다.** garden 쪽 canonical commit이
  끝난 뒤에만 미러를 생성한다.

## 정상 실행 순서

```bash
python3 .claude/skills/garden-to-wikidocs/scripts/build.py \
  --folders journal,meta,bib,notes,botlog --core
python3 .claude/skills/garden-to-wikidocs/scripts/relink.py
python3 .claude/skills/garden-to-wikidocs/scripts/audit.py --core
python3 -m unittest discover -s tests -q
# GLG 승인 후에만: git commit, 별도 push 승인 시에만 git push
WIKIDOCS_TOKEN="$(pass personal/token/wikidocs/junghanacs)" \
  python3 .claude/skills/garden-to-wikidocs/scripts/status.py --book-id 20676 --list
```

의존성 0(Python stdlib만). 토큰은 `pass personal/token/wikidocs/junghanacs`.

## Documentation & Commit Language

대화는 한국어. 커밋 메시지는 Conventional Commits 스타일 영문 요약(`feat(mirror): ...`)을
쓴다 — 기존 커밋 로그 관례를 따른다. AI attribution/Co-Authored-By 트레일러는 넣지 않는다
(사용자 전역 지침).
