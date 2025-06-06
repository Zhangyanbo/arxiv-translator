# latex_comment_remover.py
import argparse
import sys


def remove_empty_lines(latex_code: str) -> str:
    """
    从 LaTeX 代码字符串中删除连续的空行，但保留单个空行。

    Args:
        latex_code: 包含 LaTeX 代码的字符串。

    Returns:
        处理后的 LaTeX 代码字符串，连续空行被替换为单个空行。
    """
    lines = latex_code.splitlines()
    processed_lines = []
    empty_line_count = 0

    for line in lines:
        if not line.strip():
            empty_line_count += 1
            if empty_line_count <= 1:
                processed_lines.append(line)
        else:
            empty_line_count = 0
            processed_lines.append(line)

    return "\n".join(processed_lines)

def remove_comment(latex_code: str) -> str:
    """
    从 LaTeX 代码字符串中删除注释。
    处理转义的百分号 (例如 \\%)。

    Args:
        latex_code: 包含 LaTeX 代码的字符串。

    Returns:
        移除了注释的 LaTeX 代码字符串。
    """
    lines = latex_code.splitlines()
    processed_lines = []
    for line in lines:
        comment_start_index = -1
        # 遍历当前行，查找第一个未被转义的 '%'
        for i, char in enumerate(line):
            if char == '%':
                # 检查这个 '%' 是否被转义
                # 计算其前面有多少个连续的反斜杠
                num_backslashes = 0
                temp_idx = i - 1
                while temp_idx >= 0 and line[temp_idx] == '\\':
                    num_backslashes += 1
                    temp_idx -= 1
                
                # 如果前面的反斜杠数量是偶数，则这个 '%' 是注释起始符
                if num_backslashes % 2 == 0:
                    comment_start_index = i
                    break  # 找到第一个注释起始符后即可停止搜索当前行
        
        if comment_start_index != -1:
            # 保留注释之前的部分，并去除其尾部的空白字符
            processed_line = line[:comment_start_index].rstrip()
            processed_lines.append(processed_line)
        else:
            # 没有找到注释，保留原行
            processed_lines.append(line)
            
    return remove_empty_lines("\n".join(processed_lines))

def main():
    parser = argparse.ArgumentParser(
        description="从 LaTeX 文件中移除注释并输出结果。",
        formatter_class=argparse.RawTextHelpFormatter # 允许在帮助信息中使用换行符
    )
    parser.add_argument(
        "input_file",
        help="输入的 LaTeX 文件的路径。"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_file",
        help="输出文件的路径。\n如果未指定，结果将打印到标准输出(stdout)。",
        default=None # 默认为 None，表示输出到 stdout
    )
    parser.add_argument(
        "-e", "--encoding",
        default="utf-8",
        help="指定输入和输出文件的编码格式 (默认为: utf-8)。"
    )

    args = parser.parse_args()

    try:
        with open(args.input_file, 'r', encoding=args.encoding) as f:
            latex_content = f.read()
    except FileNotFoundError:
        print(f"错误: 输入文件 '{args.input_file}' 未找到。", file=sys.stderr)
        sys.exit(1) # 退出程序，返回错误码 1
    except IOError as e:
        print(f"错误: 读取文件 '{args.input_file}' 时发生 IO 错误: {e}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"错误: 使用编码 '{args.encoding}' 解码文件 '{args.input_file}' 失败: {e}", file=sys.stderr)
        print(f"提示: 请检查文件编码或尝试使用 '-e <其他编码>' 参数指定正确的编码，例如 '-e gbk' 或 '-e latin-1'。", file=sys.stderr)
        sys.exit(1)

    cleaned_content = remove_comment(latex_content)

    if args.output_file:
        try:
            with open(args.output_file, 'w', encoding=args.encoding) as f:
                f.write(cleaned_content)
            print(f"已成功移除注释，结果已保存到 '{args.output_file}' (使用编码: {args.encoding})。")
        except IOError as e:
            print(f"错误: 写入文件 '{args.output_file}' 时发生 IO 错误: {e}", file=sys.stderr)
            sys.exit(1)
        except UnicodeEncodeError as e:
            print(f"错误: 使用编码 '{args.encoding}' 编码内容到文件 '{args.output_file}' 失败: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 如果未指定输出文件，则打印到标准输出
        # print 函数会使用 sys.stdout.encoding (通常由 PYTHONIOENCODING 环境变量或区域设置决定)
        try:
            print(cleaned_content)
        except UnicodeEncodeError as e:
            # 这种情况比较少见，但如果终端编码不支持某些字符可能会发生
            print(f"错误: 打印到标准输出时发生编码错误: {e}", file=sys.stderr)
            print(f"提示: 尝试将输出重定向到文件，或检查您的终端编码设置。", file=sys.stderr)
            sys.exit(1)

if __name__ == '__main__':
    main()