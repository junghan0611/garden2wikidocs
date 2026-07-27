"""relink.py 발행면 게이트 회귀 테스트.

위키독스는 `TOC.md` 에 등록된 것만 라이브로 두고 나머지는 삭제한다(2026-07 실측).
그래서 실화는 두 방향 모두 발행면에 묶인다.

- 링크 대상: TOC 밖 page_id 로는 절대 잇지 않는다(라이브 404).
- 실화 파일: TOC 밖 페이지는 라이브에 없으므로 아예 고치지 않는다. 고치면 발행면이
  바뀔 때마다 리포 전체가 흔들리는데, 정작 그 링크는 아무도 볼 수 없다.

책 대문(README.md)은 TOC 밖이지만 항상 라이브이므로 유일한 예외다.
`--repo` 로 fixture 를 물려 CLI 를 그대로 태운다.
"""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELINK_PATH = ROOT / ".claude/skills/garden-to-wikidocs/scripts/relink.py"
SPEC = importlib.util.spec_from_file_location("garden_to_wikidocs_relink", RELINK_PATH)
RELINK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELINK)

GARDEN = "https://notes.junghanacs.com"
PUBLISHED = "20260101T000000"
UNPUBLISHED = "20260103T000000"


def garden_link(gid: str) -> str:
    return f"[다른 노트]({GARDEN}/notes/{gid}/)\n"


class RelinkTargetSelectionTests(unittest.TestCase):
    """실화할 파일 목록 자체가 발행면이다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pages = Path(self._tmp.name) / "pages"
        (self.pages / "notes").mkdir(parents=True)
        for gid in (PUBLISHED, UNPUBLISHED):
            (self.pages / f"notes/{gid}.md").write_text("본문\n", encoding="utf-8")
        (self.pages / "notes/_chapter.md").write_text("표지\n", encoding="utf-8")

    def test_unpublished_pages_are_skipped(self):
        published = {"pages/notes/_chapter.md", f"pages/notes/{PUBLISHED}.md"}
        live, skipped = RELINK.relink_targets(self.pages, published)
        self.assertEqual(
            sorted(RELINK.toc_path_of(path, self.pages) for path in live),
            sorted(published))
        self.assertEqual([RELINK.toc_path_of(path, self.pages) for path in skipped],
                         [f"pages/notes/{UNPUBLISHED}.md"])

    def test_unknown_publish_surface_refuses_instead_of_relinking_everything(self):
        # fail-open 이면 TOC 유실/잘못된 --repo 가 리포 전량을 흔든다. 멈추는 게 맞다.
        with self.assertRaises(ValueError):
            RELINK.relink_targets(self.pages, None)

    def test_toc_path_uses_build_convention_regardless_of_pages_location(self):
        # --pages 로 리포 밖을 물려도 TOC 표기(`pages/<folder>/<name>.md`)로 맞춘다.
        self.assertEqual(
            RELINK.toc_path_of(self.pages / f"notes/{PUBLISHED}.md", self.pages),
            f"pages/notes/{PUBLISHED}.md")


class RelinkCliPublishSurfaceTests(unittest.TestCase):
    """CLI 를 그대로 태워 게이트가 실제 배선에 걸려 있는지 본다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        (self.repo / "pages/notes").mkdir(parents=True)

        # 두 페이지 모두 '발행된 노트'를 가리키는 같은 가든 링크를 갖는다.
        # 달라지는 건 그 링크를 담은 파일이 발행면 안이냐 밖이냐뿐이다.
        self.live_page = self.repo / f"pages/notes/{PUBLISHED}.md"
        self.dead_page = self.repo / f"pages/notes/{UNPUBLISHED}.md"
        self.live_page.write_text(garden_link(PUBLISHED), encoding="utf-8")
        self.dead_page.write_text(garden_link(PUBLISHED), encoding="utf-8")
        (self.repo / "pages/notes/_chapter.md").write_text(
            garden_link(UNPUBLISHED), encoding="utf-8")
        (self.repo / "README.md").write_text(garden_link(PUBLISHED), encoding="utf-8")
        (self.repo / "TOC.md").write_text(
            "# 목차\n\n"
            "- [4 노트](pages/notes/_chapter.md)\n"
            f"  - [가](pages/notes/{PUBLISHED}.md)\n",
            encoding="utf-8")
        (self.repo / "mapping.json").write_text(json.dumps({
            PUBLISHED: {"path": f"pages/notes/{PUBLISHED}.md", "page_id": 111,
                        "url": "https://wikidocs.net/111"},
            UNPUBLISHED: {"path": f"pages/notes/{UNPUBLISHED}.md", "page_id": 222,
                          "url": "https://wikidocs.net/222"},
            "_chapters": {"notes": {"page_id": 333,
                                    "url": "https://wikidocs.net/333"}},
        }, ensure_ascii=False), encoding="utf-8")

    def run_relink(self, *extra):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            RELINK.main(["--repo", str(self.repo), *extra])
        return buffer.getvalue()

    def test_published_page_gets_wikidocs_link(self):
        self.run_relink()
        self.assertIn("https://wikidocs.net/111", self.live_page.read_text())

    def test_unpublished_page_is_left_on_garden(self):
        self.run_relink()
        # 대상(111)은 발행면 안이지만, 이 링크를 담은 파일이 라이브에 없으므로 손대지 않는다.
        self.assertEqual(self.dead_page.read_text(), garden_link(PUBLISHED))

    def test_readme_is_relinked_even_though_it_is_outside_toc(self):
        self.run_relink()
        self.assertIn("https://wikidocs.net/111", (self.repo / "README.md").read_text())

    def test_unpublished_target_stays_on_garden_inside_published_page(self):
        self.run_relink()
        # 표지는 발행면 안이지만 가리키는 노트가 TOC 밖이므로 가든에 남는다.
        self.assertEqual((self.repo / "pages/notes/_chapter.md").read_text(),
                         garden_link(UNPUBLISHED))

    def test_report_separates_publish_surface_cover_and_skipped(self):
        output = self.run_relink("--dry-run")
        # 발행면 2 = 표지 + 발행 노트. 대문은 TOC 밖이므로 발행면에 합산하지 않는다.
        self.assertIn("대상 3개 = 발행면 2 + 대문 1", output)
        self.assertIn("발행면 밖 1개 건너뜀", output)

    def test_dry_run_writes_nothing(self):
        self.run_relink("--dry-run")
        self.assertEqual(self.live_page.read_text(), garden_link(PUBLISHED))

    def test_relink_is_idempotent(self):
        self.run_relink()
        first = self.live_page.read_text()
        self.run_relink()
        self.assertEqual(self.live_page.read_text(), first)

    def test_missing_toc_exits_nonzero_and_writes_nothing(self):
        (self.repo / "TOC.md").unlink()
        before = self.live_page.read_text()
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            status = RELINK.main(["--repo", str(self.repo)])
        self.assertEqual(status, 1)
        self.assertIn("TOC.md 없음", buffer.getvalue())
        self.assertEqual(self.live_page.read_text(), before)


if __name__ == "__main__":
    unittest.main()
