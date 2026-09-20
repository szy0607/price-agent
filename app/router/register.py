from fastapi import APIRouter
register_router = APIRouter(
    prefix="/register",
    tags=["register"]
)
@register_router.post("/")
async def register():
    pass
