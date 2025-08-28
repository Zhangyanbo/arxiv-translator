from translator import LaTeXTranslator
from google import genai
import os
from dotenv import load_dotenv
from pathlib import Path

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Translate LaTeX documents using Gemini AI.")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash", help="Model to use for translation.")
    parser.add_argument("--source", type=str, required=True, help="Path to the LaTeX source file to translate.")
    parser.add_argument("--chunk_size", type=int, default=3000, help="Size of each LaTeX chunk to translate.")
    parser.add_argument("--output", type=str, default='translated.txt', help="Path to save the translated text.")


    args = parser.parse_args()
    HERE = Path(__file__).resolve().parent
    load_dotenv(HERE / ".env")
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    translator = LaTeXTranslator(
        client, 
        model=args.model,
        chunk_size=args.chunk_size, 
        save_path=args.output)

    source = open(args.source, 'r', encoding='utf-8').read()
    translator.translate(source)