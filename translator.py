import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env in local development.
load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL")
MODEL_NAME = os.getenv("OPENROUTER_MODEL")

if not API_KEY:
    raise RuntimeError("Missing required environment variable: OPENROUTER_API_KEY")
if not BASE_URL:
    raise RuntimeError("Missing required environment variable: OPENROUTER_BASE_URL")
if not MODEL_NAME:
    raise RuntimeError("Missing required environment variable: OPENROUTER_MODEL")

client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY
)

def translate_text(text, target_language="Chinese"):
    """
    调用 LLM 进行翻译
    """
    system_prompt = f"You are a professional translator. Translate the user's text into {target_language}. Preserve meaning, tone, and intent. Return only the translated text."
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        user_input = sys.argv[1]
        result = translate_text(user_input, target_language="Chinese")
        print("原文:", user_input)
        print("翻译结果:", result)
    else:
        print("请在命令行输入要翻译的内容，vercel login例如: python translator.py 'How are you?'")