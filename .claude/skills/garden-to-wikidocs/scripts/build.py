#!/usr/bin/env python3
"""garden -> wikidocs github-book 변환기 v2 (stdlib only).

폴더 미러 방식. 가든의 각 폴더(journal/meta/notes/bib/botlog)를 위키독스 책의
'챕터'로 만든다. 가든 원본은 절대 수정하지 않는다(read-only).

산출물(이 리포 안):
    TOC.md                       폴더=챕터 계층
    pages/<folder>/_chapter.md   챕터 표지(AEO recent-first 제목/메타/요약/링크)
    pages/autholog/_chapter.md   autholog 태그 집합(AEO lastmod recent-first index)
    pages/<folder>/<denote-id>.md  각 노트 (H1 없음, gid 앵커 포함)
    assets/                      복사된 로컬 이미지
    mapping.json                 denote-id -> page/source metadata ledger
    BUILD-MANIFEST.json          canonical garden commit + deterministic input hash

3단계 파이프라인 + 품질 게이트:
    1) seed   : build.py --folders journal  → 생성, 내부 relref는 가든 절대URL.
                기존 mapping의 page_id는 동일 gid에 승계. 각 페이지에 <!-- gid:ID --> 앵커.
    2) recover: (별도) 최초 push/새 페이지 동기화 후 gid<->page_id 회수
    3) relink : (별도) 내부 relref 를 wikidocs.net/<page_id> 로 재작성
    gate) audit: (별도) push 전 TOC·mapping·본문 구조 품질 검증

사용:
    build.py --folders journal,meta,bib,notes,botlog
             [--garden ~/repos/gh/notes] [--out <repo root>]
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

GARDEN_URL = "https://notes.junghanacs.com"
WIKIDOCS_URL = "https://wikidocs.net"
SOURCE_REPOSITORY = "https://github.com/junghan0611/garden"
BOOK_ID = 20676
MANIFEST_NAME = "BUILD-MANIFEST.json"


def load_scrub_rules(garden_root: Path):
    """회사/직장 신원 난독화 규칙을 가든의 change-text.sh 에서 런타임에 읽는다.

    이 스크립트에 민감어를 하드코딩하지 않기 위함(그 자체가 pre-commit 훅에 걸린다).
    change-text.sh 의 `s/PAT/REP/flags` 규칙을 파싱하고, 번호 접미(예: 6)가 붙은
    규칙은 전 변형(숫자 0개 이상)까지 커버하도록 일반화한다."""
    script = garden_root / "change-text.sh"
    rules = []
    if not script.exists():
        return rules
    text = script.read_text(encoding="utf-8")
    for m in re.finditer(r"s([/|])(.+?)\1(.+?)\1([giI]*)", text):
        pat, rep, flags = m.group(2), m.group(3), m.group(4)
        fl = re.I if "I" in flags or "i" in flags else 0
        rules.append((re.compile(re.escape(pat), fl), rep.replace("\\", "\\\\")))
        base = re.sub(r"\d+$", "", pat)
        rbase = re.sub(r"\d+$", "", rep)
        if base and base != pat:
            rules.append((re.compile(re.escape(base) + r"([0-9]*)", fl),
                          rbase.replace("\\", "\\\\") + r"\1"))
    return rules


def scrub_identity(text: str, rules) -> str:
    for pat, rep in rules:
        text = pat.sub(rep, text)
    return text

# 폴더 -> 챕터 표시 이름. 위키독스는 표지 제목을 알파벳순 강제정렬하므로 숫자 접두어로
# 원하는 순서를 만든다(저널·메타·참고문헌·노트·봇로그). TOC.md 자체도 같은 순서로
# 생성해야 가져오기 도중 한 챕터가 실패했을 때 순서 진단이 어긋나지 않는다.
CHAPTER_NAMES = {
    "journal": "1 저널", "meta": "2 메타", "bib": "3 참고문헌",
    "notes": "4 노트", "botlog": "5 봇로그", "talks": "토크",
}
CHAPTER_ORDER = {folder: i for i, folder in enumerate(CHAPTER_NAMES)}

# WikiDocs에 없는 가든 태그 탐색면 가운데 보존할 가치가 큰 집합 페이지. 원본 노트를
# 복제하지 않고 이미 미러된 페이지를 lastmod 최신순으로 모으는 가상 챕터다.
COLLECTIONS = {
    "autholog": {
        "subject": "0 어쏠로그",
        "path": "pages/autholog/_chapter.md",
        "source_url": f"{GARDEN_URL}/tags/autholog/",
    },
}

# 위키독스 책은 TOC.md 에 등록된 페이지를 최대 500개까지만 받는다(2026-07 실측). 초과하면
# 웹훅 동기화 자체가 거부되고, 반대로 TOC 에서 빠진 페이지는 라이브에서 삭제된다(404).
# 그래서 TOC 는 목차가 아니라 발행 목록이고, mapping 에 page_id 가 남아 있어도 TOC 밖
# 페이지의 위키독스 URL 은 죽은 링크다. `--core` 는 상한 아래로 내리는 발행면이며
# pages/ 와 mapping 은 가든 전량을 그대로 보존한다.
PUBLISH_LIMIT = 500
CORE_TAG = "autholog"
CORE_FOLDERS = ("botlog",)


def is_core_member(folder: str, tags, core: bool) -> bool:
    """발행 코어 판정. 예산 사전검사와 TOC 생성이 같은 규칙을 쓰도록 한 곳에 둔다."""
    return not core or CORE_TAG in tags or folder in CORE_FOLDERS


# 직전 판 TOC 의 링크 대상. 이번 build 가 덮어쓰기 전에 읽어 "발행면에 새로 들어오는
# 페이지"를 가른다. 삭제된 페이지의 page_id 는 되살아나지 않는다 — 2026-07-27 실측:
# 상한 컷 때 지워졌던 두 노트가 발행면에 다시 들어오자 위키독스는 옛 381403/381716 이
# 아니라 새 387071/387072 를 발급했다.
TOC_TARGET = re.compile(r"^\s*- \[[^\]]*\]\((pages/[^)]+)\)\s*$", re.M)


def previous_publish_surface(toc_path: Path):
    """직전 판 발행 경로 집합. 파일이 아예 없으면 None.

    "없음"과 "있는데 링크 0개"를 뭉개지 않는다. 후자는 bootstrap 이 아니라 손상이고,
    둘을 같은 값으로 접으면 판정 불가 상태에서 조용히 승계가 열린다. 어느 쪽을
    허용할지는 mapping 의 회수 이력을 함께 보는 호출부가 정한다.
    """
    if not toc_path.exists():
        return None
    return set(TOC_TARGET.findall(toc_path.read_text(encoding="utf-8")))


def has_recovered_ids(previous_mapping: dict) -> bool:
    """직전 mapping 에 회수된 remote id 가 하나라도 있는가 = 발행 이력이 있는가."""
    return any(entry.get("page_id")
               for key, entry in previous_mapping.items() if key != "_chapters") or \
        any(entry.get("page_id")
            for entry in previous_mapping.get("_chapters", {}).values())


def inherit_remote_id(entry: dict, previous: dict, page_rel: str, live_paths,
                      publishing: bool = True) -> bool:
    """page_id 를 승계하되 발행면 신규 진입이면 보류한다. 보류했으면 True.

    발행면에 새로 들어오는 페이지는 라이브에 없으니 mapping 의 page_id 가 죽은 값이다.
    그대로 승계하면 relink 가 404 URL 을 심는데 어떤 게이트도 울리지 않는다 — page_id 가
    있고 TOC 안이라 link_target 도 relink 도 audit 도 통과한다. 여기서 비워야 relink 가
    가든 원본으로 내보내고, push 후 recover 가 새로 발급된 id 를 채운다.

    발행면 밖에 머무는 페이지의 page_id 도 컷 이후로는 죽은 값이지만 그대로 둔다. TOC
    게이트가 그 URL 을 어디에도 내보내지 않아 노출 경로가 없고, 언젠가 발행면에 들어올
    때 이 규칙이 그 자리에서 잡는다. 죽었다고 지금 전량을 비우면 2천여 항목이 흔들려
    실제 위험 구간이 diff 에 묻힌다.
    """
    if publishing and live_paths is not None and page_rel not in live_paths:
        return bool(previous.get("page_id"))
    for key in ("page_id", "url"):
        if previous.get(key):
            entry[key] = previous[key]
    return False

# ---------------------------------------------------------------- 제목/식별자

SIGILS = "#@§¤†‡©※¶‣∷"
# 개인 노트 제목에서 의미를 보태는 입력용 기호지만 위키독스 TOC 링크텍스트에는 넣지
# 않는다. 일부 기호와 중첩 대괄호는 위키독스의 TOC 파서를 중단시킬 수 있다.
TOC_UNSAFE_CHARS = "\u00a0—§¶†‡№↔←→⊢⊨∉©¬¤µ¡¿◊⁂¥¢£[]"
TOC_TRANSLATION = str.maketrans({ch: " " for ch in TOC_UNSAFE_CHARS})
DENOTE_ID = re.compile(r"(\d{8}T\d{6})")


def strip_wrapping_quotes(raw: str) -> str:
    """양 끝이 같은 따옴표일 때만 바깥 한 쌍을 제거한다.

    `str.strip("'")`는 제목 본문이 끝 따옴표로 끝나는 경우 그 문자만 지워
    `'모델/도구'`를 `'모델/도구`로 훼손하므로 사용하지 않는다.
    """
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1].strip()
    return text


def clean_title(raw: str) -> str:
    t = strip_wrapping_quotes(raw)
    for ch in SIGILS:
        t = t.replace(ch, "")
    t = re.sub(r"\s+", " ", t).strip()
    t = t.lstrip(":·•*-— ").strip()
    return t


def clean_toc_title(raw: str) -> str:
    """위키독스 TOC/페이지 제목용 평문 정리.

    가든 원본의 입력용 유니코드와 Markdown 중첩 대괄호를 공백으로 바꾼 뒤 기존 제목
    sigil 정리를 적용한다. 삭제 지점의 단어가 붙지 않도록 공백으로 바꾸는 것이 중요하다.
    """
    return clean_title((raw or "").translate(TOC_TRANSLATION))


def denote_id(s: str):
    m = DENOTE_ID.search(s)
    return m.group(1) if m else None


def ordered_folders(folders):
    """중복을 제거하고 알려진 챕터를 고정 순서로 정렬한다."""
    unique = list(dict.fromkeys(folders))
    input_order = {folder: i for i, folder in enumerate(unique)}
    return sorted(unique, key=lambda f: (CHAPTER_ORDER.get(f, len(CHAPTER_ORDER)),
                                         input_order[f]))


def git_output(garden_root: Path, *args) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(garden_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error)).strip()
        raise ValueError(f"garden git 조회 실패: {detail}") from error
    return result.stdout.strip()


def selected_source_paths(garden_root: Path, folders):
    """변환 결과를 결정하는 authored Markdown/scrub 입력을 상대경로순으로 고른다."""
    paths = [garden_root / "content" / "index.md", garden_root / "change-text.sh"]
    for folder in folders:
        paths.extend((garden_root / "content" / folder).glob("*.md"))
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"garden build input 없음: {[str(path) for path in missing]}")
    return sorted(set(paths), key=lambda path: path.relative_to(garden_root).as_posix())


def source_content_sha256(garden_root: Path, folders) -> str:
    """상대경로와 bytes를 length-framed 순서로 해시한다."""
    digest = hashlib.sha256()
    for path in selected_source_paths(garden_root, folders):
        relative = path.relative_to(garden_root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def make_build_manifest(garden_root: Path, folders, pages: int):
    """clean canonical garden commit을 pin한 deterministic build provenance."""
    folders = ordered_folders(folders)
    source_commit = git_output(garden_root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError(f"garden source commit 형식 오류: {source_commit!r}")
    dirty = git_output(
        garden_root,
        "status", "--porcelain=v1", "--untracked-files=all", "--",
        "content", "change-text.sh",
    )
    if dirty:
        preview = " | ".join(dirty.splitlines()[:5])
        raise ValueError(
            "garden content/change-text.sh가 dirty/untracked입니다. "
            f"canonical commit 후 build하세요: {preview}"
        )
    return {
        "schema_version": 1,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": source_commit,
        "source_content_clean": True,
        "source_content_sha256": source_content_sha256(garden_root, folders),
        "folders": folders,
        "pages": pages,
        "book_id": BOOK_ID,
    }


SOURCE_TIMESTAMP = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:T|$)")


def source_sort_timestamp(source: dict) -> str:
    """가든 목록과 같은 정렬/제목 날짜 원천을 고른다.

    journal은 created(`date`), 나머지는 modified(`lastmod`, 없을 때 `date`)다.
    """
    if source.get("folder") == "journal":
        value = source.get("date")
    else:
        value = source.get("lastmod") or source.get("date")
    if not SOURCE_TIMESTAMP.match(value or ""):
        raise ValueError(f"garden source date/lastmod 형식 오류: {value!r}")
    return value


def source_title_date(source: dict) -> str:
    """folder별 source sort timestamp를 8자리 제목 날짜로 바꾼다."""
    match = SOURCE_TIMESTAMP.match(source_sort_timestamp(source))
    return "".join(match.groups())


def source_sort_key(source: dict):
    """newest-first 정렬 키. 같은 timestamp는 Denote ID newest-first로 고정한다."""
    return source_sort_timestamp(source), source["id"]


def subject_for(source_timestamp: str, title: str) -> str:
    """source lastmod(없으면 date) 8자리 접두어로 WikiDocs 제목을 정렬한다.

    제목이 선택된 source 날짜(ISO 또는 8자리)로 이미 시작할 때만 중복을 피한다.
    build/git/mtime/WikiDocs sync 시각은 이 함수에 들어올 수 없다.
    """
    match = SOURCE_TIMESTAMP.match(source_timestamp or "")
    if match:
        d8 = "".join(match.groups())
    elif re.fullmatch(r"\d{8}(?:T\d{6})?", source_timestamp or ""):
        d8 = source_timestamp[:8]
    else:
        raise ValueError(f"source timestamp 형식 오류: {source_timestamp!r}")
    iso = f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}"
    ct = clean_toc_title(title)
    if ct.startswith(iso) or ct.startswith(d8):
        return ct
    return f"{d8} {ct}"


# ---------------------------------------------------------------- frontmatter

def split_frontmatter(text: str):
    """현재 garden의 한 줄 YAML scalar frontmatter를 명시적으로 읽는다.

    전체 YAML 구현이 아니라 garden export 형식에 맞춘 parser다. 첫 `:` 뒤의 값을
    그대로 보존하고, 양끝이 같은 ASCII quote 한 쌍만 벗긴다. 따라서 quoted
    title/description의 내부 따옴표와 ISO timestamp(+09:00)는 훼손하지 않는다.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    meta = {}
    for line in fm.split("\n"):
        m = re.match(r'^([A-Za-z0-9_]+):\s*(.*)$', line)
        if m:
            meta[m.group(1)] = strip_wrapping_quotes(m.group(2))
    return meta, body


