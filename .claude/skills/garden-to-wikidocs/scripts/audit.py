#!/usr/bin/env python3
"""가든 -> 위키독스 생성물 품질 감사(audit). stdlib only.

build/relink 뒤 push 전에 실행한다. 가든은 읽기만 하며 다음을 검증한다.
- TOC 챕터/태그 집합 순서, 엔트리 수, 링크 경로, 안전하지 않은 제목 문자
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
# 위키독스 책 설정에 손으로 붙여넣는 사이드바 스크립트. GitHub 동기화 대상이 아니라서
# 리포와 조용히 어긋날 수 있으므로 CH 배열을 TOC/mapping 과 대조한다.
USER_SCRIPT_NAME = "wikidocs-user-script.js"
# `var CH=[...]` 선언부만 잘라 낸 뒤 그 안에서 항목을 읽는다. 파일 전체에서 항목 패턴을
# 찾으면 주석에 적은 예시([380373,'1 저널'] 같은)까지 챕터로 오인한다.
USER_SCRIPT_CH_ARRAY = re.compile(r"var\s+CH\s*=\s*\[(.*?)\]\s*;", re.DOTALL)
USER_SCRIPT_CH_ITEM = re.compile(r"\[(\d+|null)\s*,\s*'([^']*)'\]")
HEADING = re.compile(r"^#{2,6}[ \t]+", re.MULTILINE)
GID_LINE = re.compile(r"^<!-- gid:(\d{8}T\d{6}) -->$")
RELREF_SHORTCODE = re.compile(r"\{\{<\s*relref\b")
WIKIDOCS_LINK = re.compile(r"https://wikidocs\.net/(\d+)")
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


def user_script_chapters(text: str):
    """사용자 스크립트 CH 배열을 (page_id|None, subject) 목록으로 읽는다.

    `var CH=[...]` 선언 밖(주석·다른 코드)은 보지 않는다. 선언이 없으면 빈 목록이라
    audit 은 '챕터 목록 불일치' 오류로 잡는다.
    """
    declaration = USER_SCRIPT_CH_ARRAY.search(text)
    if not declaration:
        return []
    return [(None if raw == "null" else int(raw), subject)
            for raw, subject in USER_SCRIPT_CH_ITEM.findall(declaration.group(1))]


def chapter_key(path: str) -> str:
    """`pages/<key>/_chapter.md` 의 key(폴더명 또는 태그명)."""
    parts = path.split("/")
    return parts[1] if len(parts) > 2 else path


def user_script_findings(declared, expected_nav):
    """CH 배열 대조 결과를 (errors, warnings)로 돌려준다.

    - 챕터 목록/순서가 TOC 와 다르면 오류. 사이드바에 없는 챕터를 넣거나 빠뜨린다.
    - 선언한 page_id 가 mapping 과 다르면 오류. 독자가 죽은 링크를 본다.
    - mapping 이 아직 미회수(None)인데 page_id 를 선언했으면 오류. 회수 전에는 그 숫자의
      출처가 없다 — 재생성 전 옛 ID 이거나 임의값이고, 둘 다 엉뚱한 페이지로 보낸다.
    - 회수된 page_id 가 있는데 아직 null 이면 경고. DOM 폴백으로 돌긴 하지만
      제목 매칭에 기대는 상태라 회수한 값으로 고정하는 편이 낫다.
    """
    errors, warnings = [], []
    if [label for _, label in declared] != [label for _, label in expected_nav]:
        errors.append(
            f"{USER_SCRIPT_NAME}: 챕터 목록/순서가 TOC 와 다름: "
            f"{[label for _, label in declared]} != "
            f"{[label for _, label in expected_nav]}")
        return errors, warnings
    for (declared_id, label), (actual_id, _) in zip(declared, expected_nav):
        if declared_id is not None and actual_id is None:
            errors.append(
                f"{USER_SCRIPT_NAME}: '{label}' 은 mapping 에 회수된 page_id 가 없는데 "
                f"{declared_id} 를 선언했다(출처 없는 ID)")
        elif declared_id is not None and actual_id is not None \
                and declared_id != actual_id:
            errors.append(
                f"{USER_SCRIPT_NAME}: '{label}' page_id 불일치: "
                f"{declared_id} != {actual_id}")
        elif declared_id is None and actual_id is not None:
            warnings.append(
                f"{USER_SCRIPT_NAME}: '{label}' 은 회수된 page_id {actual_id} 가 "
                "있는데 아직 null(DOM 폴백). CH 갱신 권장")
    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--garden", default="~/repos/gh/notes")
    ap.add_argument("--out", default=None,
                    help="미러 리포 루트(기본: 이 스크립트로부터 위 README.md 있는 곳)")
    ap.add_argument("--allow-missing-page-ids", action="store_true")
    ap.add_argument("--core", action="store_true",
                    help="build --core 로 만든 발행면을 검증한다(TOC = 코어만).")
    ap.add_argument("--garden-links", action="store_true",
                    help="build --garden-links 로 만든 표지를 검증한다(링크 전부 가든).")
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
        (spec["subject"], spec["path"]) for spec in BUILD.COLLECTIONS.values()
    ] + [
        (BUILD.CHAPTER_NAMES.get(folder, folder), f"pages/{folder}/_chapter.md")
        for folder in folders
    ]
    actual_chapters = [(label, path) for label, path, _ in chapters]
    if actual_chapters != expected_chapters:
        errors.append(f"TOC: 챕터 순서/목록 불일치: {actual_chapters} != {expected_chapters}")

    child_paths = [path for _, path, _ in children]
    # TOC 에 등록된 것만 위키독스가 라이브로 두므로, 발행면과 링크 기준을 여기서 정한다.
    published = set(child_paths) | {path for _, path, _ in chapters}
    link_scope = set() if args.garden_links else published
    registered = len(child_paths) + len(chapters)
    if registered > BUILD.PUBLISH_LIMIT:
        errors.append(
            f"TOC: 발행 {registered}개 > 위키독스 상한 {BUILD.PUBLISH_LIMIT}개 "
            "(웹훅이 동기화를 통째로 거부한다)")

    # 코어 판정에 필요한 garden source 를 한 번만 읽어 집합면 검증과 공유한다.
    sources = {}
    for gid, value in pages_map.items():
        source_path = garden / "content" / value["folder"] / f"{gid}.md"
        if source_path.exists():
            sources[gid] = BUILD.read_source(source_path, value["folder"])

    def is_core(gid, value):
        source = sources.get(gid)
        return (source is not None and BUILD.CORE_TAG in source["tags"]) \
            or value.get("folder") in BUILD.CORE_FOLDERS

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
        expected_paths.extend(
            value["path"] for gid, value in folder_entries
            if not args.core or is_core(gid, value)
        )
        # 표지 목록은 발행 여부와 무관하게 폴더 전량을 싣는다. 달라지는 건 링크 대상뿐이다.
        cover_path = out / f"pages/{folder}/_chapter.md"
        expected_index = BUILD.chapter_index(
            folder, [(value["subject"], value) for _, value in folder_entries], link_scope
        )
        if not cover_path.exists() or cover_path.read_text(encoding="utf-8") != expected_index:
            errors.append(f"chapter index: {folder} recent-first 목록/링크 불일치")

    collection_counts = {}
    for tag, spec in BUILD.COLLECTIONS.items():
        tagged = [(source, pages_map[gid]) for gid, source in sources.items()
                  if tag in source["tags"]]
        tagged.sort(key=lambda item: BUILD.collection_sort_key(item[0]), reverse=True)
        collection_counts[tag] = len(tagged)
        expected_index = BUILD.collection_index(tag, [
            (BUILD.subject_for(BUILD.collection_sort_key(source)[0], source["title"]), value)
            for source, value in tagged
        ], link_scope)
        collection_path = out / spec["path"]
        if (not collection_path.exists() or
                collection_path.read_text(encoding="utf-8") != expected_index):
            errors.append(f"collection index: {tag} lastmod recent-first 목록/링크 불일치")

    expected_navigation = set(folders) | set(BUILD.COLLECTIONS)
    actual_navigation = set(mapping.get("_chapters", {}))
    if actual_navigation != expected_navigation:
        errors.append(
            f"mapping: navigation 표지 불일치: {sorted(actual_navigation)} != "
            f"{sorted(expected_navigation)}")
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

    # 발행면 밖 page_id 로 나가는 링크는 라이브에서 404 다(TOC 에서 빠지면 삭제되므로).
    # 우리 mapping 이 소유한 page_id 만 본다 — 저자가 인용한 외부 위키독스 링크는 대상이 아니다.
    owned_ids = {str(value["page_id"]): gid for gid, value in pages_map.items()
                 if value.get("page_id")}
    live_ids = {str(value["page_id"]) for gid, value in pages_map.items()
                if value.get("page_id") and value["path"] in published}
    live_ids |= {str(cover["page_id"]) for cover in mapping.get("_chapters", {}).values()
                 if cover.get("page_id")}
    dead_links = []
    for path in sorted(out.glob("pages/**/*.md")) + [out / "README.md"]:
        if not path.exists():
            continue
        for page_id in set(WIKIDOCS_LINK.findall(path.read_text(encoding="utf-8"))):
            if page_id in owned_ids and page_id not in live_ids:
                dead_links.append(f"{path.relative_to(out)}->{page_id}")
    if dead_links:
        errors.append(
            f"링크: 발행면 밖 page_id 참조 {len(dead_links)}개(라이브 404): {dead_links[:5]}")

    # 사이드바 스크립트는 웹훅이 아니라 손으로 위키독스에 붙여넣는다. 리포가 정본이므로
    # 여기서 어긋나면 독자는 죽은 챕터 링크를 보게 된다.
    script_path = out / USER_SCRIPT_NAME
    declared = []
    if not script_path.exists():
        # canonical 리포에는 항상 있다. 임시 --out 검증에서는 없는 게 정상이라 오류로는
        # 올리지 않되, 정본에서 사라진 것을 조용히 넘기지도 않는다.
        warnings.append(f"{USER_SCRIPT_NAME}: 없음 — 사이드바 챕터 대조를 건너뛴다")
    else:
        declared = user_script_chapters(script_path.read_text(encoding="utf-8"))
        navigation = mapping.get("_chapters", {})
        script_errors, script_warnings = user_script_findings(
            declared,
            [(navigation.get(chapter_key(path), {}).get("page_id"), label)
             for label, path, _ in chapters])
        errors.extend(script_errors)
        warnings.extend(script_warnings)

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
        # page_id 는 위키독스가 발행할 때 부여한다. 발행면 밖 페이지는 없는 게 정상이다.
        if not value.get("page_id") and value["path"] in published:
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
        # source URL 개수는 provenance block 안에서만 센다. 본문이 같은 노트를 가리키는
        # 저자 링크(문서 내 헤딩 참조 등)는 정상이고, relink 전에는 가든 URL 그대로다.
        if len(provenance) != 1 or \
                provenance[0].group(0).count(source["source_url"]) != 1:
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

    missing_navigation_ids = [
        key for key, value in mapping.get("_chapters", {}).items()
        if not value.get("page_id")
    ]
    if (missing_ids or missing_navigation_ids) and not args.allow_missing_page_ids:
        if missing_ids:
            errors.append(f"mapping: page_id 없는 항목 {len(missing_ids)}개: {missing_ids[:5]}")
        if missing_navigation_ids:
            errors.append(
                f"mapping: page_id 없는 표지 {len(missing_navigation_ids)}개: "
                f"{missing_navigation_ids[:5]}")
    elif missing_ids or missing_navigation_ids:
        if missing_ids:
            warnings.append(f"mapping: page_id 없는 항목 {len(missing_ids)}개")
        if missing_navigation_ids:
            warnings.append(f"mapping: page_id 없는 표지 {len(missing_navigation_ids)}개")
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
    collection_summary = ", ".join(
        f"{tag} {count}개" for tag, count in collection_counts.items()
    )
    print(f"[ok] chapters : folder recent-first {len(folders)}개, tag collection {collection_summary}")
    carried_ids = sum(1 for value in pages_map.values() if value.get("page_id"))
    published_pages = sum(1 for value in pages_map.values()
                          if value["path"] in published)
    print(f"[ok] mapping  : {len(pages_map)}개, page_id {carried_ids}개, "
          f"발행 {published_pages}개/{BUILD.PUBLISH_LIMIT}, uniqueness/completeness 보존")
    print(f"[ok] source   : garden metadata/title/provenance 전 페이지 일치 (abstract-first {abstract_pages}개)")
    if declared:
        pinned = sum(1 for page_id, _ in declared if page_id is not None)
        print(f"[ok] userjs   : {USER_SCRIPT_NAME} 챕터 {len(declared)}개 TOC 일치 "
              f"(page_id 고정 {pinned}, DOM 폴백 {len(declared) - pinned})")
    print("[ok] headings : 원본/미러 전 페이지 보존")
    print("[ok] relref   : 코드펜스 밖 미처리 0개")
    print("[ok] audit    : 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
