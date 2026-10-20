"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .device import AppleTvCoordinator


class AppleTvEntity(CoordinatorEntity[AppleTvCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: AppleTvCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.device = coordinator.device
        self._attr_unique_id = f"{self.device.identifier}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return self.device.device_info
