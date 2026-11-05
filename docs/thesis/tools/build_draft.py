#!/usr/bin/env python3
"""由分章真源生成目录和阅读副本，不调用模型或更改实验材料。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path


def headings(text: str) -> list[tuple[int, str]]:
    result = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        match = re.match(r"^(#{1,3}) (.+)$", line)
        if match and not in_code:
            result.append((len(match[1]), match[2]))
    return result


def make_docx(
    rendered: str, target: Path, title: str, version: str, export_date: str
) -> dict:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
    from lxml import html

    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.3), Cm(2.3)
    section.left_margin, section.right_margin = Cm(2.5), Cm(2.3)
    document.core_properties.title = title
    document.core_properties.subject = f"硕士论文阶段初稿{version}，{export_date}"
    document.core_properties.author = ""

    def font(style, name, size):
        style.font.name = name
        style.font.size = Pt(size)
        style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)

    font(document.styles["Normal"], "Noto Serif CJK SC", 11)
    normal = document.styles["Normal"].paragraph_format
    normal.line_spacing = 1.35
    normal.space_after = Pt(6)
    for name, size in [
        ("Title", 20),
        ("Heading 1", 17),
        ("Heading 2", 14),
        ("Heading 3", 12),
    ]:
        font(document.styles[name], "Noto Sans CJK SC", size)
        fmt = document.styles[name].paragraph_format
        fmt.keep_with_next = True
        fmt.space_before, fmt.space_after = Pt(12), Pt(7)

    header = section.header.paragraphs[0]
    header.text = f"Forge · 硕士论文阶段初稿 {version} · {export_date}"
    header.style = document.styles["Normal"]
    for run in header.runs:
        run.font.size = Pt(8)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("— ")
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    footer.add_run(" —")

    root = html.fragment_fromstring(rendered, create_parent="div")

    def text_run(paragraph, text, bold=False, italic=False, code=False):
        if not text:
            return
        run = paragraph.add_run(text)
        run.bold, run.italic = bold, italic
        if code:
            run.font.name = "DejaVu Sans Mono"
            run.font.size = Pt(9)
        return run

    def inline(paragraph, element, bold=False, italic=False, code=False):
        text_run(paragraph, element.text, bold, italic, code)
        for child in element:
            if child.tag == "img":
                image = Path(child.get("src", ""))
                if image.exists():
                    paragraph.add_run().add_picture(str(image), width=Cm(16))
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    raise FileNotFoundError(image)
            elif child.tag == "br":
                paragraph.add_run().add_break()
            else:
                inline(
                    paragraph,
                    child,
                    bold or child.tag in {"strong", "b"},
                    italic or child.tag in {"em", "i"},
                    code or child.tag == "code",
                )
            text_run(paragraph, child.tail, bold, italic, code)

    title_seen = False
    for element_index, element in enumerate(root):
        tag = element.tag
        following = root[element_index + 1] if element_index + 1 < len(root) else None
        following_text = following.text_content() if following is not None else ""
        if tag in {"h1", "h2", "h3"}:
            level = int(tag[1])
            if level == 1 and not title_seen:
                paragraph = document.add_paragraph(style="Title")
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                title_seen = True
            else:
                paragraph = document.add_heading(level=level)
                if level == 1:
                    paragraph.paragraph_format.page_break_before = True
            inline(paragraph, element)
        elif tag == "table":
            rows = element.xpath(".//tr")
            compact = len(rows) <= 8 and len(element.text_content()) < 1400
            width = max(len(row) for row in rows)
            table = document.add_table(rows=0, cols=width)
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = False
            # 文本列给出较多宽度，避免五列表格的长标签被逐字挤压。
            weights = [2.1] + [1.0] * (width - 1) if width >= 5 else [1.0] * width
            for column, weight in zip(table.columns, weights):
                column.width = Cm(16.2 * weight / sum(weights))
            for index, row in enumerate(rows):
                cells = table.add_row().cells
                for cell, source in zip(cells, row):
                    paragraph = cell.paragraphs[0]
                    paragraph.paragraph_format.space_after = Pt(3)
                    paragraph.paragraph_format.line_spacing = 1.1
                    inline(paragraph, source, bold=index == 0)
                    for run in paragraph.runs:
                        run.font.size = Pt(8 if width >= 6 else 9)
                    if (compact or index == len(rows) - 1) and re.match(
                        r"^表[0-9A-Z]", following_text
                    ):
                        paragraph.paragraph_format.keep_with_next = True
                # 避免真实案例的一行在换页处被切成两半。
                no_split = OxmlElement("w:cantSplit")
                table.rows[-1]._tr.get_or_add_trPr().append(no_split)
                if index == 0:
                    repeat = OxmlElement("w:tblHeader")
                    table.rows[0]._tr.get_or_add_trPr().append(repeat)
            spacer = document.add_paragraph().paragraph_format
            spacer.space_after = Pt(0)
            spacer.keep_with_next = bool(re.match(r"^表[0-9A-Z]", following_text))
        elif tag == "pre":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.line_spacing = 1.1
            paragraph.paragraph_format.keep_together = True
            text_run(paragraph, element.text_content(), code=True)
        elif tag in {"ul", "ol"}:
            for index, item in enumerate(element, 1):
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Cm(0.5)
                paragraph.paragraph_format.first_line_indent = Cm(-0.4)
                text_run(paragraph, f"{index}. " if tag == "ol" else "• ")
                inline(paragraph, item)
        elif tag == "blockquote":
            for child in element:
                paragraph = document.add_paragraph(style="Quote")
                inline(paragraph, child)
        elif tag != "hr":
            paragraph = document.add_paragraph()
            inline(paragraph, element)
            if element.xpath(".//img") and re.match(r"^图[0-9A-Z]", following_text):
                paragraph.paragraph_format.keep_with_next = True

    document.save(target)
    return {
        "paragraphs": len(document.paragraphs),
        "tables": len(document.tables),
        "images": len(document.inline_shapes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deps-dir", type=Path)
    parser.add_argument("--version", default="v0.1")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    if not re.fullmatch(r"v[0-9]+(?:\.[0-9]+)+", args.version):
        parser.error("版本使用v0.1等数字格式")
    filename = f"Forge-硕士论文阶段初稿-{args.version}"
    if args.deps_dir:
        sys.path.insert(0, str(args.deps_dir.resolve()))

    source_root = Path(__file__).resolve().parents[1]
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    chapters = sorted((source_root / "chapters").glob("*.md"))
    texts = [(path, path.read_text(encoding="utf-8")) for path in chapters]
    contents = [
        "# 七章目录与章节入口",
        "",
        "由分章源稿标题生成；修改章节后重新生成。",
        "",
    ]
    reading_toc = ["# 目录", "", "阶段阅读目录；最终页码以学校模板排版为准。", ""]
    for path, text in texts[1:]:
        for level, label in headings(text):
            if level > 2:
                continue
            contents.append(f"{'  ' * (level - 1)}- [{label}](chapters/{path.name})")
            reading_toc.extend([("## " if level == 1 else "") + label, ""])
    (source_root / "CONTENTS.md").write_text(
        "\n".join(contents) + "\n", encoding="utf-8"
    )

    combined = texts[0][1] + "\n\n" + "\n".join(reading_toc)
    combined += "\n\n" + "\n\n".join(text for _, text in texts[1:])
    combined = combined.replace("../figures/", "figures/")
    markdown_path = output / f"{filename}.md"
    markdown_path.write_text(combined, encoding="utf-8")
    shutil.copytree(source_root / "figures", output / "figures", dirs_exist_ok=True)
    summary = {
        "version": args.version,
        "date": args.date,
        "source": str(source_root),
        "operation": "仅生成阅读副本；以下新增调用数不表示正文的历史实验数量",
        "chapters": [path.name for path, _ in texts],
        "main_chapters": 7,
        "source_characters": sum(len(text) for _, text in texts),
        "source_chinese_characters": sum(
            len(re.findall(r"[\u4e00-\u9fff]", text)) for _, text in texts
        ),
        "new_experiments": 0,
        "provider_calls": 0,
    }

    try:
        import markdown
        import docx  # noqa: F401
    except ImportError as error:
        summary["export_warning"] = f"已生成Markdown与目录；Word/HTML依赖缺失：{error}"
    else:
        rendered = markdown.markdown(
            combined, extensions=["tables", "fenced_code", "sane_lists"]
        )
        css = """
