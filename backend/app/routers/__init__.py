from fastapi import APIRouter

from app.routers import (
    accounts,
    dashboard,
    entries,
    quarantine,
    settle,
    split_proofs,
    verify,
)

api = APIRouter(prefix="/api")
api.include_router(dashboard.router)
api.include_router(accounts.router)
api.include_router(entries.router)
api.include_router(settle.router)
api.include_router(quarantine.router)
api.include_router(verify.router)
api.include_router(split_proofs.router)