def parse_tags(raw: str) -> list:
    """garden export의 한 줄 JSON/YAML 호환 태그 배열을 읽는다."""
    if not raw:
        return []
    try:
        tags = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"garden frontmatter tags 형식 오류: {raw!r}") from error
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError(f"garden frontmatter tags 배열 아님: {raw!r}")
    return tags


def read_source(src: Path, folder: str):
    """garden 원본의 authored metadata와 body를 하나의 record로 읽는다."""
    did = denote_id(src.name)
    if not did:
        raise ValueError(f"Denote ID 없는 source filename: {src}")
    meta, body = split_frontmatter(src.read_text(encoding="utf-8"))
    missing = [field for field in ("title", "date") if not meta.get(field)]
    if missing:
        raise ValueError(f"garden frontmatter 필수값 없음 {missing}: {src}")
    return {
        "id": did,
        "folder": folder,
        "title": meta["title"],
        "description": meta.get("description", ""),
        "date": meta["date"],
        "lastmod": meta.get("lastmod", ""),
        "tags": parse_tags(meta.get("tags", "")),
        "source_url": f"{GARDEN_URL}/{folder}/{did}/",
        "body": body,
    }


# ---------------------------------------------------------------- 본문 변환

# 펜스는 줄 시작(들여쓰기 허용)에서만 열고 닫힌다. 여는 backtick 개수(3+)를 기억해
# 같은 개수 이상으로 닫는 줄까지 매칭 → 4-backtick 블록/혼재 펜스에서 산문 오보호 방지.
CODE_FENCE = re.compile(r"^[ \t]*(`{3,})[^\n]*\n.*?^[ \t]*\1`*[ \t]*$",
                        re.DOTALL | re.MULTILINE)
