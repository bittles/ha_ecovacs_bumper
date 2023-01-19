#import hashlib
#import time
#import requests
import os
#from base64 import b64decode, b64encode
#from collections import OrderedDict
from sleekxmppfs.xmlstream import ET
from sleekxmppfs.exceptions import XMPPError

#from . import sucks_api
from .sucks_mqtt import EcoVacsIOTMQ
from .sucks_xmpp import EcoVacsXMPP

from .sucks_const import *

import logging
LOGGER = logging.getLogger(__name__)

class EventEmitter(object):
    """A very simple event emitting system."""
    def __init__(self):
        self._subscribers = []

    def subscribe(self, callback):
        listener = EventListener(self, callback)
        self._subscribers.append(listener)
        return listener

    def unsubscribe(self, listener):
        self._subscribers.remove(listener)

    def notify(self, event):
        for subscriber in self._subscribers:
            subscriber.callback(event)

class EventListener(object):
    """Object that allows event consumers to easily unsubscribe from events."""
    def __init__(self, emitter, callback):
        self._emitter = emitter
        self.callback = callback

    def unsubscribe(self):
        self._emitter.unsubscribe(self)

class VacBot():
    # switched verify and monitor just to be consistent
    def __init__(self, user, domain, resource, secret, vacuum, continent, server_address=None, verify_ssl=True, monitor=False):
        self.vacuum = vacuum
        self.server_address = server_address
        # If True, the VacBot object will handle keeping track of all statuses,
        # including the initial request for statuses, and new requests after the
        # VacBot returns from being offline. It will also cause it to regularly
        # request component lifespans
        self._monitor = monitor
        self._failed_pings = 0
        # These three are representations of the vacuum state as reported by the API
        self.clean_status = None
        self.charge_status = None
        self.battery_status = None
        # This is an aggregate state managed by the sucks library, combining the clean and charge events to a single state
        self.vacuum_status = None
        self.fan_speed = None
        # Populated by component Lifespan reports
        self.components = {}
        self.statusEvents = EventEmitter()
        self.batteryEvents = EventEmitter()
        self.lifespanEvents = EventEmitter()
        self.errorEvents = EventEmitter()
        #Set none for clients to start
        self.xmpp = None
        self.iotmq = None
        if not vacuum['iotmq']:
            self.xmpp = EcoVacsXMPP(user, domain, resource, secret, continent, vacuum, server_address)
            #Uncomment line to allow unencrypted plain auth
            #self.xmpp['feature_mechanisms'].unencrypted_plain = True
            self.xmpp.subscribe_to_ctls(self._handle_ctl)
        else:
            self.iotmq = EcoVacsIOTMQ(user, domain, resource, secret, continent, vacuum, server_address, verify_ssl=verify_ssl)
            self.iotmq.subscribe_to_ctls(self._handle_ctl)
            #The app still connects to XMPP as well, but only issues ping commands.
            #Everything works without XMPP, so leaving the below commented out.
            #self.xmpp = EcoVacsXMPP(user, domain, resource, secret, continent, vacuum, server_address)
            #Uncomment line to allow unencrypted plain auth
            #self.xmpp['feature_mechanisms'].unencrypted_plain = True
            #self.xmpp.subscribe_to_ctls(self._handle_ctl)            

    def connect_and_wait_until_ready(self):
        if not self.vacuum['iotmq']:
            self.xmpp.connect_and_wait_until_ready()
            self.xmpp.schedule('Ping', 300, lambda: self.send_ping(), repeat=True)
        else:
            self.iotmq.connect_and_wait_until_ready()
            self.iotmq.schedule(30, self.send_ping)
            #self.xmpp.connect_and_wait_until_ready() #Leaving in case xmpp is given to iotmq in the future
        if self._monitor:
            # Do a first ping, which will also fetch initial statuses if the ping succeeds
            self.send_ping()
            if not self.vacuum['iotmq']:
                self.xmpp.schedule('Components', 3600, lambda: self.refresh_components(), repeat=True)
            else:
                self.iotmq.schedule(3600,self.refresh_components)

    def _handle_ctl(self, ctl):
        method = '_handle_' + ctl['event']
        if hasattr(self, method):
            getattr(self, method)(ctl)

    def _handle_error(self, event):
        if 'error' in event or 'errs' in event:
            error = '' # init error var so it's available outside of first if loop
            if 'error' in event:
                error = event['error']
            elif 'errs' in event:
                error = event['errs']
            self.errorEvents.notify(error)
            LOGGER.error("*** error = " + error)