body{font-family:'Noto Serif CJK SC',serif;max-width:1050px;margin:40px auto;padding:0 28px;color:#20262e;line-height:1.8}
h1,h2,h3{font-family:'Noto Sans CJK SC',sans-serif;line-height:1.4;color:#17365a}
h1{margin-top:2.4em;border-bottom:1px solid #b8c8d9;padding-bottom:.4em}
table{border-collapse:collapse;width:100%;font-size:.9em;margin:1em 0}
th,td{border:1px solid #becbd8;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#edf3f9} img{max-width:100%;height:auto}pre{white-space:pre-wrap;background:#f2f4f6;padding:15px}
code{overflow-wrap:anywhere}blockquote{border-left:4px solid #a7b9d0;margin-left:0;padding-left:1em;color:#46576a}
@media print{body{margin:0;max-width:none;font-size:10.5pt}h1{break-before:page}h1:first-child{break-before:auto}tr,img{break-inside:avoid}}
"""
        title = "面向C/C++仓库自动化构建的状态感知动作选择与验证方法研究"
        html_path = output / f"{filename}.html"
        html_path.write_text(
            f'<!doctype html>\n<html lang="zh-CN"><meta charset="utf-8"><title>{title}</title>'
            f"<style>{css}</style><body>{rendered}</body></html>\n",
            encoding="utf-8",
        )
        # Word图片使用绝对路径，HTML/Markdown图片仍相对输出目录。
        word_html = rendered.replace('src="figures/', f'src="{output}/figures/')
        summary["word"] = make_docx(
            word_html, output / f"{filename}.docx", title, args.version, args.date
        )
    (output / "build-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