HEAD_ANCHOR = re.compile(r"[ \t]*\{#[^}]*\}[ \t]*$", re.M)
TIMESTAMP = re.compile(
    r'<span class="timestamp-wrapper">\s*<span class="timestamp">\s*'
    r'(\[[^\]]*\])\s*</span>\s*</span>'
)
CALLOUT = re.compile(r"^>\s*\[!([A-Za-z]+)\]\s*(.*)$")
# citeproc 참고문헌 한 항목은 한 줄짜리 목록으로 변환한다. 코드펜스는 이 단계 전에 보호됨.
CSL_ENTRY = re.compile(
    r'^[ \t]*<div class="csl-entry"[^>]*>(.*?)</div>[ \t]*$', re.MULTILINE)
CSL_ID = re.compile(r'<a id="citeproc_bib_item_\d+"></a>')
DIVTAG = re.compile(r"</?div[^>]*>")
ATAG = re.compile(r'<a\s+[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
# 링크 텍스트에 `]` 가 있어도(중첩 대괄호) 실제 링크 종료 `](` 에서만 끊기게 tempered.
# 인라인 링크는 절대 줄바꿈을 넘지 않는다. 이 제한이 없으면 앞선 일반 `[대괄호]`부터
# 뒤의 relref까지 문단·헤딩·표 전체를 삼킨 뒤 clean_title이 줄바꿈을 삭제한다.
RELREF = re.compile(
    r'\[((?:[^\]\n]|\](?!\())*)\]\(\{\{<\s*relref\s+"([^"]+)"\s*>\}\}\)')
RELREF_SHORTCODE_TEXT = re.compile(r'\{\{<\s*relref\s+"([^"]+)"\s*>\}\}')
# caption 에 <span> 등 `>` 가 들어와도 실제 종료 `>}}` 까지 잡게 .*? 사용.
FIGURE = re.compile(r'\{\{<\s*figure\s+(.*?)>\}\}')
IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# 대문(README) 전용: 가든 크롤러용 'AI visitors' 안내(블록쿼트 + H2 섹션)를 제거하고
# 위키독스 책 메타데이터 섹션으로 대체한다. (llms.txt·sitemap·robots·RSS 는 책 안에선
# 무의미.) 이 책 본문은 위키독스 책 대문(book summary)으로 동기화된다.
AI_VISITORS_BQ = re.compile(r"^>\s*AI visitors: start here\..*$\n?", re.MULTILINE)
AI_VISITORS_SEC = re.compile(r"^## AI visitors\b.*?(?=^## |\Z)", re.DOTALL | re.MULTILINE)
GARDEN_HOME = "https://notes.junghanacs.com"
GARDEN_REPO = "https://github.com/junghan0611/garden"
MIRROR_REPO = "https://github.com/junghan0611/garden2wikidocs"
# 코어가 왜 가든 전량이 아닌지를 저자가 직접 쓴 글. 대문에서 여기로 보낸다.
CORE_NOTE_URL = f"{GARDEN_URL}/notes/20230706T160800"


def readme_meta_block(published: int = 0, total: int = 0, core: bool = False,
                      folders=()) -> str:
    """책 대문 상단 메타데이터 섹션(헤딩 레벨). 마지막 동기화 = 빌드 날짜.

    코어 판본일 때 '미러링한 책'이라고 쓰면 거짓이다. 가든 전량이 아니라 골라 낸
    현재 판본임을 숫자와 함께 밝히고, 왜 전체가 아닌지를 설명한 노트로 보낸다.
    """
    if not core:
        return (
            "## 이 책에 대하여\n\n"
            "정한(Junghan Kim)의 디지털 가든을 위키독스로 미러링한 책입니다. "
            "원본과 최신본은 가든에서 보실 수 있습니다.\n\n"
            f"- 원본 가든: <{GARDEN_HOME}>\n"
            f"- 가든 소스: <{GARDEN_REPO}>\n"
            f"- 미러 리포: <{MIRROR_REPO}>\n"
            f"- 마지막 동기화: {date.today().isoformat()}\n"
        )
    scope = "·".join(CHAPTER_NAMES[folder][2:] for folder in folders
                     if folder in CHAPTER_NAMES) if folders else ""
    return (
        "## 이 책에 대하여\n\n"
        "정한(Junghan Kim)의 **디지털가든 코어**입니다. 가든 전체를 미러링한 책이 "
        "아닙니다. 어쏠로그(생생날것)와 봇로그를 중심으로 "
        f"미러 대상 {len(folders)}개 폴더({scope}) {total:,}개 문서 가운데 "
        f"{published:,}개를 골라 낸 현재 판본입니다. 여기 없는 글도 지워진 것이 아니라 "
        "가든에 그대로 있고, 원본과 최신본은 언제나 가든입니다.\n\n"
        "코어는 가장 좋은 글의 목록이 아니라, 지금 불러낼 수 있는 이름과 말과 그 관계를 "
        "쌓아온 시간축의 현재 판본입니다. 왜 전체가 아니라 코어인지는 "
        f"[생생날것 500개 문턱 — 디지털가든 코어는 시간축의 판본이다]({CORE_NOTE_URL})에 "
        "적혀 있습니다.\n\n"
        f"- 원본 가든: <{GARDEN_HOME}>\n"
        f"- 가든 소스: <{GARDEN_REPO}>\n"
        f"- 코어 리포: <{MIRROR_REPO}>\n"
        f"- 이 판본: 미러 대상 {total:,}개 중 {published:,}개\n"
        f"- 마지막 동기화: {date.today().isoformat()}\n"
    )


def readme_head(readme_body: str, published: int = 0, total: int = 0,
                core: bool = False, folders=()) -> str:
    body = AI_VISITORS_BQ.sub("", readme_body, count=1)
    body = AI_VISITORS_SEC.sub("", body, count=1)
    return readme_meta_block(published, total, core, folders) + "\n" + body.lstrip("\n")


def figure_repl(m):
    """Hugo {{< figure src=... caption=... >}} -> ![alt](src). 이후 IMG 단계가 assets 복사.
    caption 에 HTML(<span> 등)이 섞이면 alt 를 비운다(위키독스 렌더 깔끔)."""
    attrs = m.group(1)
    src = re.search(r'src="([^"]*)"', attrs)
    if not src:
        return ""
    cap = re.search(r'(?:title|caption|alt)="([^"]*)"', attrs)
    alt = cap.group(1) if (cap and "<" not in cap.group(1)) else ""
    return f'![{alt}]({src.group(1)})'

CALLOUT_LABELS = {
    "abstract": "요약", "summary": "요약", "tldr": "요약",
    "note": "노트", "info": "정보", "tip": "팁", "hint": "팁",
    "question": "질문", "faq": "질문", "help": "질문",
    "warning": "주의", "caution": "주의", "attention": "주의",
    "danger": "주의", "error": "주의", "failure": "실패",
    "bug": "버그", "example": "예시", "quote": "인용", "cite": "인용",
    "done": "완료", "success": "완료", "check": "완료",
}

# 저자가 쓴 대표 abstract만 시스템 provenance와 분리해 페이지 맨 앞으로 옮긴다.
# 내부 섹션의 [!abstract] 예시는 건드리지 않고 정확한 제목 `이 노트에 대하여`만 잡는다.
AUTHOR_ABSTRACT = re.compile(
    r'^>\s*\[!abstract\]\s+이 노트에 대하여[ \t]*\n(?:^>[^\n]*(?:\n|\Z))*',
    re.MULTILINE,
)
PROVENANCE_START = "<!-- provenance:source:start -->"
PROVENANCE_END = "<!-- provenance:source:end -->"
CHAPTER_INDEX_START = "<!-- chapter-index:recent-first:start -->"
CHAPTER_INDEX_END = "<!-- chapter-index:recent-first:end -->"
COLLECTION_MARKER = "<!-- collection:{tag} -->"
COLLECTION_INDEX_START = "<!-- collection-index:recent-first:start -->"
COLLECTION_INDEX_END = "<!-- collection-index:recent-first:end -->"


def extract_author_abstract(body: str):
    """대표 abstract와 나머지 authored body를 분리한다."""
    match = AUTHOR_ABSTRACT.search(body)
    if not match:
        return "", body
    abstract = match.group(0).strip() + "\n"
    rest = (body[:match.start()] + body[match.end():]).strip()
    return abstract, (rest + "\n" if rest else "")


def provenance_block(source: dict) -> str:
    """가든 정본으로 돌아가는 페이지별 시스템 provenance 블록."""
    modified = source["lastmod"] or f'{source["date"]} (lastmod 없음: date fallback)'
    return (
        f"{PROVENANCE_START}\n"
        '[[TIP("원본·최신본")]]\n'
        "이 페이지는 한국어 검색과 읽기를 위한 WikiDocs 미러입니다. "
        f'[원본·최신본은 가든]({source["source_url"]})에 있습니다. '
        "최신 수정 내용·백링크·태그·히스토리·댓글·출처 정보는 원본 가든에서 확인하세요.\n\n"
        f'- 작성: `{source["date"]}`\n'
        f"- 최근 수정: `{modified}`\n"
        "[[/TIP]]\n"
        f"{PROVENANCE_END}"
    )


def compose_page(author_abstract: str, body: str, source: dict, include_toc: bool) -> str:
    """abstract → provenance → navigation/body publication ordering을 고정한다."""
    blocks = []
    if author_abstract:
        blocks.append(author_abstract.strip())
    blocks.append(provenance_block(source))
    if include_toc:
        blocks.append("[TOC]")
    if body.strip():
        blocks.append(body.strip())
    return "\n\n".join(blocks) + "\n"


def collection_sort_key(source: dict):
    """태그 집합은 폴더와 무관하게 lastmod(없으면 date), ID 최신순이다."""
    value = source.get("lastmod") or source.get("date")
    if not SOURCE_TIMESTAMP.match(value or ""):
        raise ValueError(f"garden collection lastmod/date 형식 오류: {value!r}")
    return value, source["id"]


def link_target(entry: dict, published=None) -> str:
    """발행된 페이지만 위키독스 URL로 잇고, 나머지는 가든 원본으로 보낸다.

    `published` 는 TOC 에 등록된 page 경로 집합이다. TOC 밖 페이지는 위키독스가
    삭제하므로 mapping 에 page_id 가 남아 있어도 그 URL 은 404 다. None 이면
    (전량 발행) 종전대로 page_id 우선이다.
    """
    if published is not None and entry["path"] not in published:
        return entry["source_url"]
    return entry.get("url") or entry["source_url"]


def public_index_metadata(source: dict, scrub_rules) -> dict:
    """표지와 mapping에 싣는 공개용 description/tags 캐시."""
    return {
        "description": scrub_identity(source.get("description", ""), scrub_rules),
        "tags": [scrub_identity(tag, scrub_rules) for tag in source.get("tags", [])],
    }


def public_index_title(source: dict, scrub_rules) -> str:
    """날짜 접두어 없는 AEO 표지 heading. 공개 난독화 경계를 함께 적용한다."""
    return scrub_identity(clean_toc_title(source["title"]), scrub_rules)


def plain_summary(text: str) -> str:
    """frontmatter의 한 줄 plain text를 Markdown에서 같은 글자로 보이게 한다.

    중간의 `#태그`와 authored `*강조*`/`_강조_`는 그대로 둔다. 기존 HTML entity의
    `&`도 이중 인코딩하지 않는다. 실제 텍스트 소실을 만드는 angle bracket과 미래의
    줄 시작 block 문법만 막는다.
    """
    text = (text or "").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"(?m)^(\s*)(#{1,6})(?=\s)", r"\1\\\2", text)
    text = re.sub(r"(?m)^(\s*)([-+*>])(?=\s)", r"\1\\\2", text)
    text = re.sub(r"(?m)^(\s*)(\d+\.)(?=\s)", r"\1\\\2", text)
    return text


