from fastapi import APIRouter
log_in_router = APIRouter(
    prefix="/login",
    tags=["login"]
)
@log_in_router.post("/")
async def login():
    pass
