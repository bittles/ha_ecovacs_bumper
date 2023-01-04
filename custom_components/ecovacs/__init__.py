"""Support for Ecovacs Deebot vacuums."""
import random
import string
##import asyncio ## to do will need to convert to slixmpp to do this i believe

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL, # added
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol
#just included the modified sucks in component
from .sucksbumper import EcoVacsAPI, VacBot
from .const import (
    ECOVACS_DEVICES,
    DOMAIN,
    CONF_COUNTRY,
    CONF_CONTINENT,
    CONF_BUMPER,
    CONF_BUMPER_SERVER,
    SERVER_ADDRESS,
    _LOGGER
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_COUNTRY): vol.All(vol.Lower, cv.string),
                vol.Required(CONF_CONTINENT): vol.All(vol.Lower, cv.string),
                vol.Optional(CONF_BUMPER, default=False): cv.boolean,
                vol.Optional(CONF_BUMPER_SERVER): cv.string,
                vol.Optional(CONF_VERIFY_SSL, default=True): cv.boolean, # can probably get rid of this and set verify ssl false if bumper true
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
    _LOGGER.debug("Creating new Ecovacs component")

    hass.data[ECOVACS_DEVICES] = []
    # if we're using bumper then define the server address
    if CONF_BUMPER == True:
        SERVER_ADDRESS = (config[DOMAIN].get(CONF_BUMPER_SERVER), 5223)
    # if not make sure it's null
    else:
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
            SERVER_ADDRESS, # include server address in class, if it's null shoul be no effect
            config[DOMAIN].get(CONF_VERIFY_SSL), # verify ssl or not
            monitor=True,
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