def source_day(value: str) -> str:
    """ISO source timestamp를 표지 메타의 YYYY-MM-DD로 줄인다."""
    match = SOURCE_TIMESTAMP.match(value or "")
    if not match:
        raise ValueError(f"source timestamp 형식 오류: {value!r}")
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def index_headings(entries: list) -> list:
    """깨끗한 제목을 쓰되 같은 표지 안의 중복 제목만 작성일로 구분한다."""
    title_counts = {}
    for title, _ in entries:
        title_counts[title] = title_counts.get(title, 0) + 1
    dated_counts = {}
    for title, entry in entries:
        if title_counts[title] > 1:
            dated = (title, source_day(entry["source_date"]))
            dated_counts[dated] = dated_counts.get(dated, 0) + 1

    headings = []
    for title, entry in entries:
        heading = title
        if title_counts[title] > 1:
            day = source_day(entry["source_date"])
            heading = f"{title} — {day}"
            if dated_counts[(title, day)] > 1:
                heading += f" — {Path(entry['path']).stem}"
        headings.append(plain_summary(heading))
    return headings


def index_item_blocks(entries: list, published=None) -> list:
    """제목/메타/description/읽기 링크를 AEO용 section들로 렌더한다."""
    blocks = []
    for heading, (_, entry) in zip(index_headings(entries), entries):
        metadata = [f"작성 {source_day(entry['source_date'])}"]
        if entry.get("source_lastmod"):
            metadata.append(f"수정 {source_day(entry['source_lastmod'])}")
        if entry.get("tags"):
            metadata.append("태그 " + ", ".join(plain_summary(tag) for tag in entry["tags"]))
        target = link_target(entry, published)
        destination = "위키독스" if target.startswith(f"{WIKIDOCS_URL}/") else "가든 원본"
        parts = [f"## {heading}", " · ".join(metadata)]
        if entry.get("description"):
            parts.append(plain_summary(entry["description"]))
        parts.append(f"[{destination}에서 읽기 →]({target})")
        blocks.append("\n\n".join(parts))
    return blocks


