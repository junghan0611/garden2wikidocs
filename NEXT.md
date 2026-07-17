# NEXT — garden2wikidocs

다음 세션 핸드오프. 개요·불변식·변환 메커니즘 SSOT 는
`.claude/skills/garden-to-wikidocs/SKILL.md`. 릴리즈 이력은 `CHANGELOG.md`.

## NOW — 어디까지 왔나

`v2026.7.17` 로 가든 5폴더 전체 미러 완성(2238p + 대문). 이후 push:
- **챕터 순서** 숫자 접두어 `1 저널·2 메타·3 참고문헌·4 노트·5 봇로그` (위키독스 알파벳
  강제정렬을 숫자로 제어). in-place 리네임 확인(노드 2243 유지, 중복 없음).
- **README = 책 대문**: `## 이 책에 대하여` 메타데이터 섹션(가든 홈·가든 소스·미러 리포
  깃허브 + 마지막 동기화 날짜), 'AI visitors' 블록쿼트+섹션 제거. 본문은 book `summary`
  로 동기화(전체 웹훅 sync ~19분 완료 후 갱신).

## NEXT — 다음 세션 주제: 페이지 내보내기 로직 결함

### 1) RELREF 줄바꿈 붕괴 버그 (우선순위 최상, 정밀 진단됨)
증상: 일부 페이지가 무너짐 — 문단이 줄바꿈을 잃고 한 줄로 뭉개지고 테이블·헤딩이
소실. 예: `pages/botlog/20260407T093255.md` (원본 203줄 → 45줄).

근본 원인: `build.py` 의
```
RELREF = re.compile(r'\[((?:[^\]]|\](?!\())*)\]\(\{\{<\s*relref\s+"([^"]+)"\s*>\}\}\)')
```
링크텍스트 그룹 `[^\]]` 가 **줄바꿈을 넘어 매칭**한다. 비-링크 대괄호(예: 히스토리의
`[프로젝트 관리 멤버 할일 서포트]`)가 열고 한참 뒤 relref `](...)` 가 닫히면, 그 사이
전 영역(테이블·헤딩·문단)이 하나의 relref 링크텍스트로 삼켜지고 `clean_title` 의
`\s+ -> ' '` 가 줄바꿈을 공백으로 뭉갠다. RELREF 단계에서 180줄→35줄 붕괴 실측.

수정 방향: 링크텍스트를 줄바꿈 불포함으로 제한(`[^\]\n]` + 대체군에 `\n` 배제).
같은 부류(줄바꿈 넘김) 위험을 ATAG·FIGURE 등 다른 정규식에서도 점검.
블래스트 반경: relref 앞에 비-링크 `[대괄호]` 가 있는 모든 페이지(botlog·notes 다수 추정)
→ 수정 후 전체 재-build → recover → relink → push 필요.

### 2) 위키독스 확장문법 정합성 (참고: https://wikidocs.net/141888)
- **테이블**: 파이프/하이픈 표준. 위 버그로 인라인 뭉개짐이 근본이지만, 정상 케이스도
  위키독스 렌더 확인. 셀 내 `|` 는 `&#124;`.
- **각주**: `[^name]` 본문 + `[^name]: 설명` 하단. 가든 citeproc/각주를 이 문법으로 매핑
  검토(현재 citeproc 는 텍스트/링크로만 변환).
- **[TOC]**: 이미 `## ` 3개 이상 페이지에 자동 삽입 중 — 위키독스 `[TOC]` 와 일치 확인.

### 3) 갱신 사이클 (상시)
가든 변경 시: `build.py --folders journal,meta,notes,bib,botlog` → push →
`recover.py --book-id 20676` → `relink.py` → push. build 는 `pages/`·`mapping.json`·
`README.md` 를 통째로 재생성하므로 반드시 recover→relink 재실행.

## 선택지 (급하지 않음)
- 릴리즈 follow-up 태그 `v2026.7.17-fix.1` (챕터 재정렬 + README 메타데이터 반영분).
- README `## AI visitors` 는 제거 완료. mapping `_chapters` subject 는 재정렬 후 recover
  재실행하면 `1 저널` 등으로 최신화(현재 라벨만 stale, page_id/url 은 정확).

## 검증 기준
- 씨뿌리기 후: 차단어 0, 코드펜스 밖 미처리 숏코드 0, **페이지 줄수가 원본과 크게
  안 줄었는지**(RELREF 붕괴 탐지).
- 회수 후: `mapping.json` page_id N/N + `_chapters`.
- relink 후: 내부/폴더 링크 클릭 이동(콘텐츠 폴링 확인).

## 블록/주의
- **push 는 GLG만.** 커밋까지 에이전트.
- **가든 read-only.** `~/repos/gh/notes/content` 수정 금지.
- **민감어 하드코딩 금지.** 난독화는 가든 `change-text.sh` 런타임 로드.
- 대량 push: 2238p·assets 267M, 웹훅 동기화 ~19분(2243 노드).

## 알려진 데이터 결함 (가든 원본, read-only)
- 깨진 코드펜스로 거대 코드블록화(예: journal 20250630, 20260406).
- bib 20250327: relref 가 링크텍스트 위치에 들어간 원본 오류 1건.

## 보안 메모 (GLG 결정 대기)
가든 `change-text.sh` 가 어떤 회사 핸들의 특정 번호 변형만 난독화하는데 훅은 전 변형을
막는다. export 는 전 변형을 일반화 처리. 가든 change-text.sh 도 베이스 형태로 고치면
공개 가든 잔여 노출이 사라진다 — 여기서는 가든 미수정.
