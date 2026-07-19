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
RELINK_PATH = ROOT / ".claude/skills/garden-to-wikidocs/scripts/relink.py"
SPEC = importlib.util.spec_from_file_location("garden_to_wikidocs_build", BUILD_PATH)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
RELINK_SPEC = importlib.util.spec_from_file_location("garden_to_wikidocs_relink", RELINK_PATH)
RELINK = importlib.util.module_from_spec(RELINK_SPEC)
RELINK_SPEC.loader.exec_module(RELINK)


def init_git_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.com"], cwd=path,
                   check=True)
    subprocess.run(["git", "add", "content", "change-text.sh"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=path, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


class TitleTests(unittest.TestCase):
    def test_toc_title_removes_notetaking_unicode_and_markdown_brackets(self):
        raw = "앞\u00a0—§¶†‡№↔←→⊢⊨∉©¬¤µ¡¿◊⁂¥¢£[가운데]뒤"
        title = BUILD.clean_toc_title(raw)

        for char in BUILD.TOC_UNSAFE_CHARS:
            self.assertNotIn(char, title)
        self.assertEqual(title, "앞 가운데 뒤")

    def test_subject_keeps_date_prefix_after_title_cleanup(self):
        self.assertEqual(
            BUILD.subject_for("2025-06-07T12:34:56+09:00", "№332 №192 모음"),
            "20250607 332 192 모음",
        )

    def test_title_date_matches_garden_folder_listing_policy(self):
        self.assertEqual(
            BUILD.source_title_date({
                "folder": "notes",
                "date": "2024-02-15T07:18:58+09:00",
                "lastmod": "2025-06-07T12:34:56+09:00",
            }),
            "20250607",
        )
        self.assertEqual(
            BUILD.source_title_date({
                "folder": "notes",
                "date": "2024-02-15T07:18:58+09:00",
            }),
            "20240215",
        )
        self.assertEqual(
            BUILD.source_title_date({
                "folder": "journal",
                "date": "2024-02-15T07:18:58+09:00",
                "lastmod": "2025-06-07T12:34:56+09:00",
            }),
            "20240215",
        )

    def test_source_sort_key_is_newest_first_with_denote_id_tiebreak(self):
        sources = [
            {"id": "20240101T000000", "folder": "notes",
             "date": "2024-01-01T00:00:00+09:00", "lastmod": "2025-01-01T00:00:00+09:00"},
            {"id": "20240201T000000", "folder": "notes",
             "date": "2024-02-01T00:00:00+09:00", "lastmod": "2026-01-01T00:00:00+09:00"},
            {"id": "20240301T000000", "folder": "notes",
             "date": "2024-03-01T00:00:00+09:00", "lastmod": "2026-01-01T00:00:00+09:00"},
        ]
        sources.sort(key=BUILD.source_sort_key, reverse=True)
        self.assertEqual(
            [source["id"] for source in sources],
            ["20240301T000000", "20240201T000000", "20240101T000000"],
        )

    def test_frontmatter_preserves_quoted_scalars_and_timestamps(self):
        source = (
            '---\n'
            'title: "§OCR 여정 \'모델/도구\'"\n'
            'description: "설명: 내부 콜론과 \'인용\'을 보존"\n'
            'date: 2026-02-20T20:11:00+09:00\n'
            'lastmod: 2026-07-17T20:43:00+09:00\n'
            '---\n본문\n'
        )
        meta, body = BUILD.split_frontmatter(source)
        self.assertEqual(meta["title"], "§OCR 여정 '모델/도구'")
        self.assertEqual(meta["description"], "설명: 내부 콜론과 '인용'을 보존")
        self.assertEqual(meta["date"], "2026-02-20T20:11:00+09:00")
        self.assertEqual(meta["lastmod"], "2026-07-17T20:43:00+09:00")
        self.assertEqual(body, "본문\n")

    def test_balanced_inner_single_quotes_are_preserved(self):
        frontmatter = '---\ntitle: "§OCR 여정 \'모델/도구\'"\n---\n본문\n'
        meta, _ = BUILD.split_frontmatter(frontmatter)
        self.assertEqual(meta["title"], "§OCR 여정 '모델/도구'")
        self.assertEqual(BUILD.clean_toc_title(meta["title"]), "OCR 여정 '모델/도구'")

    def test_only_matching_outer_quotes_are_removed(self):
        self.assertEqual(BUILD.strip_wrapping_quotes("'바깥'"), "바깥")
        self.assertEqual(BUILD.strip_wrapping_quotes("안쪽'"), "안쪽'")

    def test_folders_have_canonical_order_and_no_duplicates(self):
        self.assertEqual(
            BUILD.ordered_folders(["notes", "bib", "journal", "notes", "botlog", "meta"]),
            ["journal", "meta", "bib", "notes", "botlog"],
        )

    def test_tags_are_read_as_string_array(self):
        self.assertEqual(
            BUILD.parse_tags('["autholog", "digitalgarden"]'),
            ["autholog", "digitalgarden"],
        )
        with self.assertRaises(ValueError):
            BUILD.parse_tags('"autholog"')


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

    def test_citeproc_entries_become_markdown_list_items(self):
        body = (
            "## BIBLIOGRAPHY\n\n"
            '<div class="csl-bib-body">\n'
            '  <div class="csl-entry"><a id="citeproc_bib_item_1"></a>첫 항목. '
            '<a href="https://example.com/1">링크 1</a>.</div>\n'
            '  <div class="csl-entry"><a id="citeproc_bib_item_2"></a>둘째 항목. '
            '<a href="https://example.com/2">링크 2</a>.</div>\n'
            "</div>\n"
        )
        transformed = self.transform(body)
        self.assertIn("- 첫 항목. [링크 1](https://example.com/1).", transformed)
        self.assertIn("- 둘째 항목. [링크 2](https://example.com/2).", transformed)
        self.assertNotIn('class="csl-entry"', transformed)

    def test_citeproc_markup_in_code_fence_stays_literal(self):
        body = '```html\n<div class="csl-entry">예시</div>\n```\n'
        self.assertEqual(self.transform(body), body)


class ProvenanceTests(unittest.TestCase):
    SOURCE = {
        "source_url": "https://notes.junghanacs.com/notes/20240215T071858/",
        "date": "2024-02-15T07:18:58+09:00",
        "lastmod": "2025-06-07T12:34:56+09:00",
    }

    def test_abstract_is_moved_before_provenance_and_toc(self):
        raw = (
            "작성자의 앞선 메모\n\n"
            "> [!abstract] 이 노트에 대하여\n"
            "> \n"
            "> 서로 다른 검색 snippet을 위한 저자 요약.\n\n"
            "## 본문\n"
        )
        abstract, body = BUILD.extract_author_abstract(raw)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            converted_abstract = BUILD.transform_body(
                abstract, root, root / "assets", "../../", []
            )
            converted_body = BUILD.transform_body(
                body, root, root / "assets", "../../", []
            )
        page = BUILD.compose_page(converted_abstract, converted_body, self.SOURCE, True)
        self.assertLess(page.index("이 노트에 대하여"), page.index(BUILD.PROVENANCE_START))
        self.assertLess(page.index(BUILD.PROVENANCE_END), page.index("[TOC]"))
        self.assertLess(page.index("[TOC]"), page.index("작성자의 앞선 메모"))
        self.assertEqual(page.count(self.SOURCE["source_url"]), 1)
        self.assertNotIn(BUILD.PROVENANCE_START,
                         page[:page.index('[[/TIP]]')])

    def test_no_abstract_starts_with_provenance(self):
        page = BUILD.compose_page("", "본문\n", self.SOURCE, False)
        self.assertTrue(page.startswith(BUILD.PROVENANCE_START))

    def test_relink_preserves_provenance_source_url(self):
        page = (
            BUILD.provenance_block(self.SOURCE) + "\n\n"
            "[다른 노트](https://notes.junghanacs.com/meta/20240101T010101/)\n"
        )
        guarded, blocks = RELINK.protect_provenance(page)
        rewritten = RELINK.GARDEN_LINK.sub(
            lambda match: f"https://wikidocs.net/{999 if match.group(1) else 0}", guarded
        )
        rewritten = RELINK.restore_provenance(rewritten, blocks)
        self.assertIn(self.SOURCE["source_url"], rewritten)
        self.assertIn("https://wikidocs.net/999", rewritten)
        self.assertEqual(rewritten.count(self.SOURCE["source_url"]), 1)

    def test_collection_index_uses_lastmod_order_and_preserves_source_route(self):
        sources = [
            {"id": "20240101T000000", "date": "2024-01-01T00:00:00+09:00",
             "lastmod": "2026-07-17T09:00:00+09:00"},
            {"id": "20240201T000000", "date": "2024-02-01T00:00:00+09:00",
             "lastmod": "2026-07-18T09:00:00+09:00"},
        ]
        sources.sort(key=BUILD.collection_sort_key, reverse=True)
        entries = [
            (f"{source['id']} 제목", {
                "url": f"https://wikidocs.net/{index}",
                "source_url": f"https://notes.junghanacs.com/notes/{source['id']}/",
            })
            for index, source in enumerate(sources, start=1)
        ]
        index = BUILD.collection_index("autholog", entries)
        self.assertLess(index.index("20240201T000000"), index.index("20240101T000000"))
        self.assertIn("`autholog` 태그 문서 2개", index)
        self.assertIn("https://notes.junghanacs.com/tags/autholog/", index)
        self.assertEqual(index.count(BUILD.COLLECTION_INDEX_START), 1)

    def test_relink_rewrites_autholog_tag_but_preserves_collection_provenance(self):
        source_url = "https://notes.junghanacs.com/tags/autholog/"
        text = (
            f"{BUILD.PROVENANCE_START}\n[원본]({source_url})\n{BUILD.PROVENANCE_END}\n"
            f"[집합]({source_url})\n"
        )
        guarded, blocks = RELINK.protect_provenance(text)
        rewritten = RELINK.COLLECTION_LINK.sub(
            lambda _: "https://wikidocs.net/999", guarded
        )
        rewritten = RELINK.restore_provenance(rewritten, blocks)
        self.assertEqual(rewritten.count(source_url), 1)
        self.assertIn("[집합](https://wikidocs.net/999)", rewritten)

    def test_chapter_index_uses_given_recent_first_order_and_stable_urls(self):
        entries = [
            ("20260718 최신", {
                "url": "https://wikidocs.net/2",
                "source_url": "https://notes.junghanacs.com/notes/20260718T000000/",
            }),
            ("20260717 이전", {
                "url": "https://wikidocs.net/1",
                "source_url": "https://notes.junghanacs.com/notes/20260717T000000/",
            }),
        ]
        index = BUILD.chapter_index("notes", entries)
        self.assertNotIn("[[SubPages]]", index)
        self.assertLess(index.index("20260718 최신"), index.index("20260717 이전"))
        self.assertIn("[20260718 최신](https://wikidocs.net/2)", index)
        self.assertEqual(index.count(BUILD.CHAPTER_INDEX_START), 1)


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
                lastmod = {
                    "journal": "2024-01-01T09:00:00+09:00",
                    "bib": "2025-06-07T12:34:56+09:00",
                    "notes": "",
                }[folder]
                source_text = (
                    f'---\ntitle: "{title}"\n'
                    f'description: "{folder} 설명"\n'
                    f'date: {did[:4]}-{did[4:6]}-{did[6:8]}T00:00:00+09:00\n'
                    + (f"lastmod: {lastmod}\n" if lastmod else "")
                    + ('tags: ["autholog"]\n' if folder in {"bib", "notes"} else "")
                    + "---\n\n"
                    + ("> [!abstract] 이 노트에 대하여\n> \n> 저자 요약\n\n"
                       if folder == "bib" else "")
                    + "본문\n"
                )
                (source_dir / f"{did}.md").write_text(source_text, encoding="utf-8")
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
            previous["_chapters"]["autholog"] = {
                "page_id": 204,
                "subject": "stale",
                "url": "https://wikidocs.net/204",
            }
            (out / "mapping.json").write_text(
                json.dumps(previous, ensure_ascii=False), encoding="utf-8"
            )
            (garden / "content/index.md").write_text(
                '---\ntitle: "§가든 — 대문"\n---\n\n대문\n', encoding="utf-8"
            )
            (garden / "change-text.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            source_commit = init_git_repo(garden)

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
                    "- [0 어쏠로그](pages/autholog/_chapter.md)",
                    "- [1 저널](pages/journal/_chapter.md)",
                    "- [3 참고문헌](pages/bib/_chapter.md)",
                    "- [4 노트](pages/notes/_chapter.md)",
                ],
            )
            self.assertIn(
                "  - [20240101 저널 시작](pages/journal/20240101T000000.md)", toc
            )
            self.assertIn(
                "  - [20250607 332 참고문헌](pages/bib/20240215T071858.md)", toc
            )
            self.assertIn(
                "  - [20240301 노트 연결](pages/notes/20240301T000000.md)", toc
            )

            mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
            manifest_text = (out / "BUILD-MANIFEST.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            expected_manifest = BUILD.make_build_manifest(
                garden, ["journal", "bib", "notes"], len(fixtures)
            )
            self.assertEqual(manifest, expected_manifest)
            self.assertEqual(
                manifest_text,
                json.dumps(expected_manifest, ensure_ascii=False, indent=2) + "\n",
            )
            self.assertEqual(manifest["source_commit"], source_commit)
            self.assertTrue(manifest["source_content_clean"])
            self.assertEqual(manifest["folders"], ["journal", "bib", "notes"])
            self.assertEqual(manifest["pages"], 3)
            self.assertEqual(len(manifest["source_content_sha256"]), 64)
            for page_id, (folder, (did, _)) in enumerate(fixtures.items(), start=101):
                self.assertEqual(mapping[did]["page_id"], page_id)
                self.assertEqual(
                    mapping[did]["source_url"],
                    f"https://notes.junghanacs.com/{folder}/{did}/",
                )
                self.assertIn("source_date", mapping[did])
                self.assertIn("source_lastmod", mapping[did])
            self.assertEqual(mapping["_chapters"]["bib"]["subject"], "3 참고문헌")
            self.assertEqual(mapping["_chapters"]["autholog"]["page_id"], 204)
            self.assertEqual(mapping["_chapters"]["autholog"]["subject"], "0 어쏠로그")
            collection = (out / "pages/autholog/_chapter.md").read_text(encoding="utf-8")
            self.assertIn("`autholog` 태그 문서 2개", collection)
            self.assertLess(collection.index("20250607 332 참고문헌"),
                            collection.index("20240301 노트 연결"))
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
            self.assertIn("[ok] manifest :", audit.stdout)
            self.assertIn("[ok] audit    : 통과", audit.stdout)

            manifest["source_content_sha256"] = "0" * 64
            (out / "BUILD-MANIFEST.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            mismatch = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_PATH),
                    "--garden",
                    str(garden),
                    "--out",
                    str(out),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("manifest: current garden 입력과 불일치", mismatch.stderr)
            self.assertIn("source_content_sha256", mismatch.stderr)

    def test_build_rejects_dirty_garden_content_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            garden = base / "garden"
            out = base / "out"
            (garden / "content/journal").mkdir(parents=True)
            out.mkdir()
            (out / "README.md").write_text("placeholder\n", encoding="utf-8")
            note = garden / "content/journal/20260713T000000.md"
            note.write_text(
                '---\ntitle: "2026-07-13"\ndescription: "fixture"\n'
                'date: 2026-07-13T00:00:00+09:00\n---\n\n본문\n',
                encoding="utf-8",
            )
            (garden / "content/index.md").write_text(
                '---\ntitle: "Home"\n---\n\n대문\n', encoding="utf-8"
            )
            (garden / "change-text.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            init_git_repo(garden)
            note.write_text(note.read_text(encoding="utf-8") + "dirty\n", encoding="utf-8")

            rejected = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_PATH),
                    "--folders",
                    "journal",
                    "--garden",
                    str(garden),
                    "--out",
                    str(out),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("dirty/untracked", rejected.stderr)
            self.assertFalse((out / "pages").exists())
            self.assertFalse((out / "BUILD-MANIFEST.json").exists())


if __name__ == "__main__":
    unittest.main()