def collection_index(tag: str, entries: list, published=None) -> str:
    """원본을 복제하지 않고 기존 미러 페이지를 잇는 AEO 태그 집합 탐색면."""
    spec = COLLECTIONS[tag]
    provenance = "\n".join([
        COLLECTION_MARKER.format(tag=tag),
        PROVENANCE_START,
        '[[TIP("원본·최신본")]]',
        "이 페이지는 가든 태그 탐색면을 WikiDocs 안에서 순회하기 위한 집합 페이지입니다. "
        f'[원본·최신본은 가든]({spec["source_url"]})에 있습니다.',
        "[[/TIP]]",
        PROVENANCE_END,
    ])
    intro = (
        f"가든 `{tag}` 태그 문서 {len(entries)}개를 최근 수정일(lastmod) 역순으로 모았습니다. "
        "각 항목은 제목, 작성·수정일, 태그, 요약과 읽기 링크를 담습니다."
    )
    blocks = [provenance, intro, COLLECTION_INDEX_START]
    blocks.extend(index_item_blocks(entries, published))
    blocks.append(COLLECTION_INDEX_END)
    return "\n\n".join(blocks) + "\n"


def chapter_index(folder: str, entries: list, published=None) -> str:
    """WikiDocs sidebar 오름차순과 분리된 AEO recent-first chapter index."""
    basis = "작성일(source_date)" if folder == "journal" \
        else "최근 수정일(source_lastmod, 없으면 source_date)"
    intro = (
        f"가든과 같은 {basis} 기준으로 {len(entries)}개 문서를 최신순으로 모았습니다. "
        "각 항목은 제목, 작성·수정일, 태그, 요약과 읽기 링크를 담습니다."
    )
    blocks = [CHAPTER_INDEX_START, intro]
    blocks.extend(index_item_blocks(entries, published))
    blocks.append(CHAPTER_INDEX_END)
    return "\n\n".join(blocks) + "\n"


