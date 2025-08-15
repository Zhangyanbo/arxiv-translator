import re
from typing import List, Tuple

def remove_useless_newlines(tex: str) -> str:
    # ===== 合并规则（逐行、只看行首）=====
    INLINE = ('\\eg', '\\footnote', '\\cite', '\\citet', '\\citep', '\\cref', '\\Cref', '\\ie')

    def is_blank_line(ln: str) -> bool:
        return ln.lstrip().rstrip('\r\n') == ''

    def is_text_line(ln: str) -> bool:
        s = ln.lstrip().rstrip('\r\n')
        if s == '':
            return False
        if s.startswith('$'):
            return True
        if s.startswith('\\'):
            return any(s.startswith(cmd) for cmd in INLINE)
        return True

    def merge_lines_block(block: str) -> str:
        lines = block.splitlines(keepends=True)
        out, can_merge = [], False
        for ln in lines:
            if is_blank_line(ln):
                out.append(ln); can_merge = False; continue
            if can_merge and is_text_line(ln):
                out[-1] = out[-1].rstrip() + ' ' + ln.lstrip()
            else:
                out.append(ln); can_merge = is_text_line(ln)
        return ''.join(out)

    # ===== 小工具 =====
    n = len(tex)
    def skip_ws(i: int) -> int:
        while i < n and tex[i].isspace(): i += 1
        return i

    def parse_group(i: int, open_ch='{', close_ch='}') -> Tuple[int, int, int]:
        """给定 tex[i] 是 '{' 或 '['，返回 (content_start, content_end, next_index)。"""
        assert tex[i] == open_ch
        depth, j = 1, i + 1
        while j < n:
            c = tex[j]
            if c == '\\':
                j = min(j + 2, n)     # 跳过转义
            elif c == open_ch:
                depth += 1; j += 1
            elif c == close_ch:
                depth -= 1; j += 1
                if depth == 0:
                    return i + 1, j - 1, j
            else:
                j += 1
        # 未闭合，视为到文末
        return i + 1, n, n

    # ===== 一次扫描：环境栈 + 收集待处理片段 =====
    env_stack: List[str] = []              # 小写环境名
    segments: List[Tuple[int, int]] = []   # 半开区间 [s, e)
    open_seg: int | None = None            # 当前“可合并”的片段起点（当栈顶 ∈ {document, abstract} 时）

    i = 0
    while i < n:
        if tex[i] == '\\':
            # 读取命令名（字母序列）
            j = i + 1
            while j < n and tex[j].isalpha(): j += 1
            cmd = tex[i+1:j].lower()

            # \begin{...}
            if cmd == 'begin':
                j = skip_ws(j)
                if j < n and tex[j] == '{':
                    cs, ce, j_after = parse_group(j, '{', '}')
                    env = tex[cs:ce].strip().lower()

                    # 进入任何环境前，若当前栈顶是 document（顶层正文片段），先截断
                    if env_stack and env_stack[-1] in ('document', 'abstract') and open_seg is not None:
                        segments.append((open_seg, i)); open_seg = None

                    env_stack.append(env)

                    # 进入 document / abstract 后，从 \begin{...} 的右花括号后一位开始新的片段
                    if env in ('document', 'abstract'):
                        open_seg = j_after

                    i = j_after
                    continue

            # \end{...}
            if cmd == 'end':
                j = skip_ws(j)
                if j < n and tex[j] == '{':
                    cs, ce, j_after = parse_group(j, '{', '}')
                    env = tex[cs:ce].strip().lower()

                    # 结束 env 之前，若当前栈顶就是它，且它是可合并环境，则把片段截到 \end 的反斜杠处
                    if env_stack and env_stack[-1] == env and env in ('document', 'abstract') and open_seg is not None:
                        segments.append((open_seg, i)); open_seg = None

                    # 宽容弹栈
                    while env_stack and env_stack[-1] != env:
                        env_stack.pop()
                    if env_stack:
                        env_stack.pop()

                    # 退出某环境后，若新的栈顶是 document/abstract，则从 \end{...} 的右花括号后一位继续开片段
                    if env_stack and env_stack[-1] in ('document', 'abstract') and open_seg is None:
                        open_seg = j_after

                    i = j_after
                    continue

            # \caption[*][opt]{...} —— 无论当前在什么环境，都处理“正文参数”
            if cmd == 'caption':
                k = j
                k = skip_ws(k)
                if k < n and tex[k] == '*':  # \caption*
                    k += 1
                k = skip_ws(k)
                if k < n and tex[k] == '[':  # 可选参数
                    _, _, k = parse_group(k, '[', ']')
                    k = skip_ws(k)
                if k < n and tex[k] == '{':
                    cs, ce, k_after = parse_group(k, '{', '}')
                    # 若有打开的顶层片段，先截断到 caption 内容开始
                    if open_seg is not None and open_seg < cs:
                        segments.append((open_seg, cs))
                        open_seg = None
                    # 记录 caption 正文参数
                    if cs < ce:
                        segments.append((cs, ce))
                    # caption 结束后，如栈顶是 document/abstract，则从 '}' 后继续开片段
                    if env_stack and env_stack[-1] in ('document', 'abstract'):
                        open_seg = k_after
                    i = k_after
                    continue

            # 其它命令：如果当前栈顶是 document/abstract 且还没开片段，则从这里开
            if env_stack and env_stack[-1] in ('document', 'abstract') and open_seg is None:
                open_seg = i
            i = j if j > i else i + 1
        else:
            # 普通字符：处于 document/abstract 时确保片段开启
            if env_stack and env_stack[-1] in ('document', 'abstract') and open_seg is None:
                open_seg = i
            i += 1

    # 文件结束：若仍有打开片段
    if open_seg is not None and open_seg < n:
        segments.append((open_seg, n))

    if not segments:
        return tex

    # ===== 把这些片段做“按行合并”，再拼回去 =====
    out, last = [], 0
    for s, e in segments:
        if last < s:
            out.append(tex[last:s])
        out.append(merge_lines_block(tex[s:e]))
        last = e
    if last < n:
        out.append(tex[last:])
    return ''.join(out)
