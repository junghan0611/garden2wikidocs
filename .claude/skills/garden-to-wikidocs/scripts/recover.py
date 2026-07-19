#!/usr/bin/env python3
"""3단계 파이프라인 2단계: 회수(recover). stdlib only.

씨뿌리기(build.py) push 후, 위키독스가 부여한 page_id 를 회수한다.
각 페이지 본문에 심어둔 `<!-- gid:<denote-id> -->` 앵커를 book get 응답에서 읽어
mapping.json 의 denote-id 항목에 page_id 와 위키독스 URL 을 채운다. 태그 집합 표지는
`<!-- collection:<tag> -->` 앵커로 `_chapters` navigation ledger에 회수한다.

사용:
    WIKIDOCS_TOKEN=... recover.py --book-id 20676 [--mapping <repo>/mapping.json]

인증: --token 우선, 없으면 환경변수 WIKIDOCS_TOKEN.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

API = "https://wikidocs.net/napi"
GID = re.compile(r"<!-- gid:(\d{8}T\d{6}) -->")
COLLECTION = re.compile(r"<!-- collection:([a-z0-9]+) -->")


def api_get(path, token):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def walk(node, acc):
    acc.append(node)
    for c in node.get("children", []):
        walk(c, acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-id", required=True)
    ap.add_argument("--mapping", default=None,
                    help="mapping.json 경로(기본: 이 스크립트로부터 위 README.md 있는 곳/mapping.json)")
    ap.add_argument("--token", default=None)
    args = ap.parse_args()

    token = args.token or os.environ.get("WIKIDOCS_TOKEN")
    if not token:
        print("[err] 토큰 없음: --token 또는 WIKIDOCS_TOKEN", file=sys.stderr)
        return 1

    if args.mapping:
        mapping_path = Path(args.mapping).expanduser()
    else:
        here = Path(__file__).resolve()
        root = next((p for p in here.parents if (p / "README.md").exists()), here.parents[3])
        mapping_path = root / "mapping.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))

    book = api_get(f"/books/{args.book_id}/", token)
    nodes = []
    for p in book.get("pages", []):
        walk(p, nodes)

    matched = 0
    fetched = 0
    resolved_content = {}
    for n in nodes:
        content = n.get("content") or ""
        if not content:                       # book get 이 content 를 안 주면 개별 조회
            content = api_get(f"/pages/{n['id']}/", token).get("content", "")
            fetched += 1
        resolved_content[n["id"]] = content
        m = GID.search(content)
        if m and m.group(1) in mapping:
            gid = m.group(1)
            mapping[gid]["page_id"] = n["id"]
            mapping[gid]["url"] = f"https://wikidocs.net/{n['id']}"
            matched += 1

    # 챕터 표지(폴더) page_id 회수: 최상위 노드 = 챕터. 자식의 gid 로 폴더를 판별한다.
    # (챕터 표지 자체엔 gid 앵커가 없으므로 자식 노트의 folder 로 역추적)
    chapters = dict(mapping.get("_chapters", {}))
    recovered_collections = []
    for top in book.get("pages", []):
        top_content = resolved_content.get(top["id"], top.get("content") or "")
        collection_match = COLLECTION.search(top_content)
        if collection_match and collection_match.group(1) in chapters:
            tag = collection_match.group(1)
            chapters[tag].update({
                "page_id": top["id"], "subject": top.get("subject"),
                "url": f"https://wikidocs.net/{top['id']}",
            })
            recovered_collections.append(tag)
            continue

        folder = None
        for c in top.get("children", []):
            cm = GID.search(resolved_content.get(c["id"], c.get("content") or ""))
            if cm and cm.group(1) in mapping and mapping[cm.group(1)].get("folder"):
                folder = mapping[cm.group(1)]["folder"]
                break
        if folder:
            previous = chapters.get(folder, {})
            chapters[folder] = {
                **previous, "page_id": top["id"], "subject": top.get("subject"),
                "url": f"https://wikidocs.net/{top['id']}",
            }
    if chapters:
        mapping["_chapters"] = chapters

    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    pages_map = {g: v for g, v in mapping.items() if g != "_chapters"}
    total = len(pages_map)
    unmatched = [g for g, v in pages_map.items() if not v.get("page_id")]
    print(f"[ok] book_id  : {args.book_id}")
    print(f"[ok] 위키독스 페이지 노드: {len(nodes)}개 (개별조회 {fetched})")
    print(f"[ok] 회수 매칭 : {matched}/{total}")
    print(f"[ok] 챕터 표지 : {len(chapters)}개 {sorted(chapters)}")
    print(f"[ok] 태그 집합 : {len(recovered_collections)}개 {sorted(recovered_collections)}")
    if unmatched:
        print(f"[warn] page_id 없는 항목 {len(unmatched)}개: {unmatched[:5]}{'...' if len(unmatched)>5 else ''}")
    print(f"[ok] mapping  : {mapping_path}")


if __name__ == "__main__":
    sys.exit(main())