def protect_code(text):
    blocks = []

    def repl(m):
        blocks.append(m.group(0))
        return f"\x00CODE{len(blocks)-1}\x00"

    return CODE_FENCE.sub(repl, text), blocks


def restore_code(text, blocks):
    for i, b in enumerate(blocks):
        text = text.replace(f"\x00CODE{i}\x00", b)
    return text


def convert_callouts(text: str) -> str:
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m = CALLOUT.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        ctype = m.group(1).lower()
        ctitle = m.group(2).strip()
        i += 1
        body = []
        while i < len(lines) and lines[i].startswith(">"):
            body.append(re.sub(r"^>\s?", "", lines[i]))
            i += 1
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        label = clean_title(ctitle) if (ctitle and ctitle.lower() != ctype) \
            else CALLOUT_LABELS.get(ctype, ctype)
        out.append(f'[[TIP("{label}")]]')
        out.extend(body)
        out.append("[[/TIP]]")
    return "\n".join(out)


def convert_html(text: str) -> str:
    text = CSL_ENTRY.sub(lambda m: f"- {m.group(1).strip()}", text)
    text = CSL_ID.sub("", text)
    text = DIVTAG.sub("", text)

    def a_repl(m):
        href, inner = m.group(1), m.group(2).strip()
        if href.startswith("#"):
            return inner
        return f"[{inner}]({href})"

    return ATAG.sub(a_repl, text)


def relref_repl(m):
    """씨뿌리기 단계: 모든 정상 내부 relref 를 가든 절대 URL 로.

    원본 오류로 링크텍스트 자체가 relref 숏코드인 경우에는 대상 문자열을 평문화한다.
    `/folder/id.md`가 아닌 상대 대상은 가든 URL로 확정할 수 없으므로 깨진 링크 대신
    평문만 남긴다.
    """
    raw_text = RELREF_SHORTCODE_TEXT.sub(r"\1", m.group(1))
    txt = clean_title(raw_text)
    target = m.group(2)
    if not target.startswith("/"):
        return txt or clean_title(target)
    path = target[:-3] if target.endswith(".md") else target
    return f"[{txt}]({GARDEN_URL}{path}/)"


def make_images(garden_root: Path, assets_dir: Path, rel_prefix: str, copied: list):
    def repl(m):
        alt, src = m.group(1), m.group(2)
        if src.startswith("/images/"):
            fn = src[len("/images/"):]
            src_file = garden_root / "static" / "images" / fn
            if src_file.exists():
                assets_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, assets_dir / fn)
                copied.append(fn)
                return f"![{alt}]({rel_prefix}assets/{fn.replace(' ', '%20')})"
        return m.group(0)
    return repl


