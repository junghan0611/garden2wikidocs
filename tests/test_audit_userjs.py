"""audit.py 의 사용자 스크립트 대조 게이트 회귀 테스트.

`wikidocs-user-script.js` 는 위키독스 책 설정에 손으로 붙여넣는 사이드바 스크립트다.
GitHub 웹훅 동기화 대상이 아니라서 리포와 조용히 어긋날 수 있고, 어긋난 채로 붙여넣으면
독자는 죽은 챕터 링크를 본다. 그래서 audit 이 CH 배열을 TOC/mapping 과 대조한다.
"""
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / ".claude/skills/garden-to-wikidocs/scripts/audit.py"
SPEC = importlib.util.spec_from_file_location("garden_to_wikidocs_audit", AUDIT_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class AeoIndexContractTests(unittest.TestCase):
    ENTRIES = [
        ("첫째", {"path": "pages/notes/20260102T000000.md",
                  "url": "https://wikidocs.net/2",
                  "source_url": "https://notes.junghanacs.com/notes/20260102T000000/"}),
        ("둘째", {"path": "pages/notes/20260101T000000.md",
                  "url": "https://wikidocs.net/1",
                  "source_url": "https://notes.junghanacs.com/notes/20260101T000000/"}),
    ]

    def test_heading_count_and_read_link_order_match(self):
        text = (
            "안내\n\n## 첫째\n\n[위키독스에서 읽기 →](https://wikidocs.net/2)\n\n"
            "## 둘째\n\n[위키독스에서 읽기 →](https://wikidocs.net/1)\n")
        self.assertEqual(
            AUDIT.index_structure_findings("notes", text, self.ENTRIES, None), [])

    def test_description_heading_injection_changes_count(self):
        text = (
            "## 첫째\n\n## 설명이 만든 가짜 헤딩\n\n"
            "[위키독스에서 읽기 →](https://wikidocs.net/2)\n\n"
            "## 둘째\n\n[위키독스에서 읽기 →](https://wikidocs.net/1)\n")
        errors = AUDIT.index_structure_findings("notes", text, self.ENTRIES, None)
        self.assertTrue(any("## 항목 수 불일치" in error for error in errors))

    def test_duplicate_headings_are_rejected(self):
        text = (
            "## 같은 제목\n\n[위키독스에서 읽기 →](https://wikidocs.net/2)\n\n"
            "## 같은 제목\n\n[위키독스에서 읽기 →](https://wikidocs.net/1)\n")
        errors = AUDIT.index_structure_findings("notes", text, self.ENTRIES, None)
        self.assertTrue(any("중복 heading" in error for error in errors))

    def test_reordered_read_links_are_rejected(self):
        text = (
            "## 첫째\n\n[위키독스에서 읽기 →](https://wikidocs.net/1)\n\n"
            "## 둘째\n\n[위키독스에서 읽기 →](https://wikidocs.net/2)\n")
        errors = AUDIT.index_structure_findings("notes", text, self.ENTRIES, None)
        self.assertTrue(any("순서/대상 불일치" in error for error in errors))


class UserScriptParseTests(unittest.TestCase):
    def test_ch_array_is_read_as_page_id_and_subject(self):
        script = ("var CH=[[null,'0 어쏠로그'],[380373,'1 저널'],"
                  "[382535,'5 봇로그']];")
        self.assertEqual(
            AUDIT.user_script_chapters(script),
            [(None, "0 어쏠로그"), (380373, "1 저널"), (382535, "5 봇로그")])

    def test_chapter_key_reads_folder_or_tag_from_cover_path(self):
        self.assertEqual(AUDIT.chapter_key("pages/notes/_chapter.md"), "notes")
        self.assertEqual(AUDIT.chapter_key("pages/autholog/_chapter.md"), "autholog")

    def test_comment_examples_are_not_mistaken_for_chapters(self):
        script = ("/* 유지보수: [999999,'옛 챕터'] 처럼 적는다 */\n"
                  "var CH=[[null,'0 어쏠로그'],[380373,'1 저널']];")
        self.assertEqual(AUDIT.user_script_chapters(script),
                         [(None, "0 어쏠로그"), (380373, "1 저널")])

    def test_missing_declaration_reads_as_no_chapters(self):
        self.assertEqual(AUDIT.user_script_chapters("var OTHER=[[1,'x']];"), [])


class UserScriptGateTests(unittest.TestCase):
    """대조 게이트의 오류/경고 분기. 생성물 상태에 기대지 않는다."""

    NAV = [(None, "0 어쏠로그"), (380373, "1 저널"), (382535, "5 봇로그")]

    def test_matching_script_reports_nothing(self):
        errors, warnings = AUDIT.user_script_findings(self.NAV, self.NAV)
        self.assertEqual((errors, warnings), ([], []))

    def test_wrong_page_id_is_an_error(self):
        declared = [(None, "0 어쏠로그"), (999999, "1 저널"), (382535, "5 봇로그")]
        errors, warnings = AUDIT.user_script_findings(declared, self.NAV)
        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("999999 != 380373", errors[0])

    def test_missing_chapter_is_an_error(self):
        declared = [(None, "0 어쏠로그"), (380373, "1 저널")]
        errors, _ = AUDIT.user_script_findings(declared, self.NAV)
        self.assertEqual(len(errors), 1)
        self.assertIn("챕터 목록/순서가 TOC 와 다름", errors[0])

    def test_reordered_chapters_are_an_error(self):
        declared = [(380373, "1 저널"), (None, "0 어쏠로그"), (382535, "5 봇로그")]
        errors, _ = AUDIT.user_script_findings(declared, self.NAV)
        self.assertEqual(len(errors), 1)

    def test_recovered_page_id_still_null_is_a_warning_not_an_error(self):
        # 회수 후 CH 갱신을 잊은 상태. DOM 폴백으로 돌긴 하므로 push 를 막지는 않는다.
        expected = [(390000, "0 어쏠로그"), (380373, "1 저널"), (382535, "5 봇로그")]
        errors, warnings = AUDIT.user_script_findings(self.NAV, expected)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("390000", warnings[0])

    def test_unrecovered_cover_on_both_sides_is_silent(self):
        # 아직 발행 전이라 양쪽 다 page_id 가 없다 — 정상이다.
        errors, warnings = AUDIT.user_script_findings(
            [(None, "0 어쏠로그")], [(None, "0 어쏠로그")])
        self.assertEqual((errors, warnings), ([], []))

    def test_page_id_declared_before_recovery_is_an_error(self):
        # mapping 이 미회수인데 CH 에 숫자가 있으면 그 ID 의 출처가 없다(옛 ID/임의값).
        errors, warnings = AUDIT.user_script_findings(
            [(999999, "0 어쏠로그")], [(None, "0 어쏠로그")])
        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("출처 없는 ID", errors[0])


if __name__ == "__main__":
    unittest.main()
