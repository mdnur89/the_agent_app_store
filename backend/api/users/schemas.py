from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    email: str | None
    username: str | None
    is_admin: bool
    telegram_linked: bool


class TelegramLinkCodeOut(BaseModel):
    code: str
    expires_at: str
