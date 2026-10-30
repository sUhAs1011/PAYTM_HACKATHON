from fastapi import FastAPI

from app.bill_validation.routes.controller import router as bill_validation_router
from app.credit.routes.controller import router as credit_router
from app.core.logging_config import RequestLoggingMiddleware, configure_logging
from app.price_analysis.routes.controller import router as price_analysis_router

configure_logging()

app = FastAPI(title="ParchaPay AI API")
app.add_middleware(RequestLoggingMiddleware)
app.include_router(bill_validation_router)
app.include_router(price_analysis_router)
app.include_router(credit_router)
