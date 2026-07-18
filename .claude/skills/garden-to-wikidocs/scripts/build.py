#!/usr/bin/env python3
"""garden -> wikidocs github-book 변환기 v2 (stdlib only).

폴더 미러 방식. 가든의 각 폴더(journal/meta/notes/bib/botlog)를 위키독스 책의
'챕터'로 만든다. 가든 원본은 절대 수정하지 않는다(read-only).

산출물(이 리포 안):
    TOC.md                       폴더=챕터 계층
    pages/<folder>/_chapter.md   챕터 표지(explicit recent-first index)
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


def readme_meta_block() -> str:
    """책 대문 상단 메타데이터 섹션(헤딩 레벨). 마지막 동기화 = 빌드 날짜."""
    return (
        "## 이 책에 대하여\n\n"
        "정한(Junghan Kim)의 디지털 가든을 위키독스로 미러링한 책입니다. "
        "원본과 최신본은 가든에서 보실 수 있습니다.\n\n"
        f"- 원본 가든: <{GARDEN_HOME}>\n"
        f"- 가든 소스: <{GARDEN_REPO}>\n"
        f"- 미러 리포: <{MIRROR_REPO}>\n"
        f"- 마지막 동기화: {date.today().isoformat()}\n"
    )


def readme_head(readme_body: str) -> str:
    body = AI_VISITORS_BQ.sub("", readme_body, count=1)
    body = AI_VISITORS_SEC.sub("", body, count=1)
    return readme_meta_block() + "\n" + body.lstrip("\n")


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


def chapter_index(folder: str, entries: list) -> str:
    """WikiDocs sidebar 오름차순과 분리된 안정적 recent-first chapter index."""
    basis = "작성일(source_date)" if folder == "journal" \
        else "최근 수정일(source_lastmod, 없으면 source_date)"
    lines = [
        CHAPTER_INDEX_START,
        "## 최신순 목록",
        "",
        f"가든과 같은 {basis} 기준의 최신순 목록입니다.",
        "",
    ]
    for subject, entry in entries:
        target = entry.get("url") or entry["source_url"]
        lines.append(f"- [{subject}]({target})")
    lines.extend([CHAPTER_INDEX_END, ""])
    return "\n".join(lines)


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

    # pages/ 초기화(생성물 전체) — 폴더 미러를 깨끗이 다시 쓴다
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    pages_dir.mkdir(parents=True)

    scrub_rules = load_scrub_rules(garden_root)
    mapping = {}
    copied = []
    toc = ["# 목차", ""]

    for folder in folders:
        src_dir = garden_root / "content" / folder
        notes = sorted(src_dir.glob("*.md"), key=lambda p: p.name)
        if not notes:
            print(f"[warn] {folder}: 노트 없음, 건너뜀")
            continue

        (pages_dir / folder).mkdir(parents=True, exist_ok=True)
        chapter_name = CHAPTER_NAMES.get(folder, folder)

        # 챕터 표지는 아래에서 stable page URL을 사용한 recent-first index로 완성한다.
        cover_rel = f"pages/{folder}/_chapter.md"
        toc.append(f"- [{chapter_name}]({cover_rel})")
        chapter_entries = []

        # 페이지는 pages/<folder>/<id>.md → assets 는 두 단계 위.
        # TOC와 mapping 생성 순서도 가든 folder listing과 같이 newest-first다.
        rel_prefix = "../../"
        sources = [read_source(src, folder) for src in notes]
        sources.sort(key=source_sort_key, reverse=True)
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
            toc.append(f"  - [{subject}]({page_rel})")
            entry = {
                "path": page_rel,
                "subject": subject,
                "folder": folder,
                "source_url": source["source_url"],
                "source_date": source["date"],
                "source_lastmod": source["lastmod"],
            }
            previous = previous_mapping.get(did, {})
            for key in ("page_id", "url"):
                if previous.get(key):
                    entry[key] = previous[key]
            mapping[did] = entry
            chapter_entries.append((subject, entry))

        (out / cover_rel).write_text(
            chapter_index(folder, chapter_entries), encoding="utf-8"
        )

    # 챕터 표지도 이미 회수한 page_id를 승계하되 subject는 현재 번호 제목으로 갱신한다.
    previous_chapters = previous_mapping.get("_chapters", {})
    chapters = {}
    for folder in folders:
        previous = previous_chapters.get(folder, {})
        if previous.get("page_id"):
            chapters[folder] = {
                "page_id": previous["page_id"],
                "subject": CHAPTER_NAMES.get(folder, folder),
                "url": previous.get("url") or f"https://wikidocs.net/{previous['page_id']}",
            }
    if chapters:
        mapping["_chapters"] = chapters

    # 대문: 가든 content/index.md -> README.md. README 는 위키독스 책 '대문'으로 동기화되고
    # GitHub 리포 대문이기도 하다. index.md 도 계속 갱신되므로 빌드 때마다 재생성한다.
    # README 는 리포 루트라 이미지 rel_prefix 는 "" (assets/... 직접 참조).
    index_src = garden_root / "content" / "index.md"
    if index_src.exists():
        imeta, ibody = split_frontmatter(index_src.read_text(encoding="utf-8"))
        icontent = transform_body(ibody, garden_root, assets_dir, "", copied)
        icontent = readme_head(icontent)            # AI visitors 제거 + 메타데이터 섹션
        icontent = scrub_identity(icontent, scrub_rules)
        ititle = clean_toc_title(imeta.get("title") or "Home")
        (out / "README.md").write_text(f"# {ititle}\n\n{icontent}", encoding="utf-8")
        print(f"[ok] README    : content/index.md -> README.md ({ititle})")

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
    print(f"[ok] pages    : {page_count}개 (+챕터표지 {len(folders)})")
    print(f"[ok] assets   : {len(copied)}개")
    print(f"[ok] mapping  : mapping.json ({page_count} entries, page_id 승계 {carried_ids}개)")
    print(f"[ok] manifest : {MANIFEST_NAME} ({manifest['source_commit']}, sha256 {manifest_sha})")


if __name__ == "__main__":
    sys.exit(main())
