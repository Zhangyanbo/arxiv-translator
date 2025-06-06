#!/usr/bin/env python3
"""latex_splitter.py
A lightweight utility to split LaTeX documents into length‑bounded, syntax‑balanced
chunks and to restore them later. The tool works in two stages:

1.  *Template extraction* – All regions between consecutive
    ``\begin{document}`` … ``\end{document}`` pairs are replaced by
    placeholders (``$content0`` … ``$contentK``) inside the returned
    *template* string. The removed regions are returned as a list for every
    placeholder.
2.  *Chunking* – Each extracted article (the content of a placeholder) is
    broken into chunks whose concatenated length is roughly *N* characters
    while ensuring LaTeX syntax *closure* (matching braces, environments, math
    modes, …) at chunk boundaries.

The module exposes two public functions:

``split_latex(source: str, target_length: int = 2000)
    -> tuple[str, dict[str, list[str]]]``
    Return the template and a mapping from placeholders to their chunk lists.

``restore_latex(template: str, content_map: dict[str, list[str]]) -> str``
    Rebuild the original document.

When executed as a script it offers two sub‑commands via *argparse*:

    latex_splitter.py split  -i <input.tex> -o <template.tex> -j <chunks.json> \
                              -n <target_length>
    latex_splitter.py merge  -t <template.tex> -j <chunks.json> -o <output.tex>

Only the Python standard library is required.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Tuple, Dict

###############################################################################
#                               INTERNAL HELPERS                              #
###############################################################################
_ENV_PATTERN = re.compile(r"\\(?P<type>begin|end)\{(?P<name>[^}]+)\}")
_DOLLAR_DOLLAR = re.compile(r"\$\$")
_BEGIN_DOC_PATTERN = re.compile(r"\\begin\{document\}", re.IGNORECASE)
_END_DOC_PATTERN = re.compile(r"\\end\{document\}", re.IGNORECASE)


def _extract_document_regions(text: str) -> Tuple[str, List[str]]:
    """Return (template, article_list).

    The *template* is the original *text* but every region between
    ``\begin{document}`` … ``\end{document}`` (excluding the markers) is replaced by a
    placeholder ``$content<i>``. The *article_list* contains the content
    between the markers.
    """
    idx = 0
    articles: List[str] = []
    out_parts: List[str] = []
    pos = 0
    while True:
        m_begin = _BEGIN_DOC_PATTERN.search(text, pos)
        if not m_begin:
            out_parts.append(text[pos:])
            break
        start = m_begin.start()
        m_end = _END_DOC_PATTERN.search(text, start)
        if not m_end:
            raise ValueError("Unmatched \\begin{document} – missing \\end{document}.")
        content = text[m_begin.end():m_end.start()]
        placeholder = f"\\begin{{document}}$content{idx}\\end{{document}}"
        out_parts.extend([text[pos:start], placeholder])
        articles.append(content)
        idx += 1
        pos = m_end.end()
    template = "".join(out_parts)
    return template, articles


###############################################################################
#                              BALANCE CHECKERS                               #
###############################################################################
class _BalanceState:
    """Track LaTeX‑specific balance while scanning lines."""

    __slots__ = ("brace", "bracket", "env_stack", "in_math")

    def __init__(self) -> None:
        self.brace: int = 0
        self.bracket: int = 0
        self.env_stack: List[str] = []
        self.in_math: bool = False  # toggled by $$

    # ---------------------------------------------------------------------
    def update(self, line: str) -> None:  # noqa: C901 (complexity is acceptable here)
        """Update counters with *line* (comments stripped)."""
        # Remove trailing comments – simplistic but effective.
        code = re.sub(r"%.*", "", line)

        # Handle $$ … $$ math mode (display math).
        for _ in _DOLLAR_DOLLAR.finditer(code):
            self.in_math = not self.in_math

        # Environments.
        for m in _ENV_PATTERN.finditer(code):
            if m["type"] == "begin":
                self.env_stack.append(m["name"])
            else:  # end
                if self.env_stack and self.env_stack[-1] == m["name"]:
                    self.env_stack.pop()
                else:
                    # Unbalanced, push negative marker to keep length > 0.
                    self.env_stack.append("__unmatched__")

        # Braces & brackets (ignore inside comments).
        self.brace += code.count("{") - code.count("}")
        self.bracket += code.count("[") - code.count("]")

    # ---------------------------------------------------------------------
    def is_balanced(self) -> bool:
        """Return *True* when everything seen so far is syntactically closed."""
        return (
            self.brace == 0
            and self.bracket == 0
            and not self.env_stack
            and not self.in_math
        )

###############################################################################
#                                CORE LOGIC                                   #
###############################################################################

def _chunk_article(article: str, target_len: int) -> List[str]:
    """Split *article* into roughly *target_len* sized syntax‑balanced chunks."""
    lines = article.splitlines(keepends=True)

    chunks: List[str] = []
    segment_buffer: List[str] = []  # holds lines until closure → becomes *segment*
    chunk_segments: List[str] = []  # each balanced segment collected until len ≥ N
    state = _BalanceState()

    def _flush_segment() -> None:
        if segment_buffer:
            seg = "".join(segment_buffer)
            chunk_segments.append(seg)
            segment_buffer.clear()

    def _flush_chunk(force: bool = False) -> None:
        total_len = sum(len(s) for s in chunk_segments)
        if force or total_len >= target_len:
            if chunk_segments:
                chunks.append("".join(chunk_segments))
                chunk_segments.clear()

    for line in lines:
        segment_buffer.append(line)
        state.update(line)
        if state.is_balanced():
            # Balanced → close segment and maybe chunk.
            _flush_segment()
            _flush_chunk()
            state = _BalanceState()  # reset for next segment

    # Trailing data.
    _flush_segment()
    _flush_chunk(force=True)
    return chunks


def split_latex(source: str | Path, target_length: int = 2000) -> Tuple[str, Dict[str, List[str]]]:
    """Split LaTeX file or string *source* (path or contents).

    Parameters
    ----------
    source : str | pathlib.Path
        Either the LaTeX source string or a path to a ``.tex`` file.
    target_length : int, optional
        Desired character length of each chunk.

    Returns
    -------
    template : str
        The modified LaTeX with ``$content<i>`` placeholders.
    content_map : dict[str, list[str]]
        Mapping from each placeholder to its list of chunk strings.
    """
    if isinstance(source, Path) or (hasattr(source, "exists")):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = str(source)

    template, articles = _extract_document_regions(text)

    content_map: Dict[str, List[str]] = {}
    for idx, art in enumerate(articles):
        placeholder = f"content{idx}"
        content_map[placeholder] = _chunk_article(art, target_length)

    return template, content_map


def restore_latex(template: str | Path, content_map: Dict[str, List[str]]) -> str:
    """Rebuild the original LaTeX string from *template* and *content_map*."""
    if isinstance(template, Path) or (hasattr(template, "exists")):
        template_txt = Path(template).read_text(encoding="utf-8")
    else:
        template_txt = str(template)

    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        try:
            chunks = content_map[key]
        except KeyError as exc:
            raise KeyError(f"Missing key '{key}' in content_map") from exc
        return "".join(chunks)

    pattern = re.compile(r"\$(content\d+)")
    return pattern.sub(_replacer, template_txt)

###############################################################################
#                               CLI INTERFACE                                 #
###############################################################################

def _cli() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(description="Split or merge LaTeX files using balanced chunking.")
    sub = parser.add_subparsers(dest="command", required=True, help="Sub‑commands")

    # Split command.
    p_split = sub.add_parser("split", help="Split a LaTeX file into chunks.")
    p_split.add_argument("-i", "--input", required=True, type=Path, help="Input LaTeX file")
    p_split.add_argument("-o", "--output-template", required=True, type=Path, help="Output template file (.tex)")
    p_split.add_argument("-j", "--output-json", required=True, type=Path, help="Output JSON with chunks map")
    p_split.add_argument("-n", "--target-length", type=int, default=2000, help="Target chunk length (default: 2000)")

    # Merge command.
    p_merge = sub.add_parser("merge", help="Reconstruct a LaTeX file from template + JSON.")
    p_merge.add_argument("-t", "--template", required=True, type=Path, help="Template .tex file")
    p_merge.add_argument("-j", "--json", required=True, type=Path, help="JSON file with chunks map")
    p_merge.add_argument("-o", "--output", required=True, type=Path, help="Restored LaTeX output file")

    args = parser.parse_args()

    if args.command == "split":
        template, c_map = split_latex(args.input, target_length=args.target_length)
        args.output_template.write_text(template, encoding="utf-8")
        args.output_json.write_text(json.dumps(c_map, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ Split complete → {args.output_template} & {args.output_json}")

    elif args.command == "merge":
        c_map = json.loads(args.json.read_text(encoding="utf-8"))
        restored = restore_latex(args.template, c_map)
        args.output.write_text(restored, encoding="utf-8")
        print(f"✅ Merge complete → {args.output}")


if __name__ == "__main__":
    _cli()
