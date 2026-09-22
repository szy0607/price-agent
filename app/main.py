from fastapi import FastAPI
from app.core.errors import register_exception_handlers
app = FastAPI()
register_exception_handlers(app)
