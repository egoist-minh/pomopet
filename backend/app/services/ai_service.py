import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.system_prompt = """You are Pomo, a friendly AI pet companion that helps users stay productive.
You provide advice on:
- Focus techniques and time management
- Task prioritization
- Dealing with distractions
- Motivation and encouragement
- Work-life balance

Keep responses concise, friendly, and actionable. Use a warm, supportive tone."""

    async def chat(self, message: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=200,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Sorry, I encountered an error: {str(e)}"
