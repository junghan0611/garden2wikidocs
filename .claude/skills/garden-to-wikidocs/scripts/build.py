#!/usr/bin/env python3
"""garden -> wikidocs github-book 변환기 (stdlib only).

가든(Quartz/Hugo-flavored MD)의 노트를 위키독스 깃허브 연동 책 형식으로 변환한다.
가든 원본은 절대 수정하지 않는다(read-only). 산출물은 out 디렉토리의
TOC.md / pages/*.md / assets/ 뿐이다.

사용:
    build.py --manifest sample.json [--garden ~/repos/gh/notes] [--out <repo root>]

manifest(JSON) 스키마:
    {
      "book_title": "...",              # README 참고용(현재 README는 건드리지 않음)
      "garden_root": "~/repos/gh/notes",# --garden 로 덮어쓸 수 있음
      "entries": [
        {"num": "01", "src": "content/notes/2025....md"},
        {"num": "05", "src": "content/meta/2022....md"},
        {"num": "05-1", "src": "content/notes/2025....md"}  # num 의 '-' 깊이가 계층
      ]
    }
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------- 제목/슬러그

# 가든 내부 표식 문자(태그/시퀀스/저자 마커). 위키독스 제목/링크에선 제거한다.
SIGILS = "#@§¤†‡©※¶‣∷"


def clean_title(raw: str) -> str:
    """가든 sigil 을 제거해 사람이 읽을 제목으로. (규칙은 SKILL.md 에 문서화, 조정 가능)"""
    t = (raw or "").strip().strip('"').strip("'")
    for ch in SIGILS:
        t = t.replace(ch, "")
    t = re.sub(r"\s+", " ", t).strip()
    t = t.lstrip(":·•*-— ").strip()
    return t


def slugify(title: str) -> str:
    s = clean_title(title).lower()
    s = re.sub(r"[^0-9a-z가-힣]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or "page"


DENOTE_ID = re.compile(r"(\d{8}T\d{6})")


def denote_id(path_or_name: str):
    m = DENOTE_ID.search(path_or_name)
    return m.group(1) if m else None


# ---------------------------------------------------------------- frontmatter

def split_frontmatter(text: str):
    """(meta dict, body) 반환. title 등 최상위 단순 key 만 파싱(YAML 라이브러리 미사용)."""
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

CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
HEAD_ANCHOR = re.compile(r"[ \t]*\{#[^}]*\}[ \t]*$", re.M)
TIMESTAMP = re.compile(
    r'<span class="timestamp-wrapper">\s*<span class="timestamp">\s*'
    r'(\[[^\]]*\])\s*</span>\s*</span>'
)
CALLOUT = re.compile(r"^>\s*\[!([A-Za-z]+)\]\s*(.*)$")
CSL_ID = re.compile(r'<a id="citeproc_bib_item_\d+"></a>')
DIVTAG = re.compile(r"</?div[^>]*>")
ATAG = re.compile(r'<a\s+[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
RELREF = re.compile(r'\[([^\]]*)\]\(\{\{<\s*relref\s+"([^"]+)"\s*>\}\}\)')
IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

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
    """> [!type] title  블록 -> [[TIP("label")]] ... [[/TIP]]"""
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
        if ctitle and ctitle.lower() != ctype:
            label = clean_title(ctitle)
        else:
            label = CALLOUT_LABELS.get(ctype, ctype)
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
            return inner            # 인용 앵커 -> 텍스트만
        return f"[{inner}]({href})"

    return ATAG.sub(a_repl, text)


def make_relref(export_map: dict):
    def repl(m):
        txt = clean_title(m.group(1))
        target = m.group(2)                 # 예: /journal/20250217T000000.md
        did = denote_id(target)
        if did and did in export_map:       # 하이브리드: 내보낸 집합 안이면 내부 링크
            return f"[{txt}](pages/{export_map[did]})"
        path = target[:-3] if target.endswith(".md") else target
        return f"[{txt}](https://notes.junghanacs.com{path}/)"
    return repl


def make_images(garden_root: Path, assets_dir: Path, copied: list):
    def repl(m):
        alt, src = m.group(1), m.group(2)
        if src.startswith("/images/"):
            fn = src[len("/images/"):]
            src_file = garden_root / "static" / "images" / fn
            if src_file.exists():
                assets_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, assets_dir / fn)
                copied.append(fn)
                enc = fn.replace(" ", "%20")
                return f"![{alt}](../assets/{enc})"
        return m.group(0)               # 외부 URL 이미지는 그대로
    return repl


def transform_body(body, garden_root, assets_dir, export_map, copied):
    body, blocks = protect_code(body)
    body = HEAD_ANCHOR.sub("", body)
    body = TIMESTAMP.sub(r"\1", body)
    body = convert_callouts(body)
    body = convert_html(body)
    body = RELREF.sub(make_relref(export_map), body)
    body = IMG.sub(make_images(garden_root, assets_dir, copied), body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    body = restore_code(body, blocks)
    return body


# ---------------------------------------------------------------- 빌드

def depth_of(num: str) -> int:
    return num.count("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--garden", default=None)
    ap.add_argument("--out", default=None,
                    help="책 리포 루트(기본: manifest 로부터 위로 올라가며 README.md 있는 곳)")
    ap.add_argument("--toc-threshold", type=int, default=3,
                    help="이 개수 이상 h2 헤딩이면 페이지 상단에 [TOC] 삽입")
    args = ap.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    garden_root = Path(args.garden or manifest.get("garden_root", "~/repos/gh/notes")).expanduser()
    if args.out:
        out = Path(args.out).expanduser()
    else:
        out = next((p for p in manifest_path.parents if (p / "README.md").exists()),
                   manifest_path.parents[2])
    pages_dir = out / "pages"
    assets_dir = out / "assets"

    entries = manifest["entries"]

    # 1) export_map(denote-id -> page filename) 선계산 → 내부 링크 해석에 사용
    export_map = {}
    for e in entries:
        src = garden_root / e["src"]
        meta, _ = split_frontmatter(src.read_text(encoding="utf-8"))
        title = e.get("title") or meta.get("title") or src.stem
        fn = f"{e['num']}-{slugify(title)}.md"
        e["_title"] = clean_title(title)
        e["_fname"] = fn
        did = denote_id(e["src"])
        if did:
            export_map[did] = fn

    # 2) pages/ 초기화(기존 생성물만 제거) 후 각 페이지 작성
    if pages_dir.exists():
        for f in pages_dir.glob("*.md"):
            f.unlink()
    pages_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for e in entries:
        src = garden_root / e["src"]
        _, body = split_frontmatter(src.read_text(encoding="utf-8"))
        content = transform_body(body, garden_root, assets_dir, export_map, copied)
        if content.count("\n## ") >= args.toc_threshold:
            content = "[TOC]\n\n" + content
        (pages_dir / e["_fname"]).write_text(content, encoding="utf-8")

    # 3) TOC.md
    toc = ["# 목차", ""]
    for e in entries:
        indent = "  " * depth_of(e["num"])
        toc.append(f"{indent}- [{e['num']}. {e['_title']}](pages/{e['_fname']})")
    (out / "TOC.md").write_text("\n".join(toc) + "\n", encoding="utf-8")

    # 요약 출력
    print(f"[ok] book_title : {manifest.get('book_title','')}")
    print(f"[ok] garden     : {garden_root}")
    print(f"[ok] out        : {out}")
    print(f"[ok] pages      : {len(entries)}개")
    print(f"[ok] assets 복사 : {len(copied)}개 {copied if copied else ''}")
    for e in entries:
        print(f"      {e['_fname']}   <-  {e['src']}")


if __name__ == "__main__":
    sys.exit(main())
