"""status.py 발행면 계약 회귀 테스트.

위키독스는 `TOC.md` 에 등록된 것만 라이브로 두고 나머지는 삭제한다(2026-07 실측).
그래서 동기화 진척의 분모는 로컬 전량이 아니라 TOC 등록분이고, 발행면 밖 페이지가
라이브에 없는 것은 오류가 아니라 정상이다. 라이브 API 는 가짜로 갈아 끼워 CLI 를
그대로 태운다.
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / ".claude/skills/garden-to-wikidocs/scripts/status.py"
SPEC = importlib.util.spec_from_file_location("garden_to_wikidocs_status", STATUS_PATH)
STATUS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATUS)

PUBLISHED_A = "20260101T000000"
PUBLISHED_B = "20260102T000000"
UNPUBLISHED = "20260103T000000"


def page_body(gid: str) -> str:
    return f"<!-- gid:{gid} -->\n본문 {gid}\n"


def collection_body(tag: str) -> str:
    return f"<!-- collection:{tag} -->\n집합 표지\n"


class StatusPublishSurfaceTests(unittest.TestCase):
    """TOC 등록분만 분모로 세고, 밖의 것은 미발행으로 분리한다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        (self.repo / "README.md").write_text("대문\n", encoding="utf-8")
        (self.repo / "pages/notes").mkdir(parents=True)
        (self.repo / "pages/autholog").mkdir(parents=True)

        for gid in (PUBLISHED_A, PUBLISHED_B, UNPUBLISHED):
            (self.repo / f"pages/notes/{gid}.md").write_text(
                page_body(gid), encoding="utf-8")
        # 폴더 표지는 TOC 최상위, 집합 표지는 미등록(코어 모드에서 발행면 밖).
        (self.repo / "pages/notes/_chapter.md").write_text("표지\n", encoding="utf-8")
        (self.repo / "pages/autholog/_chapter.md").write_text(
            collection_body("autholog"), encoding="utf-8")
        (self.repo / "TOC.md").write_text(
            "# 목차\n\n"
            "- [4 노트](pages/notes/_chapter.md)\n"
            f"  - [가](pages/notes/{PUBLISHED_A}.md)\n"
            f"  - [나](pages/notes/{PUBLISHED_B}.md)\n",
            encoding="utf-8",
        )

        self._real_api_get = STATUS.api_get
        self.addCleanup(setattr, STATUS, "api_get", self._real_api_get)

    def run_status(self, live_gids, *extra):
        """라이브 책을 가짜로 물리고 CLI 를 그대로 돌린다. (exit code, stdout)."""
        book = {"pages": [{
            "id": 1, "content": "표지",
            "children": [{"id": 100 + i, "content": page_body(gid)}
                         for i, gid in enumerate(live_gids)],
        }]}
        STATUS.api_get = lambda path, token: book
        argv = [str(STATUS_PATH), "--book-id", "20676",
                "--repo", str(self.repo), "--token", "fake", *extra]
        buffer = io.StringIO()
        original = sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(buffer):
                code = STATUS.main()
        finally:
            sys.argv = original
        return code, buffer.getvalue()

    def test_only_toc_registered_pages_count_toward_total(self):
        _, out = self.run_status([PUBLISHED_A, PUBLISHED_B])
        # 로컬 authored page 는 3개지만 발행면은 2개다.
        self.assertIn("반영 완료: 2/2", out)

    def test_pages_outside_toc_are_reported_as_unpublished_not_missing(self):
        _, out = self.run_status([PUBLISHED_A, PUBLISHED_B])
        # 미등록 authored page 1개 + 미등록 집합 표지 1개.
        self.assertIn("미발행   : 2개", out)
        self.assertIn("미생성   : 0개", out)

    def test_fully_synced_publish_surface_exits_zero(self):
        code, out = self.run_status([PUBLISHED_A, PUBLISHED_B])
        self.assertIn("미반영   : 0개", out)
        self.assertIn("미생성   : 0개", out)
        self.assertEqual(code, 0)

    def test_published_page_absent_from_live_is_missing_and_exits_one(self):
        code, out = self.run_status([PUBLISHED_A])
        self.assertIn("미생성   : 1개", out)
        self.assertIn("반영 완료: 1/2", out)
        self.assertEqual(code, 1)

    def test_published_page_with_stale_live_body_is_pending(self):
        book = {"pages": [{
            "id": 1, "content": "표지",
            "children": [
                {"id": 101, "content": page_body(PUBLISHED_A)},
                {"id": 102, "content": f"<!-- gid:{PUBLISHED_B} -->\n옛 본문\n"},
            ],
        }]}
        STATUS.api_get = lambda path, token: book
        argv = [str(STATUS_PATH), "--book-id", "20676",
                "--repo", str(self.repo), "--token", "fake"]
        buffer = io.StringIO()
        original = sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(buffer):
                code = STATUS.main()
        finally:
            sys.argv = original
        self.assertIn("미반영   : 1개", buffer.getvalue())
        self.assertEqual(code, 1)

    def test_json_summary_carries_unpublished_count(self):
        _, out = self.run_status([PUBLISHED_A, PUBLISHED_B], "--json")
        summary = json.loads(out)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["synced"], 2)
        self.assertEqual(summary["unpublished"], 2)
        self.assertEqual(summary["pending"], 0)
        self.assertEqual(summary["missing"], 0)

    def test_published_collection_cover_is_compared_not_skipped(self):
        (self.repo / "TOC.md").write_text(
            "# 목차\n\n"
            "- [0 어쏠로그](pages/autholog/_chapter.md)\n"
            "- [4 노트](pages/notes/_chapter.md)\n"
            f"  - [가](pages/notes/{PUBLISHED_A}.md)\n"
            f"  - [나](pages/notes/{PUBLISHED_B}.md)\n",
            encoding="utf-8",
        )
        # 표지를 TOC 에 올렸는데 라이브에 없으면 미생성이다.
        code, out = self.run_status([PUBLISHED_A, PUBLISHED_B])
        self.assertIn("미생성   : 1개", out)
        self.assertIn("미발행   : 1개", out)
        self.assertEqual(code, 1)


class StatusTocTargetTests(unittest.TestCase):
    """발행면 파싱은 TOC 링크 대상만 집는다."""

    def test_toc_target_matches_chapter_and_child_entries(self):
        toc = ("# 목차\n\n"
               "- [4 노트](pages/notes/_chapter.md)\n"
               "  - [제목 (괄호) 포함](pages/notes/20260101T000000.md)\n")
        self.assertEqual(
            STATUS.TOC_TARGET.findall(toc),
            ["pages/notes/_chapter.md", "pages/notes/20260101T000000.md"],
        )

    def test_toc_target_ignores_non_page_links(self):
        toc = "- [가든](https://notes.junghanacs.com/notes/20260101T000000/)\n"
        self.assertEqual(STATUS.TOC_TARGET.findall(toc), [])


if __name__ == "__main__":
    unittest.main()
