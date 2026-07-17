#!/usr/bin/env python3
"""garden -> wikidocs github-book 변환기 v2 (stdlib only).

폴더 미러 방식. 가든의 각 폴더(journal/meta/notes/bib/botlog)를 위키독스 책의
'챕터'로 만든다. 가든 원본은 절대 수정하지 않는다(read-only).

산출물(이 리포 안):
    TOC.md                       폴더=챕터 계층
    pages/<folder>/_chapter.md   챕터 표지([[SubPages]])
    pages/<folder>/<denote-id>.md  각 노트 (H1 없음, gid 앵커 포함)
    assets/                      복사된 로컬 이미지
    mapping.json                 denote-id -> {path, subject}  (씨뿌리기 시점 기록)

3단계 파이프라인:
    1) seed   : build.py --folders journal  → 생성, 내부 relref는 가든 절대URL
                (page_id 아직 없음). 각 페이지에 <!-- gid:ID --> 앵커.
    2) recover: (별도) push 후 book get 으로 gid<->page_id 회수해 mapping.json 갱신
    3) relink : (별도) 내부 relref 를 wikidocs.net/<page_id> 로 재작성

사용:
    build.py --folders journal [--garden ~/repos/gh/notes] [--out <repo root>]
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

GARDEN_URL = "https://notes.junghanacs.com"


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
# 원하는 순서를 만든다(저널·메타·참고문헌·노트·봇로그).
CHAPTER_NAMES = {
    "journal": "1 저널", "meta": "2 메타", "bib": "3 참고문헌",
    "notes": "4 노트", "botlog": "5 봇로그", "talks": "토크",
}

# ---------------------------------------------------------------- 제목/식별자

SIGILS = "#@§¤†‡©※¶‣∷"
DENOTE_ID = re.compile(r"(\d{8}T\d{6})")


def clean_title(raw: str) -> str:
    t = (raw or "").strip().strip('"').strip("'")
    for ch in SIGILS:
        t = t.replace(ch, "")
    t = re.sub(r"\s+", " ", t).strip()
    t = t.lstrip(":·•*-— ").strip()
    return t


def denote_id(s: str):
    m = DENOTE_ID.search(s)
    return m.group(1) if m else None


def subject_for(did: str, title: str) -> str:
    """제목 앞에 날짜 8자리 접두어를 붙여 알파벳순=시간순으로 정렬되게 한다.
    단, 제목이 이미 그 날짜(ISO 또는 8자리)로 시작하면 중복을 피한다."""
    d8 = did[:8]
    iso = f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}"
    ct = clean_title(title)
    if ct.startswith(iso) or ct.startswith(d8):
        return ct
    return f"{d8} {ct}"


# ---------------------------------------------------------------- frontmatter

def split_frontmatter(text: str):
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
            meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return meta, body


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
CSL_ID = re.compile(r'<a id="citeproc_bib_item_\d+"></a>')
DIVTAG = re.compile(r"</?div[^>]*>")
ATAG = re.compile(r'<a\s+[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
# 링크 텍스트에 `]` 가 있어도(중첩 대괄호) 실제 링크 종료 `](` 에서만 끊기게 tempered.
RELREF = re.compile(r'\[((?:[^\]]|\](?!\())*)\]\(\{\{<\s*relref\s+"([^"]+)"\s*>\}\}\)')
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
    text = CSL_ID.sub("", text)
    text = DIVTAG.sub("", text)

    def a_repl(m):
        href, inner = m.group(1), m.group(2).strip()
        if href.startswith("#"):
            return inner
        return f"[{inner}]({href})"

    return ATAG.sub(a_repl, text)


def relref_repl(m):
    """씨뿌리기 단계: 모든 내부 relref 를 가든 절대 URL 로. (page_id 는 3단계에서)"""
    txt = clean_title(m.group(1))
    target = m.group(2)
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
    body = RELREF.sub(relref_repl, body)
    body = FIGURE.sub(figure_repl, body)
    body = IMG.sub(make_images(garden_root, assets_dir, rel_prefix, copied), body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    body = restore_code(body, blocks)
    return body


# ---------------------------------------------------------------- 빌드(씨뿌리기)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folders", required=True, help="가든 폴더들, 쉼표구분 (예: journal,meta)")
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
    folders = [f.strip() for f in args.folders.split(",") if f.strip()]

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

        # 챕터 표지: [[SubPages]] 로 하위 자동 나열
        cover_rel = f"pages/{folder}/_chapter.md"
        (out / cover_rel).write_text(f"[[SubPages]]\n", encoding="utf-8")
        toc.append(f"- [{chapter_name}]({cover_rel})")

        # 페이지는 pages/<folder>/<id>.md → assets 는 두 단계 위
        rel_prefix = "../../"
        for src in notes:
            did = denote_id(src.name)
            if not did:
                continue
            meta, body = split_frontmatter(src.read_text(encoding="utf-8"))
            title = meta.get("title") or src.stem
            subject = subject_for(did, title)
            content = transform_body(body, garden_root, assets_dir, rel_prefix, copied)
            content = scrub_identity(content, scrub_rules)   # 공개 전 회사/직장 신원 난독화
            if content.count("\n## ") >= args.toc_threshold:
                content = "[TOC]\n\n" + content
            # 회수 앵커(렌더 비표시) — 2단계에서 gid<->page_id 매핑
            content = f"<!-- gid:{did} -->\n" + content

            page_rel = f"pages/{folder}/{did}.md"
            (out / page_rel).write_text(content, encoding="utf-8")
            toc.append(f"  - [{subject}]({page_rel})")
            mapping[did] = {"path": page_rel, "subject": subject, "folder": folder}

    # 대문: 가든 content/index.md -> README.md. README 는 위키독스 책 '대문'으로 동기화되고
    # GitHub 리포 대문이기도 하다. index.md 도 계속 갱신되므로 빌드 때마다 재생성한다.
    # README 는 리포 루트라 이미지 rel_prefix 는 "" (assets/... 직접 참조).
    index_src = garden_root / "content" / "index.md"
    if index_src.exists():
        imeta, ibody = split_frontmatter(index_src.read_text(encoding="utf-8"))
        icontent = transform_body(ibody, garden_root, assets_dir, "", copied)
        icontent = readme_head(icontent)            # AI visitors 제거 + 메타데이터 섹션
        icontent = scrub_identity(icontent, scrub_rules)
        ititle = clean_title(imeta.get("title") or "Home")
        (out / "README.md").write_text(f"# {ititle}\n\n{icontent}", encoding="utf-8")
        print(f"[ok] README    : content/index.md -> README.md ({ititle})")

    (out / "TOC.md").write_text("\n".join(toc) + "\n", encoding="utf-8")
    (out / "mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[ok] out      : {out}")
    print(f"[ok] folders  : {folders}")
    print(f"[ok] pages    : {len(mapping)}개 (+챕터표지 {len(folders)})")
    print(f"[ok] assets   : {len(copied)}개")
    print(f"[ok] mapping  : mapping.json ({len(mapping)} entries, page_id 는 아직 비어있음)")


if __name__ == "__main__":
    sys.exit(main())
