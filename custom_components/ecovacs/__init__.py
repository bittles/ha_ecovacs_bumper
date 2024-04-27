"""Support for Ecovacs Deebot vacuums."""
import random
import string
#import asyncio ## to do will need to convert to slixmpp to do this i believe

from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_COUNTRY,
    CONF_VERIFY_SSL,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
#use local sucks
from .sucks import VacBot
from .sucks_api import EcoVacsAPI
from .const import *

import logging
LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_COUNTRY): vol.All(vol.Lower, cv.string),
                vol.Required(CONF_CONTINENT): vol.All(vol.Lower, cv.string),
                vol.Optional(CONF_VERIFY_SSL, default=True): cv.boolean, # can probably get rid of this and set verify ssl false if
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# Generate a random device ID on each bootup
ECOVACS_API_DEVICEID = "".join(
    random.choice(string.ascii_uppercase + string.digits) for _ in range(8)
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ecovacs component."""
    LOGGER.debug("Creating new Ecovacs component")
    def get_devices() -> list[VacBot]:
        ecovacs_api = EcoVacsAPI(
            ECOVACS_API_DEVICEID,
            config[DOMAIN].get(CONF_USERNAME),
            EcoVacsAPI.md5(config[DOMAIN].get(CONF_PASSWORD)),
            config[DOMAIN].get(CONF_COUNTRY),
            config[DOMAIN].get(CONF_CONTINENT),
        )
        ecovacs_devices = ecovacs_api.devices()
        _LOGGER.debug("Ecobot devices: %s", ecovacs_devices)

    SERVER_ADDRESS = None

        devices: list[VacBot] = []
        for device in ecovacs_devices:
            _LOGGER.info(
                "Discovered Ecovacs device on account: %s with nickname %s",
                device.get("did"),
                device.get("nick"),
            )
            vacbot = VacBot(
                ecovacs_api.uid,
                ecovacs_api.REALM,
                ecovacs_api.resource,
                ecovacs_api.user_access_token,
                device,
                config[DOMAIN].get(CONF_CONTINENT).lower(),
                config[DOMAIN].get(CONF_VERIFY_SSL), # add to class call
                monitor=True,
            )

            devices.append(vacbot)
        return devices

    hass.data[ECOVACS_DEVICES] = await hass.async_add_executor_job(get_devices)

    async def async_stop(event: object) -> None:
        """Shut down open connections to Ecovacs XMPP server."""
        devices: list[VacBot] = hass.data[ECOVACS_DEVICES]
        for device in devices:
            LOGGER.info(
                "Shutting down connection to Ecovacs device %s",
                device.vacuum.get("did"),
            )
            await hass.async_add_executor_job(device.disconnect)

    # Listen for HA stop to disconnect.
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)
    if hass.data[ECOVACS_DEVICES]:
        LOGGER.debug("Starting vacuum components")
        hass.async_create_task(
            discovery.async_load_platform(hass, Platform.VACUUM, DOMAIN, {}, config)
        )
    return True
