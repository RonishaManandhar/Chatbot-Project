import os
from openai import OpenAI


def ask_chatgpt(message, knowledge_context="", triage_context="", faq_context=""):
    try:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            return {
                "ok": False,
                "answer": "AI is unavailable. Missing API key."
            }

        client = OpenAI(api_key=api_key)

        system_prompt = f"""
You are an AI-powered IT Service Desk assistant.

Use this order:
1. Use FAQ context first.
2. Use Knowledge Base context second.
3. If no direct match is found, use general IT troubleshooting knowledge.
4. If the issue needs account access, security investigation, admin permission, or hardware replacement, recommend creating a support ticket.

Triage Context:
{triage_context}

FAQ Context:
{faq_context}

Knowledge Base Context:
{knowledge_context}

Response rules:
- Give practical step-by-step troubleshooting.
- Keep the answer clear and professional.
- Do not invent company-specific policies.
- Do not claim you performed system actions.
- End by asking whether this solved the issue.
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
            max_tokens=600
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