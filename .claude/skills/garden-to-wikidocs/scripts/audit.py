#!/usr/bin/env python3
"""가든 -> 위키독스 생성물 품질 감사(audit). stdlib only.

build/relink 뒤 push 전에 실행한다. 가든은 읽기만 하며 다음을 검증한다.
- TOC 챕터 순서, 엔트리 수, 링크 경로, 안전하지 않은 제목 문자
- mapping과 생성 페이지의 1:1 대응, gid 앵커, page_id 완전성
- 코드펜스 밖 미처리 relref 부재
- 원본과 미러의 Markdown 헤딩 수 보존(줄바꿈 붕괴 탐지)
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


HERE = Path(__file__).resolve()
BUILD_PATH = HERE.with_name("build.py")
SPEC = importlib.util.spec_from_file_location("garden_to_wikidocs_build", BUILD_PATH)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)

TOC_LINE = re.compile(r"^(\s*)- \[([^\]]*)\]\(([^)]+)\)$")
HEADING = re.compile(r"^#{2,6}[ \t]+", re.MULTILINE)
GID_LINE = re.compile(r"^<!-- gid:(\d{8}T\d{6}) -->$")
RELREF_SHORTCODE = re.compile(r"\{\{<\s*relref\b")
SOURCE_URL_ID = re.compile(r"^https://notes\.junghanacs\.com/[^/]+/(\d{8}T\d{6})/$")
PROVENANCE_BLOCK = re.compile(
    r"<!-- provenance:source:start -->.*?<!-- provenance:source:end -->", re.DOTALL)
OUTPUT_ABSTRACT = re.compile(
    r'^\[\[TIP\("이 노트에 대하여"\)\]\].*?^\[\[/TIP\]\]$',
    re.DOTALL | re.MULTILINE,
)


def duplicates(values):
    seen = set()
    repeated = set()
    for value in values:
        if value is None:
            continue
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


def unprotected(text: str) -> str:
    guarded, _ = BUILD.protect_code(text)
    return guarded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--garden", default="~/repos/gh/notes")
    ap.add_argument("--out", default=None,
                    help="미러 리포 루트(기본: 이 스크립트로부터 위 README.md 있는 곳)")
    ap.add_argument("--allow-missing-page-ids", action="store_true")
    args = ap.parse_args()

    garden = Path(args.garden).expanduser()
    if args.out:
        out = Path(args.out).expanduser()
    else:
        out = next((p for p in HERE.parents if (p / "README.md").exists()), HERE.parents[3])

    errors = []
    warnings = []
    mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
    pages_map = {gid: value for gid, value in mapping.items() if gid != "_chapters"}
    folders = BUILD.ordered_folders(
        list(dict.fromkeys(value.get("folder") for value in pages_map.values()
                           if value.get("folder"))))

    manifest_path = out / BUILD.MANIFEST_NAME
    actual_manifest = None
    try:
        expected_manifest = BUILD.make_build_manifest(garden, folders, len(pages_map))
    except (OSError, ValueError) as error:
        expected_manifest = None
        errors.append(f"manifest: garden input 검증 실패: {error}")
    if not manifest_path.exists():
        errors.append(f"manifest: 없음: {manifest_path}")
    else:
        try:
            actual_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"manifest: JSON 읽기 실패: {error}")
        if actual_manifest is not None and expected_manifest is not None:
            if actual_manifest != expected_manifest:
                mismatched = [
                    key for key in sorted(set(actual_manifest) | set(expected_manifest))
                    if actual_manifest.get(key) != expected_manifest.get(key)
                ]
                errors.append(f"manifest: current garden 입력과 불일치: {mismatched}")

    # page_id/url/path는 기존 recover/relink와 garden importer의 안정성 계약이다.
    all_remote = list(pages_map.values()) + list(mapping.get("_chapters", {}).values())
    for key in ("page_id", "url"):
        dup = duplicates(value.get(key) for value in all_remote)
        if dup:
            errors.append(f"mapping: 중복 {key} {len(dup)}개: {dup[:5]}")
    bad_remote_urls = [
        value.get("url") for value in all_remote
        if value.get("page_id") and
        value.get("url") != f'https://wikidocs.net/{value["page_id"]}'
    ]
    if bad_remote_urls:
        errors.append(
            f"mapping: page_id/url 짝 불일치 {len(bad_remote_urls)}개: "
            f"{bad_remote_urls[:5]}")
    for key in ("path", "source_url"):
        dup = duplicates(value.get(key) for value in pages_map.values())
        if dup:
            errors.append(f"mapping: 중복 {key} {len(dup)}개: {dup[:5]}")

    source_gids = set()
    for folder in {value.get("folder") for value in pages_map.values()}:
        if not folder:
            continue
        source_gids.update(
            filter(None, (BUILD.denote_id(path.name)
                          for path in (garden / "content" / folder).glob("*.md")))
        )
    missing_mapping = sorted(source_gids - set(pages_map))
    extra_mapping = sorted(set(pages_map) - source_gids)
    if missing_mapping or extra_mapping:
        errors.append(
            f"mapping: garden completeness 불일치 missing={len(missing_mapping)} "
            f"extra={len(extra_mapping)}: {missing_mapping[:3]} {extra_mapping[:3]}")

    toc_lines = (out / "TOC.md").read_text(encoding="utf-8").splitlines()
    chapters = []
    children = []
    for line_number, line in enumerate(toc_lines, start=1):
        if not line.lstrip().startswith("- ["):
            continue
        match = TOC_LINE.match(line)
        if not match:
            errors.append(f"TOC:{line_number}: 파싱 불가: {line}")
            continue
        indent, label, path = match.groups()
        unsafe = sorted(set(label) & set(BUILD.TOC_UNSAFE_CHARS))
        if unsafe:
            errors.append(f"TOC:{line_number}: 안전하지 않은 제목 문자 {unsafe}: {label}")
        if not (out / path).exists():
            errors.append(f"TOC:{line_number}: 대상 파일 없음: {path}")
        if indent:
            children.append((label, path, line_number))
        else:
            chapters.append((label, path, line_number))

    expected_chapters = [
        (BUILD.CHAPTER_NAMES.get(folder, folder), f"pages/{folder}/_chapter.md")
        for folder in folders
    ]
    actual_chapters = [(label, path) for label, path, _ in chapters]
    if actual_chapters != expected_chapters:
        errors.append(f"TOC: 챕터 순서/목록 불일치: {actual_chapters} != {expected_chapters}")

    child_paths = [path for _, path, _ in children]
    expected_paths = []
    for folder in folders:
        folder_entries = [
            (gid, value) for gid, value in pages_map.items() if value.get("folder") == folder
        ]
        folder_entries.sort(
            key=lambda item: BUILD.source_sort_key({
                "id": item[0],
                "folder": folder,
                "date": item[1].get("source_date"),
                "lastmod": item[1].get("source_lastmod"),
            }),
            reverse=True,
        )
        expected_paths.extend(value["path"] for _, value in folder_entries)
        cover_path = out / f"pages/{folder}/_chapter.md"
        expected_index = BUILD.chapter_index(
            folder, [(value["subject"], value) for _, value in folder_entries]
        )
        if not cover_path.exists() or cover_path.read_text(encoding="utf-8") != expected_index:
            errors.append(f"chapter index: {folder} recent-first 목록/링크 불일치")
    if len(child_paths) != len(expected_paths):
        errors.append(f"TOC: 페이지 수 불일치: {len(child_paths)} != {len(expected_paths)}")
    if len(child_paths) != len(set(child_paths)):
        errors.append("TOC: 중복 페이지 경로 있음")
    if child_paths != expected_paths:
        first_difference = next(
            (i for i, (actual, expected) in enumerate(zip(child_paths, expected_paths))
             if actual != expected),
            min(len(child_paths), len(expected_paths)),
        )
        errors.append(
            f"TOC: folder별 source newest-first 순서 불일치 at {first_difference}: "
            f"{child_paths[first_difference:first_difference+3]} != "
            f"{expected_paths[first_difference:first_difference+3]}")
    missing_toc = sorted(set(expected_paths) - set(child_paths))
    extra_toc = sorted(set(child_paths) - set(expected_paths))
    if missing_toc:
        errors.append(f"TOC: 누락 경로 {len(missing_toc)}개: {missing_toc[:5]}")
    if extra_toc:
        errors.append(f"TOC: 미등록 경로 {len(extra_toc)}개: {extra_toc[:5]}")

    missing_ids = []
    heading_mismatches = []
    unresolved = []
    provenance_errors = []
    metadata_errors = []
    abstract_pages = 0
    for gid, value in pages_map.items():
        page_path = out / value["path"]
        if not page_path.exists():
            errors.append(f"mapping: 생성 페이지 없음: {value['path']}")
            continue
        output = page_path.read_text(encoding="utf-8")
        first_line = output.splitlines()[0] if output else ""
        gid_match = GID_LINE.match(first_line)
        if not gid_match or gid_match.group(1) != gid:
            errors.append(f"mapping: gid 앵커 불일치: {value['path']}")
        if not value.get("page_id"):
            missing_ids.append(gid)
        if RELREF_SHORTCODE.search(unprotected(output)):
            unresolved.append(value["path"])

        source_path = garden / "content" / value["folder"] / f"{gid}.md"
        if not source_path.exists():
            errors.append(f"garden: 원본 없음: {source_path}")
            continue
        source = BUILD.read_source(source_path, value["folder"])
        source_body = source["body"]

        expected_cache = {
            "source_url": source["source_url"],
            "source_date": source["date"],
            "source_lastmod": source["lastmod"],
        }
        for key, expected in expected_cache.items():
            if value.get(key) != expected:
                metadata_errors.append(f"{gid}:{key}")
        url_match = SOURCE_URL_ID.fullmatch(value.get("source_url", ""))
        if not url_match or url_match.group(1) != gid:
            metadata_errors.append(f"{gid}:source_url join key")
        expected_subject = BUILD.subject_for(
            BUILD.source_title_date(source), source["title"]
        )
        if value.get("subject") != expected_subject:
            metadata_errors.append(f"{gid}:subject date")

        provenance = list(PROVENANCE_BLOCK.finditer(output))
        if len(provenance) != 1 or output.count(source["source_url"]) != 1:
            provenance_errors.append(f"{gid}:block/url count")
        else:
            provenance_match = provenance[0]
            raw_abstract, _ = BUILD.extract_author_abstract(source_body)
            output_abstract = OUTPUT_ABSTRACT.search(output)
            if raw_abstract:
                abstract_pages += 1
                if not output_abstract or output_abstract.end() > provenance_match.start():
                    provenance_errors.append(f"{gid}:abstract ordering")
                elif (BUILD.PROVENANCE_START in output_abstract.group(0) or
                      BUILD.PROVENANCE_END in output_abstract.group(0)):
                    provenance_errors.append(f"{gid}:provenance inside abstract")
            else:
                visible = output.split("\n", 1)[1].lstrip() if "\n" in output else ""
                if not visible.startswith(BUILD.PROVENANCE_START):
                    provenance_errors.append(f"{gid}:provenance not first")

        source_headings = len(HEADING.findall(unprotected(source_body)))
        output_headings = len(HEADING.findall(unprotected(output)))
        if source_headings != output_headings:
            heading_mismatches.append(
                f"{value['path']}({source_headings}->{output_headings})")

    if missing_ids and not args.allow_missing_page_ids:
        errors.append(f"mapping: page_id 없는 항목 {len(missing_ids)}개: {missing_ids[:5]}")
    elif missing_ids:
        warnings.append(f"mapping: page_id 없는 항목 {len(missing_ids)}개")
    if unresolved:
        errors.append(f"페이지: 코드펜스 밖 미처리 relref {len(unresolved)}개: {unresolved[:5]}")
    if metadata_errors:
        errors.append(
            f"mapping: garden source metadata/title 불일치 {len(metadata_errors)}개: "
            f"{metadata_errors[:5]}")
    if provenance_errors:
        errors.append(
            f"페이지: provenance/abstract 계약 불일치 {len(provenance_errors)}개: "
            f"{provenance_errors[:5]}")
    if heading_mismatches:
        errors.append(
            f"페이지: 원본/미러 헤딩 수 불일치 {len(heading_mismatches)}개: "
            f"{heading_mismatches[:5]}")

    for warning in warnings:
        print(f"[warn] {warning}")
    if errors:
        for error in errors:
            print(f"[err] {error}", file=sys.stderr)
        print(f"[fail] audit: 오류 {len(errors)}개", file=sys.stderr)
        return 1

    print(f"[ok] manifest : schema/source commit/clean/folders/pages/content hash 일치")
    print(f"[ok] TOC      : 챕터 {len(chapters)}개, 페이지 {len(children)}개, folder별 source newest-first")
    print(f"[ok] chapters : explicit recent-first index {len(chapters)}개")
    print(f"[ok] mapping  : {len(pages_map)}개, page_id {len(pages_map)-len(missing_ids)}개, uniqueness/completeness 보존")
    print(f"[ok] source   : garden metadata/title/provenance 전 페이지 일치 (abstract-first {abstract_pages}개)")
    print("[ok] headings : 원본/미러 전 페이지 보존")
    print("[ok] relref   : 코드펜스 밖 미처리 0개")
    print("[ok] audit    : 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
