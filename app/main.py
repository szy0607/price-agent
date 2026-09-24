from fastapi import FastAPI
from app.core.errors import register_exception_handlers
from app.router.log_in import auth_router
app = FastAPI()
register_exception_handlers(app)
app.include_router(auth_router)

