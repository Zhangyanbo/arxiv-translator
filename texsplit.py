from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import re

from pylatexenc.latexwalker import (
    LatexWalker,
    LatexNode,
    LatexEnvironmentNode,
    LatexCharsNode,
    LatexCommentNode,
    LatexMacroNode,
)

BLANKLINE_RE = re.compile(r'(?:\r?\n[ \t]*){2,}', re.MULTILINE)


class LaTeXSlicingError(Exception):
    pass


def _walk_nodes(nodes: List[LatexNode]):
    """遍历节点树（尽量复用 latexwalker 通用结构，不造轮子）。"""
    stack = list(nodes)[::-1]
    while stack:
        nd = stack.pop()
        yield nd

        nl = getattr(nd, "nodelist", None)
        if isinstance(nl, list):
            stack.extend(nl[::-1])

        nodeargd = getattr(nd, "nodeargd", None)
        if nodeargd is not None:
            arglist = getattr(nodeargd, "arglist", None) or getattr(nodeargd, "argnlist", None)
            if arglist:
                for arg in reversed(arglist):
                    if hasattr(arg, "nodelist") and isinstance(arg.nodelist, list):
                        stack.extend(arg.nodelist[::-1])
                    elif hasattr(arg, "node") and isinstance(arg.node, LatexNode):
                        stack.append(arg.node)


def _find_first_env(nodes: List[LatexNode], name: str) -> Optional[LatexEnvironmentNode]:
    for nd in _walk_nodes(nodes):
        if isinstance(nd, LatexEnvironmentNode) and nd.envname == name:
            return nd
    return None


def _remove_comments(tex: str) -> str:
    """精确去注释：借助 CommentNode，避免误删 verbatim 中的 %。"""
    walker = LatexWalker(tex)
    nodelist, _, _ = walker.get_latex_nodes()

    spans: List[Tuple[int, int]] = []
    for nd in _walk_nodes(nodelist):
        if isinstance(nd, LatexCommentNode):
            spans.append((nd.pos, nd.pos + nd.len))

    if not spans:
        return tex

    spans.sort()
    merged: List[Tuple[int, int]] = []
    for s, e in spans:
        if not merged or s > merged[-1][1]:
            merged.append((s, e))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))

    out, cur = [], 0
    for s, e in merged:
        out.append(tex[cur:s])
        cur = e
    out.append(tex[cur:])
    return "".join(out)


def _document_body_bounds(tex: str, nodelist: List[LatexNode]) -> Tuple[int, int, Optional[LatexEnvironmentNode]]:
    doc_env = _find_first_env(nodelist, "document")
    if doc_env is None:
        return 0, len(tex), None

    env_slice = tex[doc_env.pos: doc_env.pos + doc_env.len]
    m_begin = re.search(r'\\begin\{document\}', env_slice)
    m_end = re.search(r'\\end\{document\}', env_slice)
    if not (m_begin and m_end):
        if doc_env.nodelist:
            s = doc_env.nodelist[0].pos
            e = doc_env.nodelist[-1].pos + doc_env.nodelist[-1].len
            return s, e, doc_env
        return doc_env.pos, doc_env.pos, doc_env

    body_start = doc_env.pos + m_begin.end()
    body_end = doc_env.pos + m_end.start()
    return body_start, body_end, doc_env


def _allowed_cut_positions(tex: str, body_start: int, body_end: int,
                           body_top_nodes: List[LatexNode]) -> List[int]:
    """
    允许切分的位置（严格避免行内处切分）：
      - 顶层环境的开始/结束（LatexEnvironmentNode）
      - 顶层 LatexCharsNode 里的“空行末端”（≥2 个换行，可夹空白）
      - 顶层 \par 宏之后（LatexMacroNode(macroname=='par') 的 end）
    """
    allowed = {body_start, body_end}

    for nd in body_top_nodes:
        s = max(nd.pos, body_start)
        e = min(nd.pos + nd.len, body_end)
        if not (s < e):
            continue

        if isinstance(nd, LatexEnvironmentNode):
            allowed.add(s)
            allowed.add(e)
        elif isinstance(nd, LatexCharsNode):
            seg = tex[s:e]
            for m in BLANKLINE_RE.finditer(seg):
                allowed.add(s + m.end())
        elif isinstance(nd, LatexMacroNode) and nd.macroname == "par":
            allowed.add(e)
        # 其它（宏、分组、数学等）都视为行内：不加入任何边界

    cuts = sorted(p for p in allowed if body_start <= p <= body_end)
    if not cuts or cuts[0] != body_start or cuts[-1] != body_end:
        raise LaTeXSlicingError("合法切点集合异常")
    return cuts


def latex_cut(tex: str, L: int, remove_comment: bool=True) -> Dict[str, Any]:
    """
    切分规则：
      - 无 document：整篇为正文；有 document：正文为其内部。
      - 只在：顶层环境边界、顶层空行、\\par 之后 切分；不会在任何行内宏/数学/分组边界处切。
      - 每块长度 >= L；若总长 < L，则只返回 1 块。
      - 贪心尽早切，但保证尾段也 >= L；若切点不足，则并入末段。
    返回:
      {"template": <正文替换为 $document 的模板>, "chunks": [块1, 块2, ...]}
    """
    if not isinstance(tex, str):
        raise TypeError("tex 必须是 str")
    if not isinstance(L, int) or L <= 0:
        raise ValueError("L 必须是正整数")

    tex_nc = _remove_comments(tex) if remove_comment else tex

    walker = LatexWalker(tex_nc)
    root_nodes, _, _ = walker.get_latex_nodes()

    body_start, body_end, doc_env = _document_body_bounds(tex_nc, root_nodes)
    body_text = tex_nc[body_start:body_end]

    if doc_env is not None:
        body_nodes = list(doc_env.nodelist)
    else:
        body_nodes = root_nodes
    body_nodes = [nd for nd in body_nodes if (nd.pos + nd.len) > body_start and nd.pos < body_end]

    cuts_allowed = _allowed_cut_positions(tex_nc, body_start, body_end, body_nodes)

    total_len = body_end - body_start
    if total_len <= L:
        template = tex_nc[:body_start] + "$document" + tex_nc[body_end:]
        return {"template": template, "chunks": [body_text]}

    chunks: List[str] = []
    cur = body_start
    i = cuts_allowed.index(body_start)
    last_idx = len(cuts_allowed) - 1

    while i < last_idx:
        target = cur + L
        j = i + 1
        while j <= last_idx and cuts_allowed[j] < target:
            j += 1

        if j > last_idx:
            chunks.append(tex_nc[cur:body_end])
            break

        k = j
        while k <= last_idx and cuts_allowed[k] <= (body_end - L):
            k += 1
        k -= 1

        if k < j:
            chunks.append(tex_nc[cur:body_end])
            break

        cut_pos = cuts_allowed[j]
        chunks.append(tex_nc[cur:cut_pos])
        cur = cut_pos
        i = j

    if cur < body_end:
        chunks.append(tex_nc[cur:body_end])

    template = tex_nc[:body_start] + "$document" + tex_nc[body_end:]

    # 保障每块（尤其倒数第二块）≥ L；若尾段 < L，则与前一块合并兜底
    if len(chunks) > 1 and len(chunks[-1]) < L:
        chunks[-2:] = [chunks[-2] + chunks[-1]]

    return {"template": template, "chunks": chunks}
