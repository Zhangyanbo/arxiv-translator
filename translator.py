import json
from google import genai
from google.genai import types
from pydantic import BaseModel
from tqdm import tqdm
from string import Template
from texsplit import latex_cut


system_prompt = """你是一个专业的翻译家，擅长将 LaTeX 文档翻译成中文。请确保翻译准确，并保留 LaTeX 语法结构。
用户会提供 LaTeX 文档的**片段**，你需要将这些片段翻译成通顺的中文。请注意以下几点：

翻译成通顺的中文，不要有翻译腔，不要有长句、从句、被动句（碰到了要在不改变原义的前提下修改）。\
保留原来所有的latex格式，不要修改公式。遇到新的特殊名词时，在括号里注上英文原文。\
同时注意，不要翻译原文的label、index等代码相关的东西，保持原样。

对于汉语的语法特点，请**务必**遵循以下所有原则，以翻译出地道的中文，这非常重要：

# 第一性原则
1) 形合（hypotaxis）↔ 意合（parataxis）  
   英文偏形合：用显式从属标记在同一句承载层级；中文偏意合：依靠语序与语义顺承，短句更自然。⇒ 需要时把“句内层级”外化为顺承或并列的短句。

2) 线性化（linearization）：分枝方向 + 依存距离最小化（Dependency Length Minimization, DLM）  
   英文多右分枝，容忍长距离依存；中文多修饰前置，倾向就近依存。⇒ 把重修饰前移或拆句，限制中心嵌套（center-embedding）≤2 层。

# 语法规则
1) 后置修饰 → 前置“的”结构；过长就拆句。  
   例：“the method that we propose …” → “我们提出的**方法**…”
2) 非限定与从属结构（to/-ing/-ed、状语从句等） → 明确的目的/方式/条件/因果等分句；避免尾部连串分词。
3) 减少名词化（de-nominalization）：能动词化就动词化；保持动词—宾语就近（符合 DLM）。
4) 话题—评述与可恢复省略（topic chain / pro-drop）：上下文允许时，省略重复主语/宾语，以短句串联。
5) 当长距离或深嵌套影响可读性时，优先改写为顺承/分句，确保核心谓词与论元相邻。
"""

template = """$latex
-----
对于汉语的语法特点，请**务必**遵循以下所有原则，以翻译出地道的中文，这非常重要：

# 第一性原则
1) 形合（hypotaxis）↔ 意合（parataxis）  
   英文偏形合：用显式从属标记在同一句承载层级；中文偏意合：依靠语序与语义顺承，短句更自然。⇒ 需要时把“句内层级”外化为顺承或并列的短句。

2) 线性化（linearization）：分枝方向 + 依存距离最小化（Dependency Length Minimization, DLM）  
   英文多右分枝，容忍长距离依存；中文多修饰前置，倾向就近依存。⇒ 把重修饰前移或拆句，限制中心嵌套（center-embedding）≤2 层。

# 语法规则
1) 后置修饰 → 前置“的”结构；过长就拆句。  
   例：“the method that we propose …” → “我们提出的**方法**…”
2) 非限定与从属结构（to/-ing/-ed、状语从句等） → 明确的目的/方式/条件/因果等分句；避免尾部连串分词。
3) 减少名词化（de-nominalization）：能动词化就动词化；保持动词—宾语就近（符合 DLM）。
4) 话题—评述与可恢复省略（topic chain / pro-drop）：上下文允许时，省略重复主语/宾语，以短句串联。
5) 当长距离或深嵌套影响可读性时，优先改写为顺承/分句，确保核心谓词与论元相邻。
"""

class Translation(BaseModel):
    latex: str


class Translator:
    def __init__(self, client, model="gemini-2.5-flash"):
        self.client = client
        self.model = model
        self.chat = client.chats.create(
                             model=self.model, 
                             config=types.GenerateContentConfig(
                                system_instruction=system_prompt,
                                response_mime_type="application/json",
                                response_schema=Translation,
                                thinking_config=types.ThinkingConfig(thinking_budget=1024)
                             )
                          )
        self.translated = []
        self.template = Template(template)
       
    def append(self, eng: str, ch: str):
        """将翻译结果添加到已翻译列表中"""
        self.translated.append({
              "english": eng,
              "chinese": ch
        })
 
    def translate(self, text: str) -> str:
        """将 LaTeX 文档片段翻译成中文"""
        message = self.template.substitute(latex=text)
        response = self.chat.send_message(message)
        text_chinese = json.loads(response.candidates[0].content.parts[0].text)['latex']
        self.append(eng=text, ch=text_chinese)
        return response
 
    @property
    def chinese(self) -> str:
        """获取所有翻译结果的中文文本"""
        return "\n".join([item['chinese'] for item in self.translated])


def create_report(total_prompt, cached, reasoning, output):
    return f"input: {total_prompt-cached} + [{cached} cached] -> output: [{reasoning}] + {output}"

def parse_usage(res):
    usage = res.usage_metadata
    total_prompt = usage.prompt_token_count

    cached = usage.cached_content_token_count
    cached = 0 if cached is None else cached

    reasoning = usage.thoughts_token_count
    reasoning = 0 if reasoning is None else reasoning

    output = usage.candidates_token_count

    return create_report(total_prompt, cached, reasoning, output)

class LaTeXTranslator:
    def __init__(self, client, model="gemini-2.5-flash", chunk_size=3000, save_path='./translated.text'):
        self.translator = Translator(client, model)
        self.chunk_size = chunk_size
        self.save_path = save_path
    
    @property
    def translated(self) -> str:
        main_text = self.translator.chinese
        return self.template.replace('$document', main_text)
    
    def save(self):
        """将翻译结果保存到文件"""
        with open(self.save_path, 'w', encoding='utf-8') as f:
            f.write(self.translated)
    
    def translate(self, latex: str, max_n:int=None) -> str:
        latex_chunks = latex_cut(latex, self.chunk_size)
        self.template, self.chunks = latex_chunks['template'], latex_chunks['chunks']

        if max_n is not None:
            self.chunks = self.chunks[:max_n]

        pbar = tqdm(self.chunks, desc="Translating")
        for chunk in pbar:
            response = self.translator.translate(chunk)
            usage_info = parse_usage(response)
            pbar.set_postfix_str(usage_info)
            self.save()