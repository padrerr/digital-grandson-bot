from aiogram import Router

from . import (
    start,
    family,
    elderly_manage,
    prescription,
    account,
    actions,
    notes,
    analytics,
    help_reports,
    faq,
    admin,
    privacy,
    messages,
    alerts,
    fallback,
)


def setup_routers() -> Router:
    root = Router()
    for module in (
        start,
        family,
        elderly_manage,
        prescription,
        account,
        actions,
        notes,
        analytics,
        help_reports,
        faq,
        admin,
        privacy,
        messages,
        alerts,
        fallback,
    ):
        root.include_router(module.router)
    return root