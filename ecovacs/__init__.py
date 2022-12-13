"""Support for Ecovacs Deebot vacuums."""
import logging
import random
import string

from .sucksbumper import EcoVacsAPI, VacBot
import voluptuous as vol

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ecovacs"

CONF_COUNTRY = "country"
CONF_CONTINENT = "continent"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_COUNTRY): vol.All(vol.Lower, cv.string),
                vol.Required(CONF_CONTINENT): vol.All(vol.Lower, cv.string),
                vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean, 
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

ECOVACS_DEVICES = "ecovacs_devices"

# Generate a random device ID on each bootup
ECOVACS_API_DEVICEID = "".join(
    random.choice(string.ascii_uppercase + string.digits) for _ in range(8)
)


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ecovacs component."""
    _LOGGER.debug("Creating new Ecovacs component")

    hass.data[ECOVACS_DEVICES] = []

    ecovacs_api = EcoVacsAPI(
        ECOVACS_API_DEVICEID,
        config[DOMAIN].get(CONF_USERNAME),
        EcoVacsAPI.md5(config[DOMAIN].get(CONF_PASSWORD)),
        config[DOMAIN].get(CONF_COUNTRY),
        config[DOMAIN].get(CONF_CONTINENT),
        config[DOMAIN].get(CONF_VERIFY_SSL),
    )

    devices = ecovacs_api.devices()
    _LOGGER.debug("Ecobot devices: %s", devices)

    for device in devices:
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
            monitor=True,
            config[DOMAIN].get(CONF_VERIFY_SSL),
        )
        hass.data[ECOVACS_DEVICES].append(vacbot)

    def stop(event: object) -> None:
        """Shut down open connections to Ecovacs XMPP server."""
        for device in hass.data[ECOVACS_DEVICES]:
            _LOGGER.info(
                "Shutting down connection to Ecovacs device %s",
                device.vacuum.get("did"),
            )
            device.disconnect()

    # Listen for HA stop to disconnect.
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, stop)

    if hass.data[ECOVACS_DEVICES]:
        _LOGGER.debug("Starting vacuum components")
        discovery.load_platform(hass, Platform.VACUUM, DOMAIN, {}, config)

    return True
