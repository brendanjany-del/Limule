"""Routeur principal regroupant tous les sous-routeurs API."""

from fastapi import APIRouter

from app.api.specifications import router as specifications_router
from app.api.flux import router as flux_router
from app.api.data import router as data_router

api_router = APIRouter()
api_router.include_router(specifications_router)
api_router.include_router(flux_router)
api_router.include_router(data_router)
