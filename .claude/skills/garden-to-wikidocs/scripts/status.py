#!/usr/bin/env python3
"""3단계 파이프라인 부가: 동기화 상태(status). stdlib only.

push 하면 웹훅이 위키독스를 갱신하는데, 대량(2천여 페이지)이면 한 번에 다 안 돌고
서버측에서 나눠 처리되거나 중간에 멈춰 수동 재동기화가 필요할 수 있다. 이 스크립트는
`book get` 으로 라이브 본문을 받아 로컬 `pages/**/*.md` 와 대조해 "몇 개가 반영됐는지"를
잰다. 커밋 범위에 묶이지 않는다 — 언제 돌려도 현재 라이브 vs 현재 리포 상태를 비교한다.

  synced  : 라이브 본문 == 로컬(이미지 URL 중립화 후) → 반영 완료
  pending : gid 는 있으나 본문이 옛 버전 → 아직 미반영(또는 재동기화 필요)
  missing : 로컬에 있는 gid 가 라이브에 없음 → 페이지 미생성(recover/재동기화 필요)

불변식: 위키독스는 인제스트 때 이미지를 자기 CDN(static.wikidocs.net)으로 올리고
`![](../../assets/x.png)` → `![](https://static.wikidocs.net/…)` 로 URL 을 재작성한다.
텍스트·줄수는 보존되므로 이미지 URL 만 `![](IMG)` 로 중립화해 대조한다(이미지 존재/개수/
위치는 유지 → 텍스트 변경은 여전히 잡힘). 실측으로 확인된 유일한 변환이다.

사용:
    WIKIDOCS_TOKEN=... status.py --book-id 20676 [--list] [--json]
    # 반영 완료면 exit 0, 미반영/누락 있으면 exit 1 → 대기 루프에 그대로 쓸 수 있다.

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
GID_COMMENT = re.compile(r"<!-- gid:(\d{8}T\d{6}) -->")
GID_NAME = re.compile(r"(\d{8}T\d{6})")
IMG = re.compile(r"!\[([^\]]*)\]\([^)]*\)")


def norm(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = IMG.sub(r"![\1](IMG)", s)      # 이미지 URL 중립화 (위키독스 CDN 재작성 흡수)
    return s.rstrip()


def api_get(path, token):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def walk(node, acc):
    acc.append(node)
    for c in node.get("children", []):
        walk(c, acc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-id", default="20676")
    ap.add_argument("--repo", default=None, help="리포 루트(기본: 이 스크립트 기준 README.md 있는 곳)")
    ap.add_argument("--token", default=None)
    ap.add_argument("--list", action="store_true", help="pending/missing gid 목록 출력")
    ap.add_argument("--json", action="store_true", help="요약을 JSON 한 줄로 출력")
    args = ap.parse_args()

    token = args.token or os.environ.get("WIKIDOCS_TOKEN")
    if not token:
        print("[err] 토큰 없음: --token 또는 WIKIDOCS_TOKEN", file=sys.stderr)
        return 2

    if args.repo:
        root = Path(args.repo).expanduser()
    else:
        here = Path(__file__).resolve()
        root = next((p for p in here.parents if (p / "README.md").exists()), here.parents[3])

    # 라이브 책 → gid -> content
    book = api_get(f"/books/{args.book_id}/", token)
    nodes = []
    for p in book.get("pages", []):
        walk(p, nodes)
    live = {}
    for n in nodes:
        m = GID_COMMENT.search(n.get("content") or "")
        if m:
            live[m.group(1)] = n.get("content") or ""

    # 로컬 페이지 대조
    synced, pending, missing = [], [], []
    for path in sorted(root.glob("pages/**/*.md")):
        if path.name.endswith("_chapter.md"):
            continue
        m = GID_NAME.search(path.name)
        if not m:
            continue
        gid = m.group(1)
        folder = path.relative_to(root / "pages").parts[0]
        rec = (gid, folder)
        if gid not in live:
            missing.append(rec)
        elif norm(live[gid]) == norm(path.read_text(encoding="utf-8")):
            synced.append(rec)
        else:
            pending.append(rec)

    total = len(synced) + len(pending) + len(missing)
    pct = (len(synced) / total * 100) if total else 0.0

    if args.json:
        print(json.dumps({
            "book_id": args.book_id, "total": total, "synced": len(synced),
            "pending": len(pending), "missing": len(missing), "pct": round(pct, 1),
            "live_nodes": len(nodes),
        }, ensure_ascii=False))
    else:
        print(f"[status] book_id  : {args.book_id}  (라이브 노드 {len(nodes)}개)")
        print(f"[status] 반영 완료: {len(synced)}/{total}  ({pct:.1f}%)")
        print(f"[status] 미반영   : {len(pending)}개")
        print(f"[status] 미생성   : {len(missing)}개")

    if args.list:
        def by_folder(recs):
            d = {}
            for g, f in recs:
                d.setdefault(f, []).append(g)
            return d
        if pending:
            print("[pending] " + "  ".join(f"{f}:{len(v)}" for f, v in sorted(by_folder(pending).items())))
            for f, v in sorted(by_folder(pending).items()):
                print(f"  {f}: {v}")
        if missing:
            print("[missing] " + "  ".join(f"{f}:{len(v)}" for f, v in sorted(by_folder(missing).items())))
            for f, v in sorted(by_folder(missing).items()):
                print(f"  {f}: {v}")

    return 0 if (not pending and not missing) else 1


if __name__ == "__main__":
    sys.exit(main())
