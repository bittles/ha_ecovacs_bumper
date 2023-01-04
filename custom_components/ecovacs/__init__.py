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
from .sucks import EcoVacsAPI, VacBot
from .const import (
    ECOVACS_DEVICES,
    DOMAIN,
    CONF_CONTINENT,
    LOGGER
)

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

def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ecovacs component."""
    LOGGER.debug("Creating new Ecovacs component")
    hass.data[ECOVACS_DEVICES] = []
    SERVER_ADDRESS = None

    ecovacs_api = EcoVacsAPI(
        ECOVACS_API_DEVICEID,
        config[DOMAIN].get(CONF_USERNAME),
        EcoVacsAPI.md5(config[DOMAIN].get(CONF_PASSWORD)),
        config[DOMAIN].get(CONF_COUNTRY),
        config[DOMAIN].get(CONF_CONTINENT),
        config[DOMAIN].get(CONF_VERIFY_SSL), # add to class call
    )

    devices = ecovacs_api.devices()
    LOGGER.debug("Ecobot devices: %s", devices)

    for device in devices:
        LOGGER.info(
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
            SERVER_ADDRESS, # include server address in class, if it's null should be no effect
            config[DOMAIN].get(CONF_VERIFY_SSL), # add to class call
            monitor=True
        )
        hass.data[ECOVACS_DEVICES].append(vacbot)

    def stop(event: object) -> None:
        """Shut down open connections to Ecovacs XMPP server."""
        for device in hass.data[ECOVACS_DEVICES]:
            LOGGER.info(
                "Shutting down connection to Ecovacs device %s",
                device.vacuum.get("did"),
            )
            device.disconnect()

    # Listen for HA stop to disconnect.
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop)
    if hass.data[ECOVACS_DEVICES]:
        LOGGER.debug("Starting vacuum components")
        discovery.load_platform(hass, Platform.VACUUM, DOMAIN, {}, config)
    return True
