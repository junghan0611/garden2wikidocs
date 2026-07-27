#!/usr/bin/env python3
"""3단계 파이프라인 3단계: 링크 실화(relink). stdlib only.

씨뿌리기(build.py) 단계에서 모든 내부 링크는 가든 절대 URL
    https://notes.junghanacs.com/<...>/<denote-id>/
로 심어졌다. 회수(recover.py) 후 mapping.json 에 page_id 가 채워지면, 이 스크립트가
page_id 가 있는 링크만 https://wikidocs.net/<page_id> 로 재작성한다.
mapping 에 없거나 page_id 가 아직 없는 링크는 가든 URL 그대로 둔다(하이브리드).

이렇게 하면 이미 올린 폴더 내부(및 폴더 간) 순회는 위키독스 안에서 살아나고,
아직 안 올린 폴더로의 링크는 가든으로 나간다. 폴더를 더 올릴수록 실화 비율이 오른다.

발행면 게이트는 두 방향 모두에 건다. 위키독스는 TOC.md 에 등록된 페이지만 라이브로
두고 빠진 페이지는 삭제한다(2026-07 실측).

- 링크 대상(target): mapping 에 page_id 가 남아 있어도 TOC 밖 페이지의 위키독스 URL 은
  404 다. 실화하는 대상은 항상 현재 TOC 에 등록된 경로로 제한한다.
- 실화 파일(source): TOC 밖 페이지는 라이브에 존재하지 않는다. 그 안의 위키독스 URL 은
  아무도 볼 수 없는데, 발행면이 바뀔 때마다 리포 전체를 흔든다(2026-07 실측: 코어
  발행면 249개인데 게이트 없는 relink 가 826개 파일을 고쳤고 그 중 639개가 발행면
  밖이었다). 그래서 쓰기 대상도 발행면으로 제한한다. 책 대문(README.md)은 TOC 밖이지만
  항상 라이브이므로 예외로 포함한다.

- 코드펜스 안 URL 은 건드리지 않는다(코드 예시는 literal 유지).
- 가든 URL 형태가 아닌 것(홈 `/`, `/index`, `/static/...`)은 denote-id 가 없어 자동 제외.
- 보존 대상 태그 집합(`/tags/autholog/`)은 회수된 standalone 표지 page_id로 실화한다.
- 이미 wikidocs.net URL 인 링크는 가든 패턴에 안 걸리므로 반복 실행에 안전(idempotent).

사용:
    relink.py [--repo <root>] [--pages <dir>] [--mapping <file>] [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

WIKIDOCS_URL = "https://wikidocs.net"

# TOC.md 의 링크 대상 경로(`- [제목](pages/...)`). 발행면 게이트의 입력이다.
TOC_TARGET = re.compile(r"^\s*- \[[^\]]*\]\((pages/[^)]+)\)\s*$", re.M)

# build.py 와 동일한 펜스 규칙: 줄 시작(들여쓰기 허용) 3+ backtick, 여는 개수 이상으로 닫기.
CODE_FENCE = re.compile(r"^[ \t]*(`{3,})[^\n]*\n.*?^[ \t]*\1`*[ \t]*$",
                        re.DOTALL | re.MULTILINE)
# 가든 내부 노트 링크: 경로 마지막 세그먼트가 denote-id. 홈/index/static 은 안 걸린다.
GARDEN_LINK = re.compile(
    r"https://notes\.junghanacs\.com/(?:[^()\s]*/)?(\d{8}T\d{6})/?")
# 가든 폴더 인덱스 링크(denote-id 없음): 챕터 표지 URL 로 실화. 뒤에 숫자(=노트 id) 없어야.
FOLDER_LINK = re.compile(
    r"https://notes\.junghanacs\.com/(journal|meta|notes|bib|botlog)/(?![0-9])")
# WikiDocs 자체 태그 기능을 대신하는 generated collection page. 일반 태그는 가든에 둔다.
COLLECTION_LINK = re.compile(
    r"https://notes\.junghanacs\.com/tags/(autholog)/?")
# 페이지별 provenance의 exact source URL은 원본 귀환 경로이므로 절대 실화하지 않는다.
PROVENANCE_BLOCK = re.compile(
    r"<!-- provenance:source:start -->.*?<!-- provenance:source:end -->", re.DOTALL)


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


def protect_provenance(text):
    blocks = []

    def repl(m):
        blocks.append(m.group(0))
        return f"\x00PROVENANCE{len(blocks)-1}\x00"

    return PROVENANCE_BLOCK.sub(repl, text), blocks


def restore_provenance(text, blocks):
    for i, block in enumerate(blocks):
        text = text.replace(f"\x00PROVENANCE{i}\x00", block)
    return text


def toc_path_of(path: Path, pages_dir: Path) -> str:
    """pages 디렉토리 안의 파일을 TOC.md 가 쓰는 경로 표기로 되돌린다.

    TOC 경로는 build 규약상 항상 리포 루트 기준 `pages/<folder>/<name>.md` 다.
    `--pages` 로 다른 위치를 물려도 같은 규약으로 맞춰야 게이트가 동작한다.
    """
    return f"pages/{path.relative_to(pages_dir).as_posix()}"


def relink_targets(pages_dir: Path, published):
    """실화할 파일 = 현재 발행면.

    발행면을 모르는 채로 전량을 고치는 fail-open 은 이 스크립트의 불변식과 정반대다
    (라이브에 없는 페이지를 흔들고, 죽은 URL 을 심을 수 있다). 그래서 published 가
    없으면 목록을 만들지 않고 실패한다.
    """
    if published is None:
        raise ValueError("발행면(published) 없이는 실화 대상을 정할 수 없다")
    live, skipped = [], []
    for path in sorted(pages_dir.rglob("*.md")):
        (live if toc_path_of(path, pages_dir) in published else skipped).append(path)
    return live, skipped


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None,
                    help="리포 루트(기본: 이 스크립트 기준 README.md 있는 곳). "
                         "TOC.md/README.md 를 여기서 찾는다.")
    ap.add_argument("--pages", default=None,
                    help="pages 디렉토리(기본: 리포 루트/pages)")
    ap.add_argument("--mapping", default=None,
                    help="mapping.json 경로(기본: 리포 루트/mapping.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="파일을 쓰지 않고 실화될 링크 수만 보고")
    args = ap.parse_args(argv)

    here = Path(__file__).resolve()
    if args.repo:
        root = Path(args.repo).expanduser()
    else:
        root = next((p for p in here.parents if (p / "README.md").exists()), here.parents[3])
    pages_dir = Path(args.pages).expanduser() if args.pages else root / "pages"
    mapping_path = Path(args.mapping).expanduser() if args.mapping else root / "mapping.json"

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    chapters = mapping.get("_chapters", {})

    # 현재 TOC 에 등록된 경로 = 라이브가 되는 페이지. 여기 없는 page_id 는 죽은 URL이다.
    # TOC 가 없으면 무엇이 발행면인지 알 수 없다 — 게이트를 풀고 전량 실화하는 fail-open
    # 대신 멈춘다(잘못된 --repo 나 TOC 유실이 2천 파일을 흔드는 사고를 막는다).
    toc_path = root / "TOC.md"
    if not toc_path.exists():
        print(f"[err] TOC.md 없음: {toc_path} — 발행면을 모르면 실화할 대상을 정할 수 "
              "없다. build 를 먼저 돌린다.", file=sys.stderr)
        return 1
    published = set(TOC_TARGET.findall(toc_path.read_text(encoding="utf-8")))

    def is_published(path):
        return path in published

    page_id = {did: v["page_id"] for did, v in mapping.items()
               if did != "_chapters" and v.get("page_id") and is_published(v["path"])}
    chapter_id = {f: c["page_id"] for f, c in chapters.items()
                  if c.get("page_id") and is_published(c.get("path")
                                                       or f"pages/{f}/_chapter.md")}

    stats = {"reified": 0, "reified_folder": 0, "reified_collection": 0,
             "kept": 0, "files_changed": 0}

    def repl(m):
        did = m.group(1)
        pid = page_id.get(did)
        if pid:
            stats["reified"] += 1
            return f"{WIKIDOCS_URL}/{pid}"
        stats["kept"] += 1
        return m.group(0)

    def folder_repl(m):
        cid = chapter_id.get(m.group(1))
        if cid:
            stats["reified_folder"] += 1
            return f"{WIKIDOCS_URL}/{cid}"
        stats["kept"] += 1
        return m.group(0)

    def collection_repl(m):
        cid = chapter_id.get(m.group(1))
        if cid:
            stats["reified_collection"] += 1
            return f"{WIKIDOCS_URL}/{cid}"
        stats["kept"] += 1
        return m.group(0)

    md_files, skipped = relink_targets(pages_dir, published)
    live_pages = len(md_files)
    readme = root / "README.md"          # 대문(가든 index.md 변환본)도 링크 실화 대상
    if readme.exists():
        md_files.append(readme)
    for f in md_files:
        text = f.read_text(encoding="utf-8")
        guarded, code_blocks = protect_code(text)
        guarded, provenance_blocks = protect_provenance(guarded)
        new = GARDEN_LINK.sub(repl, guarded)      # 노트 링크 -> page_id URL
        new = FOLDER_LINK.sub(folder_repl, new)   # 폴더 인덱스 링크 -> 챕터 표지 URL
        new = COLLECTION_LINK.sub(collection_repl, new)  # 보존 태그 -> 집합 표지 URL
        new = restore_provenance(new, provenance_blocks)
        new = restore_code(new, code_blocks)
        if new != text:
            stats["files_changed"] += 1
            if not args.dry_run:
                f.write_text(new, encoding="utf-8")

    mode = "dry-run(미기록)" if args.dry_run else "기록완료"
    print(f"[ok] pages     : {pages_dir} (대상 {len(md_files)}개 = 발행면 {live_pages} "
          f"+ 대문 {len(md_files) - live_pages}, 발행면 밖 {len(skipped)}개 건너뜀)")
    print(f"[ok] mapping   : {mapping_path} (page_id {len(page_id)}개)")
    print(f"[ok] 노트 실화  : {stats['reified']}개 -> wikidocs.net/<page_id> [{mode}]")
    print(f"[ok] 폴더 실화  : {stats['reified_folder']}개 -> wikidocs.net/<챕터 표지>")
    print(f"[ok] 집합 실화  : {stats['reified_collection']}개 -> wikidocs.net/<태그 집합> (표지 매핑 {len(chapter_id)}개)")
    print(f"[ok] 가든 유지  : {stats['kept']}개 링크 (매핑 없음/미시드)")
    print(f"[ok] 바뀐 파일 : {stats['files_changed']}개")


if __name__ == "__main__":
    sys.exit(main())
