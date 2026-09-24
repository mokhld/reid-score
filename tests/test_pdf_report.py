from __future__ import annotations

import re
import unittest

from reid_score.scorer import ReidScorer, _basic_pdf

PAGE_WIDTH = 595
PAGE_HEIGHT = 842

_OBJECT = re.compile(rb"(\d+) 0 obj\n")
_STREAM = re.compile(rb"<< /Length (\d+) >>\nstream\n")
_TEXT_LINE = re.compile(rb"1 0 0 1 (-?\d+) (-?\d+) Tm \(((?:\\.|[^\\()])*)\) Tj")


def _unescape(raw: bytes) -> str:
    return re.sub(rb"\\(.)", rb"\1", raw, flags=re.DOTALL).decode("cp1252")


class ParsedPDF:
    """Just enough of a PDF reader to check what _basic_pdf writes."""

    def __init__(self, pdf: bytes) -> None:
        self.pdf = pdf
        startxref = int(re.search(rb"startxref\n(\d+)\n%%EOF", pdf).group(1))
        assert pdf[startxref:].startswith(b"xref\n0 "), "startxref does not point at xref"
        header = re.match(rb"xref\n0 (\d+)\n", pdf[startxref:])
        size = int(header.group(1))
        entries = pdf[startxref + header.end():].split(b"\n")[:size]
        assert entries[0] == b"0000000000 65535 f ", entries[0]
        self.objects: dict[int, bytes] = {}
        for number, entry in enumerate(entries[1:], start=1):
            offset = int(entry[:10])
            match = _OBJECT.match(pdf, offset)
            assert match and int(match.group(1)) == number, f"xref entry {number} is wrong"
            end = pdf.index(b"\nendobj\n", match.end())
            self.objects[number] = pdf[match.end():end]
        assert f"/Size {size} ".encode() in pdf

    def stream(self, number: int) -> bytes:
        body = self.objects[number]
        match = _STREAM.match(body)
        assert match, f"object {number} is not a stream"
        length = int(match.group(1))
        data = body[match.end(): match.end() + length]
        assert body[match.end() + length:] == b"\nendstream", "stream /Length is wrong"
        return data

    def page_numbers(self) -> list[int]:
        tree = self.objects[2]
        kids = [int(n) for n in re.findall(rb"(\d+) 0 R", re.search(rb"/Kids \[(.*?)\]", tree).group(1))]
        count = int(re.search(rb"/Count (\d+)", tree).group(1))
        assert count == len(kids), "/Count does not match /Kids"
        return kids

    def text_lines(self) -> list[tuple[int, int, int, str]]:
        """Return (page index, x, y, text) for every line drawn."""
        lines = []
        for index, page in enumerate(self.page_numbers()):
            page_obj = self.objects[page]
            assert b"/Parent 2 0 R" in page_obj
            contents = int(re.search(rb"/Contents (\d+) 0 R", page_obj).group(1))
            for x, y, raw in _TEXT_LINE.findall(self.stream(contents)):
                lines.append((index, int(x), int(y), _unescape(raw)))
        return lines


class BasicPDFTests(unittest.TestCase):
    def test_twenty_record_report_spans_pages_and_keeps_every_record(self) -> None:
        scorer = ReidScorer(llm_provider="rule_based", geography="GB")
        texts = [
            f"Record {i}: email person{i}@example.com, age 34 female marine "
            "biologist in SW1A 1AA"
            for i in range(20)
        ]
        results = scorer.score_batch(texts)
        pdf = scorer.generate_report(results, standard="gdpr", format="pdf")

        parsed = ParsedPDF(pdf)
        self.assertGreater(len(parsed.page_numbers()), 1)
        lines = parsed.text_lines()
        text = "\n".join(line for _, _, _, line in lines)
        for i in range(1, 21):
            self.assertIn(f"[{i}]", text)
        for page, x, y, line in lines:
            self.assertTrue(0 < x < PAGE_WIDTH, f"x={x} off page for {line!r}")
            self.assertTrue(36 <= y <= PAGE_HEIGHT - 36, f"y={y} outside margins for {line!r}")

    def test_page_breaks_after_55_lines(self) -> None:
        one_page = ParsedPDF(_basic_pdf("\n".join(f"line {i}" for i in range(55))))
        self.assertEqual(1, len(one_page.page_numbers()))

        parsed = ParsedPDF(_basic_pdf("\n".join(f"line {i}" for i in range(56))))
        self.assertEqual(2, len(parsed.page_numbers()))
        lines = parsed.text_lines()
        self.assertEqual(56, len(lines))
        self.assertEqual((1, 40, 800, "line 55"), lines[-1])
        self.assertEqual([f"line {i}" for i in range(56)], [line for *_, line in lines])

    def test_parentheses_and_backslash_are_escaped(self) -> None:
        original = r"Name (redacted) stored at C:\records\x (see note)"
        pdf = _basic_pdf(original)
        self.assertIn(
            rb"(Name \(redacted\) stored at C:\\records\\x \(see note\)) Tj",
            pdf,
        )
        self.assertEqual([original], [line for *_, line in ParsedPDF(pdf).text_lines()])

    def test_unbalanced_parenthesis_round_trips(self) -> None:
        original = "trailing ) and ( and \\"
        lines = ParsedPDF(_basic_pdf(original)).text_lines()
        self.assertEqual([original], [line for *_, line in lines])

    def test_non_latin1_text_is_transliterated(self) -> None:
        pdf = _basic_pdf("caf\u00e9 \u201cquote\u201d \u011f \ufb01 \u6771")
        self.assertIn(b"/Encoding /WinAnsiEncoding", pdf)
        [(_, _, _, line)] = ParsedPDF(pdf).text_lines()
        # cp1252 keeps e-acute and curly quotes; g-breve and the fi ligature
        # have ASCII forms; the CJK character has none and becomes "?".
        self.assertEqual("caf\u00e9 \u201cquote\u201d g fi ?", line)

    def test_long_lines_wrap_inside_the_page(self) -> None:
        words = [f"word{i}" for i in range(60)]
        lines = ParsedPDF(_basic_pdf("    " + " ".join(words))).text_lines()
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(len(line) <= 90 for *_, line in lines))
        self.assertEqual(words, " ".join(line for *_, line in lines).split())

    def test_empty_text_is_a_valid_single_page(self) -> None:
        parsed = ParsedPDF(_basic_pdf(""))
        self.assertEqual(1, len(parsed.page_numbers()))
        self.assertEqual([], parsed.text_lines())


if __name__ == "__main__":
    unittest.main()
