from fastapi import APIRouter, Depends
from app.services.ai_service import AIService
from pydantic import BaseModel

router = APIRouter()

class ChatMessage(BaseModel):
    message: str

@router.post("/")
async def send_message(data: ChatMessage):
    service = AIService()
    response = await service.chat(data.message)
    return {"message": response}