#        if not error == '':


# Errors
# The bot broadcasts error codes for a number of cases.

# <ctl td="error" error="BatteryLow" errno="101"></ctl>

# The latest error can be requested like so:

# Request <ctl td="GetError" />
# Response <ctl ret="ok" errs="100"/>
# However in some cases the robot sends to code 100 shortly after an error has occurred, meaning that we cannot trust the GetError request to contain the last relevant error. For example, if the robot gets stuck it broadcasts 102 HostHang, then proceeds to stop and broadcasts 100 NoError.

# Known error codes

# 100 NoError: Robot is operational
# 101 BatteryLow: Low battery
# 102 HostHang: Robot is stuck
# 103 WheelAbnormal: Wheels are not moving as expected
# 104 DownSensorAbnormal: Down sensor is getting abnormal values
# 110 NoDustBox: Dust Bin Not installed
# These codes are taken from model M81 Pro. Error codes may differ between models.


    def _handle_life_span(self, event):
        type = event['type']
        try:
            type = COMPONENT_FROM_ECOVACS[type]
        except KeyError:
            LOGGER.warning("Unknown component type: '" + type + "'")
        if 'val' in event:
            lifespan = int(event['val']) / 100
            LOGGER.info("**********Component " + type + " has lifespan of " + str(lifespan) + ".")
        else:
            lifespan = int(event['left']) / 60  #This works for a D901
        self.components[type] = lifespan
        lifespan_event = {'type': type, 'lifespan': lifespan}
        self.lifespanEvents.notify(lifespan_event)
        LOGGER.info("*** life_span " + type + " = " + str(lifespan))

    def _handle_clean_report(self, event):
        type = event['type']
        try:
            type = CLEAN_MODE_FROM_ECOVACS[type]
            if self.vacuum['iotmq']: #Was able to parse additional status from the IOTMQ, may apply to XMPP too
                statustype = event['st']
                statustype = CLEAN_ACTION_FROM_ECOVACS[statustype]
                if statustype == CLEAN_ACTION_STOP or statustype == CLEAN_ACTION_PAUSE:
                    type = statustype
        except KeyError:
            LOGGER.warning("Unknown cleaning status '" + type + "'")
        self.clean_status = type
        self.vacuum_status = type
        fan = event.get('speed', None)
        if fan is not None:
            try:
                fan = FAN_SPEED_FROM_ECOVACS[fan]
            except KeyError:
                LOGGER.warning("Unknown fan speed: '" + fan + "'")
        self.fan_speed = fan
        self.statusEvents.notify(self.vacuum_status)
        if self.fan_speed:
            LOGGER.info("*** clean_status = " + self.clean_status + " fan_speed = " + self.fan_speed)
        else:
            LOGGER.info("*** clean_status = " + self.clean_status + " fan_speed = None")

    def _handle_battery_info(self, iq):
        try:
            self.battery_status = float(iq['power']) / 100
        except ValueError:
            LOGGER.warning("couldn't parse battery status " + ET.tostring(iq))
        else:
            self.batteryEvents.notify(self.battery_status)
            LOGGER.info("*** battery_status = {:.0%}".format(self.battery_status))

    def _handle_charge_state(self, event):
        if 'type' in event:
            status = event['type']
        elif 'errno' in event: #Handle error
            if event['ret'] == 'fail' and event['errno'] == '8': #Already charging
                status = 'slot_charging'
            elif event['ret'] == 'fail' and event['errno'] == '5': #Busy with another command
                status = 'idle'
            elif event['ret'] == 'fail' and event['errno'] == '3': #Bot in stuck state, example dust bin out
                status = 'idle'
            else: 
                status = 'idle' #Fall back to Idle status
                LOGGER.error("Unknown charging status '" + event['errno'] + "'") #Log this so we can identify more errors    
        try:
            status = CHARGE_MODE_FROM_ECOVACS[status]
        except KeyError:
            LOGGER.warning("Unknown charging status '" + status + "'")
        self.charge_status = status
        if status != 'idle' or self.vacuum_status == 'charging':
            # We have to ignore the idle messages, because all it means is that it's not
            # currently charging, in which case the clean_status is a better indicator
            # of what the vacuum is currently up to.
            self.vacuum_status = status
            self.statusEvents.notify(self.vacuum_status)
        LOGGER.info("*** charge_status = " + self.charge_status)

    def _vacuum_address(self):
        if not self.vacuum['iotmq']:
            return self.vacuum['did'] + '@' + self.vacuum['class'] + '.ecorobot.net/atom'
        else:
            return self.vacuum['did'] #IOTMQ only uses the did

    @property
    def is_charging(self) -> bool:
        return self.vacuum_status in CHARGING_STATES

    @property
    def is_cleaning(self) -> bool:
        return self.vacuum_status in CLEANING_STATES

    def send_ping(self):
        try:
            if not self.vacuum['iotmq']:
                self.xmpp.send_ping(self._vacuum_address())
            elif self.vacuum['iotmq']: 
                if not self.iotmq.send_ping():
                    raise RuntimeError()
        except XMPPError as err:
            LOGGER.warning("Ping did not reach VacBot. Will retry.")
            LOGGER.error("*** Error type: " + err.etype)
            LOGGER.error("*** Error condition: " + err.condition)
            self._failed_pings += 1
            if self._failed_pings >= 4:
                self.vacuum_status = 'offline'
                self.statusEvents.notify(self.vacuum_status)
        except RuntimeError as err:
            LOGGER.warning("Ping did not reach VacBot. Will retry.")
            self._failed_pings += 1
            if self._failed_pings >= 4:
                self.vacuum_status = 'offline'
                self.statusEvents.notify(self.vacuum_status)  
        else:
            self._failed_pings = 0
            if self._monitor:
                # If we don't yet have a vacuum status, request initial statuses again now that the ping succeeded
                if self.vacuum_status == 'offline' or self.vacuum_status is None:
                    self.request_all_statuses()
            else:
                # If we're not auto-monitoring the status, then just reset the status to None, which indicates unknown
                if self.vacuum_status == 'offline':
                    self.vacuum_status = None
                    self.statusEvents.notify(self.vacuum_status)

    def refresh_components(self):
        try:
            self.run(GetLifeSpan('main_brush'))
            self.run(GetLifeSpan('side_brush'))
            self.run(GetLifeSpan('filter'))
        except XMPPError as err:
            LOGGER.warning("Component refresh requests failed to reach VacBot. Will try again later.")
            LOGGER.error("*** Error type: " + err.etype)
            LOGGER.error("*** Error condition: " + err.condition)

    def refresh_statuses(self):
        try:
            self.run(GetCleanState())
            self.run(GetChargeState())
            self.run(GetBatteryState())
        except XMPPError as err:
            LOGGER.warning("Initial status requests failed to reach VacBot. Will try again on next ping.")
            LOGGER.error("*** Error type: " + err.etype)
            LOGGER.error("*** Error condition: " + err.condition)

    def request_all_statuses(self):
        self.refresh_statuses()
        self.refresh_components()

    def send_command(self, action):
        if not self.vacuum['iotmq']:
            self.xmpp.send_command(action.to_xml(), self._vacuum_address()) 
        else:
            #IOTMQ issues commands via RestAPI, and listens on MQTT for status updates         
            self.iotmq.send_command(action, self._vacuum_address())  #IOTMQ devices need the full action for additional parsing

    def run(self, action):
            self.send_command(action) 

    def disconnect(self, wait=False):
        if not self.vacuum['iotmq']:
            self.xmpp.disconnect(wait=wait)
        else:
            self.iotmq._disconnect()
            #self.xmpp.disconnect(wait=wait) #Leaving in case xmpp is added to iotmq in the future

