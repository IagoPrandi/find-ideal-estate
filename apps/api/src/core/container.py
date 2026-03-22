from __future__ import annotations

from dependency_injector import containers, providers
from modules.transport import OTPAdapter, ValhallaAdapter
from modules.transport.service import TransportService
from modules.zones import ZoneService


class ContainerNotInitializedError(RuntimeError):
    """Raised when code tries to resolve services before app startup wiring."""


class AppContainer(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(modules=["api.routes.journeys"])

    config = providers.Configuration()
    redis_client = providers.Dependency()

    valhalla_adapter = providers.Factory(
        ValhallaAdapter,
        base_url=config.valhalla_url,
        redis_client=redis_client,
        timeout_seconds=config.http_timeout_seconds,
    )
    otp_adapter = providers.Factory(
        OTPAdapter,
        base_url=config.otp_url,
        timeout_seconds=config.http_timeout_seconds,
    )

    transport_service = providers.Singleton(TransportService)
    zone_service = providers.Factory(
        ZoneService,
        valhalla_adapter=valhalla_adapter,
        otp_adapter=otp_adapter,
    )


_container: AppContainer | None = None


def set_container(container: AppContainer) -> None:
    global _container
    _container = container


def get_container() -> AppContainer:
    if _container is None:
        raise ContainerNotInitializedError("DI container has not been initialized")
    return _container


def reset_container() -> None:
    global _container
    _container = None
