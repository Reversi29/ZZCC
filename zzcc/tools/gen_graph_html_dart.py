#!/usr/bin/env python3
"""从 graph_template.html 生成 knowledge_graph_html.dart。

目的：完全绕开 Dart 单引号字符串的双重转义陷阱。
之前用 edit/write 工具直接写 Dart 字符串时，\' 和 \/ 的转义反复损坏，
导致 dart2js 编译失败或 JS 语法错误。改为"单一数据源 HTML + 生成器"。

转义规则（Dart 单引号字符串）：
  \\  -> \\\\   反斜杠转反斜杠（必须先做，否则后面的替换会二次转义）
  '   -> \\'   单引号转义
每行加 \n 后缀（除最后一行）

用法: python3 tools/gen_graph_html_dart.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'lib', 'presentation', 'pages', 'square', 'widgets', 'graph_template.html')
DST = os.path.join(os.path.dirname(HERE), 'lib', 'presentation', 'pages', 'square', 'widgets', 'knowledge_graph_html.dart')

def escape_dart(s: str) -> str:
    """把一段文本转成 Dart 单引号字符串的内容（不含外层引号）。

    Dart 单引号字符串里需要转义的字符：
      \\  -> \\\\   反斜杠（必须先做）
      '   -> \\'    单引号
      $   -> \\$    美元符（防插值）
    """
    s = s.replace('\\', '\\\\')
    s = s.replace("'", "\\'")
    s = s.replace('$', '\\$')
    return s

def main() -> int:
    if not os.path.exists(SRC):
        print(f'ERROR: template not found: {SRC}', file=sys.stderr)
        return 1

    with open(SRC, 'r', encoding='utf-8') as f:
        html = f.read()

    # 去掉末尾换行，避免最后一行多一个 \n
    html = html.rstrip('\n')
    lines = html.split('\n')

    out = [
        '// ECharts 知识图谱 HTML — native (InAppWebView) 和 Web (iframe) 共享。',
        '// ⚠️ 本文件由 tools/gen_graph_html_dart.py 自动生成，不要手改。',
        '// 要修改内容请改同目录下的 graph_template.html，然后重新运行生成器。',
        '// 生成命令: cd /Users/mac/ZZCC/zzcc && python3 tools/gen_graph_html_dart.py',
        '//',
        '// 占位符: __ECHARTS_BASE__ 由 Dart 侧在运行时替换为绝对 URL',
        '// （srcdoc iframe 的 location.origin 是字符串 "null"，不能用）。',
        '',
        "const String kGraphHtml =",
    ]

    for i, line in enumerate(lines):
        esc = escape_dart(line)
        if i == 0:
            out.append(f"    '{esc}\\n'")
        elif i == len(lines) - 1:
            # 最后一行：闭合字符串并加分号，全部在同一行（Dart 单引号字符串不能跨行）
            out.append(f"    '{esc}';")
        else:
            out.append(f"    '{esc}\\n'")
    out.append('')

    with open(DST, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))

    print(f'OK: {DST} ({os.path.getsize(DST)} bytes, {len(lines)} HTML lines)')
    return 0

if __name__ == '__main__':
    sys.exit(main())
