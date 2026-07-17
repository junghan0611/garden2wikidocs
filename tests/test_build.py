import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / ".claude/skills/garden-to-wikidocs/scripts/build.py"
AUDIT_PATH = ROOT / ".claude/skills/garden-to-wikidocs/scripts/audit.py"
SPEC = importlib.util.spec_from_file_location("garden_to_wikidocs_build", BUILD_PATH)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class TitleTests(unittest.TestCase):
    def test_toc_title_removes_notetaking_unicode_and_markdown_brackets(self):
        raw = "앞\u00a0—§¶†‡№↔←→⊢⊨∉©¬¤µ¡¿◊⁂¥¢£[가운데]뒤"
        title = BUILD.clean_toc_title(raw)

        for char in BUILD.TOC_UNSAFE_CHARS:
            self.assertNotIn(char, title)
        self.assertEqual(title, "앞 가운데 뒤")

    def test_subject_keeps_date_prefix_after_title_cleanup(self):
        self.assertEqual(
            BUILD.subject_for("20240215T071858", "№332 №192 모음"),
            "20240215 332 192 모음",
        )

    def test_folders_have_canonical_order_and_no_duplicates(self):
        self.assertEqual(
            BUILD.ordered_folders(["notes", "bib", "journal", "notes", "botlog", "meta"]),
            ["journal", "meta", "bib", "notes", "botlog"],
        )


class RelrefTests(unittest.TestCase):
    def transform(self, body):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            return BUILD.transform_body(body, root, root / "assets", "../../", [])

    def test_plain_brackets_do_not_consume_later_relref_or_newlines(self):
        body = (
            "> [!abstract] 소개\n"
            "> 본문\n\n"
            "[일반 대괄호]\n\n"
            "## 표 제목\n\n"
            "| 열1 | 열2 |\n"
            "|---|---|\n"
            "| 값1 | 값2 |\n\n"
            "[정상 링크]({{< relref \"/bib/20260407T111455.md\" >}})\n"
        )
        transformed = self.transform(body)

        self.assertIn("[일반 대괄호]\n\n## 표 제목", transformed)
        self.assertIn("| 열1 | 열2 |\n|---|---|\n| 값1 | 값2 |", transformed)
        self.assertIn(
            "[정상 링크](https://notes.junghanacs.com/bib/20260407T111455/)",
            transformed,
        )
        self.assertGreaterEqual(transformed.count("\n"), 10)

    def test_nested_closing_bracket_in_link_text_is_supported(self):
        body = '[바깥 [안쪽]]({{< relref "/notes/20250724T091841.md" >}})\n'
        self.assertEqual(
            self.transform(body),
            "[바깥 [안쪽]](https://notes.junghanacs.com/notes/20250724T091841/)\n",
        )

    def test_code_fence_relref_stays_literal(self):
        body = '```markdown\n[예시]({{< relref "/notes/20250724T091841.md" >}})\n```\n'
        self.assertEqual(self.transform(body), body)

    def test_malformed_relative_relref_in_link_text_becomes_plain_text(self):
        body = '[{{< relref "architecture" >}}]({{< relref "architecture" >}})\n'
        self.assertEqual(self.transform(body), "architecture\n")


class BuildIntegrationTests(unittest.TestCase):
    def test_build_orders_toc_sanitizes_titles_and_carries_remote_ids(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            garden = base / "garden"
            out = base / "out"
            (garden / "content").mkdir(parents=True)
            out.mkdir()
            (out / "README.md").write_text("placeholder\n", encoding="utf-8")

            fixtures = {
                "journal": ("20240101T000000", "§저널 — 시작"),
                "bib": ("20240215T071858", "№332 [참고문헌]"),
                "notes": ("20240301T000000", "◊노트 → 연결"),
            }
            previous = {}
            for page_id, (folder, (did, title)) in enumerate(fixtures.items(), start=101):
                source_dir = garden / "content" / folder
                source_dir.mkdir()
                (source_dir / f"{did}.md").write_text(
                    f'---\ntitle: "{title}"\n---\n\n본문\n', encoding="utf-8"
                )
                previous[did] = {
                    "path": f"pages/{folder}/{did}.md",
                    "subject": "stale",
                    "folder": folder,
                    "page_id": page_id,
                    "url": f"https://wikidocs.net/{page_id}",
                }
            previous["_chapters"] = {
                folder: {
                    "page_id": page_id,
                    "subject": "stale",
                    "url": f"https://wikidocs.net/{page_id}",
                }
                for page_id, folder in enumerate(fixtures, start=201)
            }
            (out / "mapping.json").write_text(
                json.dumps(previous, ensure_ascii=False), encoding="utf-8"
            )
            (garden / "content/index.md").write_text(
                '---\ntitle: "§가든 — 대문"\n---\n\n대문\n', encoding="utf-8"
            )

            subprocess.run(
                [
                    sys.executable,
                    str(BUILD_PATH),
                    "--folders",
                    "notes,bib,journal",
                    "--garden",
                    str(garden),
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            toc = (out / "TOC.md").read_text(encoding="utf-8")
            chapter_lines = [line for line in toc.splitlines() if line.startswith("- [")]
            self.assertEqual(
                chapter_lines,
                [
                    "- [1 저널](pages/journal/_chapter.md)",
                    "- [3 참고문헌](pages/bib/_chapter.md)",
                    "- [4 노트](pages/notes/_chapter.md)",
                ],
            )
            self.assertIn(
                "  - [20240101 저널 시작](pages/journal/20240101T000000.md)", toc
            )
            self.assertIn(
                "  - [20240215 332 참고문헌](pages/bib/20240215T071858.md)", toc
            )
            self.assertIn(
                "  - [20240301 노트 연결](pages/notes/20240301T000000.md)", toc
            )

            mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
            for page_id, (_, (did, _)) in enumerate(fixtures.items(), start=101):
                self.assertEqual(mapping[did]["page_id"], page_id)
            self.assertEqual(mapping["_chapters"]["bib"]["subject"], "3 참고문헌")
            self.assertEqual((out / "README.md").read_text(encoding="utf-8").splitlines()[0],
                             "# 가든 대문")

            audit = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_PATH),
                    "--garden",
                    str(garden),
                    "--out",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("[ok] audit    : 통과", audit.stdout)


if __name__ == "__main__":
    unittest.main()