class VacBotCommand:
    ACTION = {
        'forward': 'forward',
        'backward': 'backward',
        'left': 'SpinLeft',
        'right': 'SpinRight',
        'turn_around': 'TurnAround',
        'stop': 'stop'
    }

    def __init__(self, name, args=None, **kwargs):
        if args is None:
            args = {}
        self.name = name
        self.args = args

    def to_xml(self):
        ctl = ET.Element('ctl', {'td': self.name})
        for key, value in self.args.items():
            if type(value) is dict:
                inner = ET.Element(key, value)
                ctl.append(inner)
            elif type(value) is list:
                for item in value:
                    ixml = self.listobject_to_xml(key, item)
                    ctl.append(ixml)
            else:
                ctl.set(key, value)
        return ctl

    def __str__(self, *args, **kwargs):
        return self.command_name() + " command"

    def command_name(self):
        return self.__class__.__name__.lower()

    def listobject_to_xml(self, tag, conv_object):
        rtnobject = ET.Element(tag) 
        if type(conv_object) is dict:
            for key, value in conv_object.items():
                rtnobject.set(key, value)
        else:
            rtnobject.set(tag, conv_object)
        return rtnobject

class Clean(VacBotCommand):
    def __init__(self, mode='auto', speed='normal', iotmq=False, action='start',terminal=False, **kwargs):
        if kwargs == {}:
            #Looks like action is needed for some bots, shouldn't affect older models
            super().__init__('Clean', {'clean': {'type': CLEAN_MODE_TO_ECOVACS[mode], 'speed': FAN_SPEED_TO_ECOVACS[speed],'act': CLEAN_ACTION_TO_ECOVACS[action]}})
        else:
            initcmd = {'type': CLEAN_MODE_TO_ECOVACS[mode], 'speed': FAN_SPEED_TO_ECOVACS[speed]}
            for kkey, kvalue in kwargs.items():
                initcmd[kkey] = kvalue
            super().__init__('Clean', {'clean': initcmd})

