#!/usr/bin/env python3
"""3단계 파이프라인 3단계: 링크 실화(relink). stdlib only.

씨뿌리기(build.py) 단계에서 모든 내부 링크는 가든 절대 URL
    https://notes.junghanacs.com/<...>/<denote-id>/
로 심어졌다. 회수(recover.py) 후 mapping.json 에 page_id 가 채워지면, 이 스크립트가
page_id 가 있는 링크만 https://wikidocs.net/<page_id> 로 재작성한다.
mapping 에 없거나 page_id 가 아직 없는 링크는 가든 URL 그대로 둔다(하이브리드).

이렇게 하면 이미 올린 폴더 내부(및 폴더 간) 순회는 위키독스 안에서 살아나고,
아직 안 올린 폴더로의 링크는 가든으로 나간다. 폴더를 더 올릴수록 실화 비율이 오른다.

- 코드펜스 안 URL 은 건드리지 않는다(코드 예시는 literal 유지).
- 가든 URL 형태가 아닌 것(홈 `/`, `/index`, `/static/...`)은 denote-id 가 없어 자동 제외.
- 이미 wikidocs.net URL 인 링크는 가든 패턴에 안 걸리므로 반복 실행에 안전(idempotent).

사용:
    relink.py [--pages <repo>/pages] [--mapping <repo>/mapping.json] [--dry-run]
"""
import argparse
import json
import re
import sys
from pathlib import Path

WIKIDOCS_URL = "https://wikidocs.net"

# build.py 와 동일한 펜스 규칙: 줄 시작(들여쓰기 허용) 3+ backtick, 여는 개수 이상으로 닫기.
CODE_FENCE = re.compile(r"^[ \t]*(`{3,})[^\n]*\n.*?^[ \t]*\1`*[ \t]*$",
                        re.DOTALL | re.MULTILINE)
# 가든 내부 노트 링크: 경로 마지막 세그먼트가 denote-id. 홈/index/static 은 안 걸린다.
GARDEN_LINK = re.compile(
    r"https://notes\.junghanacs\.com/(?:[^()\s]*/)?(\d{8}T\d{6})/?")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=None,
                    help="pages 디렉토리(기본: 이 스크립트로부터 위 README.md 있는 곳/pages)")
    ap.add_argument("--mapping", default=None,
                    help="mapping.json 경로(기본: 리포 루트/mapping.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="파일을 쓰지 않고 실화될 링크 수만 보고")
    args = ap.parse_args()

    here = Path(__file__).resolve()
    root = next((p for p in here.parents if (p / "README.md").exists()), here.parents[3])
    pages_dir = Path(args.pages).expanduser() if args.pages else root / "pages"
    mapping_path = Path(args.mapping).expanduser() if args.mapping else root / "mapping.json"

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    page_id = {did: v["page_id"] for did, v in mapping.items() if v.get("page_id")}

    stats = {"reified": 0, "kept": 0, "files_changed": 0}

    def repl(m):
        did = m.group(1)
        pid = page_id.get(did)
        if pid:
            stats["reified"] += 1
            return f"{WIKIDOCS_URL}/{pid}"
        stats["kept"] += 1
        return m.group(0)

    md_files = sorted(pages_dir.rglob("*.md"))
    for f in md_files:
        text = f.read_text(encoding="utf-8")
        guarded, blocks = protect_code(text)
        before = stats["reified"]
        new = GARDEN_LINK.sub(repl, guarded)
        new = restore_code(new, blocks)
        if new != text:
            stats["files_changed"] += 1
            if not args.dry_run:
                f.write_text(new, encoding="utf-8")

    mode = "dry-run(미기록)" if args.dry_run else "기록완료"
    print(f"[ok] pages     : {pages_dir} ({len(md_files)}개 파일)")
    print(f"[ok] mapping   : {mapping_path} (page_id {len(page_id)}개)")
    print(f"[ok] 실화       : {stats['reified']}개 링크 -> wikidocs.net/<id> [{mode}]")
    print(f"[ok] 가든 유지  : {stats['kept']}개 링크 (아직 안 올린 폴더/매핑 없음)")
    print(f"[ok] 바뀐 파일 : {stats['files_changed']}개")


if __name__ == "__main__":
    sys.exit(main())
