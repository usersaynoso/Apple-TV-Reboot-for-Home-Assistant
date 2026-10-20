"""Diagnostic sensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfFrequency
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AppleTvConfigEntry
from .entity import AppleTvEntity


@dataclass(frozen=True, kw_only=True)
class AppleTvSensorDescription(SensorEntityDescription):
    key_in_data: str


SENSORS = (
    AppleTvSensorDescription(
        key="build", key_in_data="build", name="tvOS build", icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AppleTvSensorDescription(
        key="wifi_band", key_in_data="wifi_band", name="Wi-Fi band", icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AppleTvSensorDescription(
        key="wifi_channel", key_in_data="wifi_channel", name="Wi-Fi channel", icon="mdi:wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    AppleTvSensorDescription(
        key="wifi_bandwidth", key_in_data="wifi_bandwidth", name="Wi-Fi channel width",
        icon="mdi:wifi", native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AppleTvConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(AppleTvSensor(coordinator, description) for description in SENSORS)


class AppleTvSensor(AppleTvEntity, SensorEntity):
    entity_description: AppleTvSensorDescription

    def __init__(self, coordinator, description: AppleTvSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return (self.coordinator.data or {}).get(self.entity_description.key_in_data)