class Edge(Clean):
    def __init__(self):
        super().__init__('edge', 'high')

class Spot(Clean):
    def __init__(self):
        super().__init__('spot', 'high')

class Stop(Clean):
    def __init__(self):
        super().__init__('stop', 'normal')

class SpotArea(Clean):
    def __init__(self, action='start', area='', map_position='', cleanings='1'):
        if area != '': #For cleaning specified area
            super().__init__('spot_area', 'normal', act=CLEAN_ACTION_TO_ECOVACS[action], mid=area)
        elif map_position != '': #For cleaning custom map area, and specify deep amount 1x/2x
            super().__init__('spot_area' ,'normal',act=CLEAN_ACTION_TO_ECOVACS[action], p=map_position, deep=cleanings)
        else:
            #no valid entries
            raise ValueError("must provide area or map_position for spotarea clean")

class Charge(VacBotCommand):
    def __init__(self):
        super().__init__('Charge', {'charge': {'type': CHARGE_MODE_TO_ECOVACS['return']}})

class Move(VacBotCommand):
    def __init__(self, action):
        super().__init__('Move', {'move': {'action': self.ACTION[action]}})

class PlaySound(VacBotCommand):
    def __init__(self, sid="0"):
        super().__init__('PlaySound', {'sid': sid})

class GetCleanState(VacBotCommand):
    def __init__(self):
        super().__init__('GetCleanState')

class GetChargeState(VacBotCommand):
    def __init__(self):
        super().__init__('GetChargeState')

class GetBatteryState(VacBotCommand):
    def __init__(self):
        super().__init__('GetBatteryInfo')

class GetLifeSpan(VacBotCommand):
    def __init__(self, component):
        super().__init__('GetLifeSpan', {'type': COMPONENT_TO_ECOVACS[component]})

class SetTime(VacBotCommand):
    def __init__(self, timestamp, timezone):
        super().__init__('SetTime', {'time': {'t': timestamp, 'tz': timezone}})