def transform_body(body, garden_root, assets_dir, rel_prefix, copied):
    body, blocks = protect_code(body)
    body = HEAD_ANCHOR.sub("", body)
    body = TIMESTAMP.sub(r"\1", body)
    body = convert_callouts(body)
    body = convert_html(body)
    before_relref_lines = body.count("\n")
    body = RELREF.sub(relref_repl, body)
    if body.count("\n") != before_relref_lines:
        raise ValueError("RELREF 변환이 줄바꿈 수를 변경했습니다")
    body = FIGURE.sub(figure_repl, body)
    body = IMG.sub(make_images(garden_root, assets_dir, rel_prefix, copied), body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    body = restore_code(body, blocks)
    return body


# ---------------------------------------------------------------- 빌드(씨뿌리기)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folders", required=True,
                    help="가든 폴더들, 쉼표구분 (예: journal,meta,bib,notes,botlog)")
    ap.add_argument("--garden", default="~/repos/gh/notes")
    ap.add_argument("--out", default=None,
                    help="책 리포 루트(기본: 이 스크립트로부터 위로 README.md 있는 곳)")
    ap.add_argument("--toc-threshold", type=int, default=3)
    ap.add_argument("--core", action="store_true",
                    help=f"TOC 등록을 발행 코어(`{CORE_TAG}` 태그 ∪ "
                         f"{','.join(CORE_FOLDERS)} 폴더)로 제한한다. 위키독스 "
                         f"{PUBLISH_LIMIT}개 상한 대응. pages/·mapping 은 전량 유지.")
    ap.add_argument("--garden-links", action="store_true",
                    help="표지·집합면의 모든 링크를 가든 원본 URL로 낸다. 위키독스 URL은 "
                         "발행된 페이지에만 살아 있으므로, 발행면이 바뀌는 동안에는 "
                         "가든 한 곳으로 보내는 편이 끊기지 않는다.")
    args = ap.parse_args()

    garden_root = Path(args.garden).expanduser()
    if args.out:
        out = Path(args.out).expanduser()
    else:
        here = Path(__file__).resolve()
        out = next((p for p in here.parents if (p / "README.md").exists()), here.parents[3])

    pages_dir = out / "pages"
    assets_dir = out / "assets"
    folders = ordered_folders([f.strip() for f in args.folders.split(",") if f.strip()])

    # canonical garden commit/clean gate는 생성물을 지우거나 쓰기 전에 먼저 통과한다.
    source_page_count = sum(
        1 for folder in folders
        for path in (garden_root / "content" / folder).glob("*.md")
        if denote_id(path.name)
    )
    manifest = make_build_manifest(garden_root, folders, source_page_count)

    # 이미 회수한 원격 식별자는 동일 gid에 승계한다. 첫 씨뿌리기에는 파일이 없으므로
    # 빈 매핑으로 시작하고, 이후 갱신은 build -> relink -> audit -> 승인된 push로 가능하다.
    mapping_path = out / "mapping.json"
    previous_mapping = {}
    if mapping_path.exists():
        previous_mapping = json.loads(mapping_path.read_text(encoding="utf-8"))

    # 승계 판정 기준. TOC 를 덮어쓰기 전에 직전 판 발행면을 읽어둔다.
    #
    # 회수 이력이 있는데 직전 판 발행면을 읽을 수 없으면 어느 id 가 살아 있는지 판정할
    # 수 없다. 그 상태에서 승계하면 이 안전장치가 막으려던 사고가 그대로 열리므로, 500
    # 상한 사전검사와 같이 생성물을 건드리기 전에 멈춘다. 순수 bootstrap(회수 이력 자체가
    # 없음)만 통과시킨다 — 비울 id 가 없으니 위험도 없다.
    live_paths = previous_publish_surface(out / "TOC.md")
    if not live_paths and has_recovered_ids(previous_mapping):
        raise ValueError(
            f"직전 판 발행면을 읽을 수 없는데 mapping 에 회수된 page_id 가 있다"
            f"({out / 'TOC.md'}: "
            f"{'없음' if live_paths is None else '등록 페이지 0개'}). "
            f"어느 id 가 살아 있는지 판정할 수 없어 죽은 id 를 승계할 위험이 있다"
            f"(생성물은 건드리지 않았다). TOC 를 복원하거나, 정말 처음부터 다시 "
            f"씨뿌리는 것이면 mapping.json 의 page_id 를 비운다.")
    withheld = 0

    # 입력을 먼저 다 읽어 발행 규모를 확정한다(가든 5폴더 28MB 수준). 상한을 넘기면
    # 생성물은 하나도 건드리지 않고 실패한다 — 웹훅이 거부할 TOC 는 만들지 않는다.
    folder_sources = {}
    for folder in folders:
        notes = sorted((garden_root / "content" / folder).glob("*.md"),
                       key=lambda path: path.name)
        if not notes:
            print(f"[warn] {folder}: 노트 없음, 건너뜀")
            continue
        sources = [read_source(src, folder) for src in notes]
        sources.sort(key=source_sort_key, reverse=True)
        folder_sources[folder] = sources

    registered = len(folder_sources) + len(COLLECTIONS) + sum(
        1 for folder, sources in folder_sources.items() for source in sources
        if is_core_member(folder, source["tags"], args.core)
    )
    if registered > PUBLISH_LIMIT:
        raise ValueError(
            f"TOC 등록 {registered}개 > 위키독스 상한 {PUBLISH_LIMIT}개. "
            f"--core 로 발행면을 줄이거나 코어 정의를 조정한다(생성물은 건드리지 않았다).")

    # pages/ 초기화(생성물 전체) — 폴더 미러를 깨끗이 다시 쓴다
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    pages_dir.mkdir(parents=True)

    scrub_rules = load_scrub_rules(garden_root)
    mapping = {}
    copied = []
    toc = ["# 목차", ""]
    # 태그 집합은 0순위 탐색면이므로 authored folder 챕터들보다 먼저 둔다. 코어 모드에서도
    # 발행한다 — `autholog` 는 코어 정의의 절반이고, 그 집합면은 링크가 전부 발행면 안이라
    # 위키독스에서 온전히 순회되는 유일한 탐색면이다(botlog 는 `5 봇로그` 표지가 커버).
    toc.extend(
        f'- [{spec["subject"]}]({spec["path"]})' for spec in COLLECTIONS.values()
    )
    collection_sources = {tag: [] for tag in COLLECTIONS}
    published = set()          # TOC 에 등록된 = 라이브가 될 page 경로
    # 링크 대상 판단 기준. --garden-links 면 빈 집합이라 모든 목록이 가든으로 나간다.
    link_scope = set() if args.garden_links else published

    for folder, sources in folder_sources.items():
        (pages_dir / folder).mkdir(parents=True, exist_ok=True)
        chapter_name = CHAPTER_NAMES.get(folder, folder)

        # 챕터 표지는 아래에서 stable page URL을 사용한 recent-first index로 완성한다.
        cover_rel = f"pages/{folder}/_chapter.md"
        toc.append(f"- [{chapter_name}]({cover_rel})")
        chapter_entries = []

        # 페이지는 pages/<folder>/<id>.md → assets 는 두 단계 위.
        # TOC와 mapping 생성 순서도 가든 folder listing과 같이 newest-first다(사전 정렬됨).
        rel_prefix = "../../"
        for source in sources:
            did = source["id"]
            title_date = source_title_date(source)
            subject = subject_for(title_date, source["title"])

            raw_abstract, raw_body = extract_author_abstract(source["body"])
            abstract = transform_body(
                raw_abstract, garden_root, assets_dir, rel_prefix, copied
            ) if raw_abstract else ""
            body = transform_body(raw_body, garden_root, assets_dir, rel_prefix, copied)
            include_toc = body.count("\n## ") >= args.toc_threshold
            content = compose_page(abstract, body, source, include_toc)
            content = scrub_identity(content, scrub_rules)   # 공개 전 회사/직장 신원 난독화
            # 회수 앵커(렌더 비표시) — 2단계에서 gid<->page_id 매핑
            content = f"<!-- gid:{did} -->\n" + content

            page_rel = f"pages/{folder}/{did}.md"
            (out / page_rel).write_text(content, encoding="utf-8")
            publishing = is_core_member(folder, source["tags"], args.core)
            if publishing:
                toc.append(f"  - [{subject}]({page_rel})")
                published.add(page_rel)
            entry = {
                "path": page_rel,
                "subject": subject,
                "folder": folder,
                "source_url": source["source_url"],
                "source_date": source["date"],
                "source_lastmod": source["lastmod"],
                **public_index_metadata(source, scrub_rules),
            }
            withheld += inherit_remote_id(
                entry, previous_mapping.get(did, {}), page_rel, live_paths, publishing)
            mapping[did] = entry
            chapter_entries.append((public_index_title(source, scrub_rules), entry))
            for tag in collection_sources:
                if tag in source["tags"]:
                    collection_sources[tag].append((source, subject, entry))

        (out / cover_rel).write_text(
            chapter_index(folder, chapter_entries, link_scope), encoding="utf-8"
        )

    # 태그 집합은 authored page를 복제하지 않는 standalone top-level page다. 링크 대상은
    # 기존 mapping의 stable WikiDocs URL을 우선하고 미회수 페이지는 가든 URL로 남긴다.
    for tag, tagged in collection_sources.items():
        tagged.sort(key=lambda item: collection_sort_key(item[0]), reverse=True)
        spec = COLLECTIONS[tag]
        collection_path = out / spec["path"]
        collection_path.parent.mkdir(parents=True, exist_ok=True)
        collection_path.write_text(
            collection_index(tag, [
                (public_index_title(source, scrub_rules), entry)
                for source, _, entry in tagged
            ], link_scope),
            encoding="utf-8",
        )

    # 폴더 표지와 태그 집합 표지의 page_id를 같은 top-level navigation ledger에 승계한다.
    # `_chapters`는 garden importer가 통째로 제외하므로 Denote-ID mapping을 오염시키지 않는다.
    previous_chapters = previous_mapping.get("_chapters", {})
    chapters = {}
    for folder in folders:
        carried = {}
        withheld += inherit_remote_id(carried, previous_chapters.get(folder, {}),
                                      f"pages/{folder}/_chapter.md", live_paths)
        if carried.get("page_id"):
            chapters[folder] = {
                "page_id": carried["page_id"],
                "subject": CHAPTER_NAMES.get(folder, folder),
                "url": carried.get("url") or f"https://wikidocs.net/{carried['page_id']}",
            }
    for tag, spec in COLLECTIONS.items():
        entry = {"subject": spec["subject"], "path": spec["path"],
                 "source_url": spec["source_url"]}
        withheld += inherit_remote_id(entry, previous_chapters.get(tag, {}),
                                      spec["path"], live_paths)
        if entry.get("page_id") and not entry.get("url"):
            entry["url"] = f"https://wikidocs.net/{entry['page_id']}"
        chapters[tag] = entry
    mapping["_chapters"] = chapters

    # 대문: 가든 content/index.md -> README.md. README 는 위키독스 책 '대문'으로 동기화되고
    # GitHub 리포 대문이기도 하다. index.md 도 계속 갱신되므로 빌드 때마다 재생성한다.
    # README 는 리포 루트라 이미지 rel_prefix 는 "" (assets/... 직접 참조).
    index_src = garden_root / "content" / "index.md"
    if index_src.exists():
        imeta, ibody = split_frontmatter(index_src.read_text(encoding="utf-8"))
        icontent = transform_body(ibody, garden_root, assets_dir, "", copied)
        # AI visitors 제거 + 메타데이터 섹션. 코어 판본이면 발행 규모를 그대로 밝힌다.
        icontent = readme_head(icontent, len(published),
                               sum(key != "_chapters" for key in mapping), args.core,
                               list(folder_sources))
        icontent = scrub_identity(icontent, scrub_rules)
        ititle = clean_toc_title(imeta.get("title") or "Home")
        (out / "README.md").write_text(f"# {ititle}\n\n{icontent}", encoding="utf-8")
        print(f"[ok] README    : content/index.md -> README.md ({ititle})")

    # 예산은 생성물을 건드리기 전에 이미 확정했다. 여기서는 그 계산이 실제 TOC 와
    # 어긋나지 않았는지만 확인한다(사전검사와 생성이 같은 is_core_member 를 쓴다).
    toc_registered = sum(1 for line in toc if "](pages/" in line)
    if toc_registered != registered:
        raise ValueError(
            f"발행 예산 사전검사와 실제 TOC 불일치: {registered} != {toc_registered}")

    (out / "TOC.md").write_text("\n".join(toc) + "\n", encoding="utf-8")
    mapping_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    page_count = sum(key != "_chapters" for key in mapping)
    if page_count != manifest["pages"]:
        raise ValueError(f"manifest page count drift: {manifest['pages']} != {page_count}")
    (out / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_sha = hashlib.sha256((out / MANIFEST_NAME).read_bytes()).hexdigest()
    carried_ids = sum(key != "_chapters" and bool(value.get("page_id"))
                      for key, value in mapping.items())
    print(f"[ok] out      : {out}")
    print(f"[ok] folders  : {folders}")
    collection_counts = ", ".join(
        f"{tag} {len(entries)}개" for tag, entries in collection_sources.items()
    )
    print(f"[ok] pages    : {page_count}개 (+폴더표지 {len(folders)}, 태그집합 {len(COLLECTIONS)})")
    print(f"[ok] collect  : {collection_counts}")
    print(f"[ok] assets   : {len(copied)}개")
    print(f"[ok] mapping  : mapping.json ({page_count} entries, page_id 승계 {carried_ids}개)")
    # 2단계 push 가 필요한 항목 = 발행면인데 page_id 가 없는 것. 죽은 id 를 비운 항목만
    # 세면 처음 올라가는 페이지가 신호에서 빠진다 — 그쪽도 회수 절차는 똑같이 필요하다.
    pending_recovery = sum(
        1 for key, entry in mapping.items()
        if key != "_chapters" and entry["path"] in published and not entry.get("page_id")
    ) + sum(
        1 for folder in folders if folder not in chapters
    ) + sum(
        1 for tag in COLLECTIONS if not chapters[tag].get("page_id")
    )
    if pending_recovery:
        print(f"[warn] 발행면 page_id 미회수 {pending_recovery}개: 2단계 push 가 필요하다 "
              f"(1차 push → status → recover → build/relink → 2차 push).")
    if withheld:
        print(f"[warn] 그중 {withheld}개는 발행면 신규 진입이라 직전 판 TOC 밖의 죽은 "
              f"page_id 를 승계하지 않았다.")
    print(f"[ok] manifest : {MANIFEST_NAME} ({manifest['source_commit']}, sha256 {manifest_sha})")


if __name__ == "__main__":
    sys.exit(main())
