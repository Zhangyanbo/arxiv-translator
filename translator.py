import json
from google import genai
from google.genai import types
from pydantic import BaseModel
from tqdm import tqdm
from string import Template
from texsplit import latex_cut


grammar = """对于汉语的语法特点，翻译出地道的中文。避免长句、从句、嵌套句式。\
如果碰到原文是这类句子，务必拆分以符合清晰、流畅的现代汉语风格。
"""

system_prompt = f"""你是一个专业的翻译家，擅长将 LaTeX 文档翻译成中文。请确保翻译准确，并保留 LaTeX 语法结构。
用户会提供 LaTeX 文档的**片段**，你需要将这些片段翻译成通顺的中文。请注意以下几点：

翻译成通顺的中文，不要有翻译腔，不要有长句、从句、被动句（碰到了要在不改变原义的前提下修改）。\
保留原来所有的latex格式，不要修改公式。遇到新的特殊名词时，在括号里注上英文原文。\
同时注意，不要翻译原文的label、index等代码相关的东西，保持原样。

{grammar}

你需要输出一个JSON对象，其中包含一个latex字段。其中直接输出翻译结果，不要有任何其他内容，例如用```包裹结果，或是任何其他解释性的内容。

## Latex 格式

确保不改变原有的 LaTeX 语法结构。对于行内公式，确保你正确添加了美元符号 `$`。
"""

template = """$latex
-----
{{grammar}}
"""

class Translation(BaseModel):
   latex: str


class Translator:
   def __init__(self, client, model="gemini-2.5-flash", history=None):
      self.client = client
      self.model = model
      if history is not None:
         history = self.format_history(history)
      self.chat = client.chats.create(
                      model=self.model, 
                      config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=Translation,
                        thinking_config=types.ThinkingConfig(thinking_budget=1024)
                      ),
                      history=history
                    )
      self.translated = []
      self.template = Template(template)
   
   @staticmethod
   def format_history(h):
      from google.genai import types
      history = []

      for item in h:
         if item['role'] in ['user']:
            g_item = types.UserContent(parts=[types.Part(text=item['content'])])
         elif item['role'] in ['assistant', 'model']:
            g_item = types.Content(role="model", parts=[types.Part(text=item['content'])])
         history.append(g_item)

      return history

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
   def __init__(self, client, model="gemini-2.5-flash", chunk_size=3000, save_path='./translated.text', history=None):
      self.translator = Translator(client, model, history=history)
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