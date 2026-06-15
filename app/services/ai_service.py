import os
from openai import OpenAI


def ask_chatgpt(message, knowledge_context=""):
    try:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            return {
                "ok": False,
                "answer": "AI is unavailable. Missing API key."
            }

        client = OpenAI(api_key=api_key)

        system_prompt = f"""
You are a customer support assistant.

Use the supplied knowledge base first.

Knowledge Base:
{knowledge_context}

If the answer exists in the knowledge base,
answer using that information.

If not, answer normally.

Keep answers concise and helpful.
""".strip()

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            temperature=0.3,
            max_tokens=500
        )

        answer = response.choices[0].message.content or ""

        return {
            "ok": True,
            "answer": answer.strip()
        }

    except Exception as e:
        print("OPENAI ERROR:", str(e))

        return {
            "ok": False,
            "answer": "AI is temporarily unavailable."
        }