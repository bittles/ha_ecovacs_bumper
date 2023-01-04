import hashlib
import time
import requests
import os
from base64 import b64decode, b64encode
from collections import OrderedDict
from sleekxmppfs.xmlstream import ET
from sleekxmppfs.exceptions import XMPPError

from .mqtt_ecovacs import EcoVacsIOTMQ
from .xmpp_ecovacs import EcoVacsXMPP

from . import const

def str_to_bool_or_cert(s):
    if s == 'True' or s == True:
        return True
    elif s == 'False' or s == False:
        return False    
    else:
        if not s == None:
            if os.path.exists(s): # User could provide a path to a CA Cert as well, which is useful for Bumper
                if os.path.isfile(s):
                    return s
                else:
                    raise ValueError("Certificate path provided is not a file - {}".format(s))
        raise ValueError("Cannot covert {} to a bool or certificate path".format(s))

class EcoVacsAPI:
    CLIENT_KEY = "eJUWrzRv34qFSaYk"
    SECRET = "Cyu5jcR4zyK6QEPn1hdIGXB5QIDAQABMA0GC"
    PUBLIC_KEY = 'MIIB/TCCAWYCCQDJ7TMYJFzqYDANBgkqhkiG9w0BAQUFADBCMQswCQYDVQQGEwJjbjEVMBMGA1UEBwwMRGVmYXVsdCBDaXR5MRwwGgYDVQQKDBNEZWZhdWx0IENvbXBhbnkgTHRkMCAXDTE3MDUwOTA1MTkxMFoYDzIxMTcwNDE1MDUxOTEwWjBCMQswCQYDVQQGEwJjbjEVMBMGA1UEBwwMRGVmYXVsdCBDaXR5MRwwGgYDVQQKDBNEZWZhdWx0IENvbXBhbnkgTHRkMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDb8V0OYUGP3Fs63E1gJzJh+7iqeymjFUKJUqSD60nhWReZ+Fg3tZvKKqgNcgl7EGXp1yNifJKUNC/SedFG1IJRh5hBeDMGq0m0RQYDpf9l0umqYURpJ5fmfvH/gjfHe3Eg/NTLm7QEa0a0Il2t3Cyu5jcR4zyK6QEPn1hdIGXB5QIDAQABMA0GCSqGSIb3DQEBBQUAA4GBANhIMT0+IyJa9SU8AEyaWZZmT2KEYrjakuadOvlkn3vFdhpvNpnnXiL+cyWy2oU1Q9MAdCTiOPfXmAQt8zIvP2JC8j6yRTcxJCvBwORDyv/uBtXFxBPEC6MDfzU2gKAaHeeJUWrzRv34qFSaYkYta8canK+PSInylQTjJK9VqmjQ'
    MAIN_URL_FORMAT = 'https://eco-{country}-api.ecovacs.com/v1/private/{country}/{lang}/{deviceId}/{appCode}/{appVersion}/{channel}/{deviceType}'
    USER_URL_FORMAT = 'https://users-{continent}.ecouser.net:8000/user.do'
    PORTAL_URL_FORMAT = 'https://portal-{continent}.ecouser.net/api'
    USERSAPI = 'users/user.do'
    IOTDEVMANAGERAPI = 'iot/devmanager.do' # IOT Device Manager - This provides control of "IOT" products via RestAPI, some bots use this instead of XMPP
    PRODUCTAPI = 'pim/product' # Leaving this open, the only endpoint known currently is "Product IOT Map" -  pim/product/getProductIotMap - This provides a list of "IOT" products.  Not sure what this provides the app.
    REALM = 'ecouser.net'

    def __init__(self, device_id, account_id, password_hash, country, continent, verify_ssl=True):
        self.meta = {
            'country': country,
            'lang': 'en',
            'deviceId': device_id,
            'appCode': 'i_eco_e',
            #'appCode': 'i_eco_a' - iphone
            'appVersion': '1.3.5',
            #'appVersion': '1.4.6' - iphone
            'channel': 'c_googleplay',
            #'channel': 'c_iphone', - iphone
            'deviceType': '1'
            #'deviceType': '2' - iphone
        }
        self.verify_ssl = str_to_bool_or_cert(verify_ssl)
        _LOGGER.debug("Setting up EcoVacsAPI")
        self.resource = device_id[0:8]
        self.country = country
        self.continent = continent
        login_info = self.__call_main_api('user/login',
                                          ('account', self.encrypt(account_id)),
                                          ('password', self.encrypt(password_hash)))
        self.uid = login_info['uid']
        self.login_access_token = login_info['accessToken']
        self.auth_code = self.__call_main_api('user/getAuthCode',
                                              ('uid', self.uid),
                                              ('accessToken', self.login_access_token))['authCode']
        login_response = self.__call_login_by_it_token()
        self.user_access_token = login_response['token']
        if login_response['userId'] != self.uid:
            logging.debug("Switching to shorter UID " + login_response['userId'])
            self.uid = login_response['userId']
        logging.debug("EcoVacsAPI connection complete")

    def __sign(self, params):
        result = params.copy()
        result['authTimespan'] = int(time.time() * 1000)
        result['authTimeZone'] = 'GMT-8'
        sign_on = self.meta.copy()
        sign_on.update(result)
        sign_on_text = EcoVacsAPI.CLIENT_KEY + ''.join(
            [k + '=' + str(sign_on[k]) for k in sorted(sign_on.keys())]) + EcoVacsAPI.SECRET
        result['authAppkey'] = EcoVacsAPI.CLIENT_KEY
        result['authSign'] = self.md5(sign_on_text)
        return result

    def __call_main_api(self, function, *args):
        _LOGGER.debug("calling main api {} with {}".format(function, args))
        params = OrderedDict(args)
        params['requestId'] = self.md5(time.time())
        url = (EcoVacsAPI.MAIN_URL_FORMAT + "/" + function).format(**self.meta)
        api_response = requests.get(url, self.__sign(params), verify=self.verify_ssl)
        json = api_response.json()
        _LOGGER.debug("got {}".format(json))
        if json['code'] == '0000':
            return json['data']
        elif json['code'] == '1005':
            _LOGGER.warning("incorrect email or password")
            raise ValueError("incorrect email or password")
        else:
            _LOGGER.error("call to {} failed with {}".format(function, json))
            raise RuntimeError("failure code {} ({}) for call {} and parameters {}".format(
                json['code'], json['msg'], function, args))

    def __call_user_api(self, function, args):
        _LOGGER.debug("calling user api {} with {}".format(function, args))
        params = {'todo': function}
        params.update(args)
        response = requests.post(EcoVacsAPI.USER_URL_FORMAT.format(continent=self.continent), json=params, verify=self.verify_ssl)
        json = response.json()
        _LOGGER.debug("got {}".format(json))
        if json['result'] == 'ok':
            return json
        else:
            _LOGGER.error("call to {} failed with {}".format(function, json))
            raise RuntimeError(
                "failure {} ({}) for call {} and parameters {}".format(json['error'], json['errno'], function, params))

    def __call_portal_api(self, api, function, args, verify_ssl=True, **kwargs):
        if api == self.USERSAPI:
            params = {'todo': function}
            params.update(args)
        else:
            params = {}
            params.update(args)
        _LOGGER.debug("calling portal api {} function {} with {}".format(api, function, params))
        continent = self.continent
        if 'continent' in kwargs:
            continent = kwargs.get('continent')
        url = (EcoVacsAPI.PORTAL_URL_FORMAT + "/" + api).format(continent=continent, **self.meta)
        response = requests.post(url, json=params, verify=verify_ssl)
        json = response.json()
        _LOGGER.debug("got {}".format(json))
        if api == self.USERSAPI:
            if json['result'] == 'ok':
                return json
            elif json['result'] == 'fail':
                if json['error'] == 'set token error.': # If it is a set token error try again
                    if not 'set_token' in kwargs:      
                        _LOGGER.debug("loginByItToken set token error, trying again (2/3)")
                        return self.__call_portal_api(self.USERSAPI, function, args, verify_ssl=verify_ssl, set_token=1)
                    elif kwargs.get('set_token') == 1:
                        _LOGGER.debug("loginByItToken set token error, trying again with ww (3/3)")
                        return self.__call_portal_api(self.USERSAPI, function, args, verify_ssl=verify_ssl, set_token=2, continent="ww")
                    else:
                        _LOGGER.debug("loginByItToken set token error, failed after 3 attempts")
        if api.startswith(self.PRODUCTAPI):
            if json['code'] == 0:
                return json

        else:
            _LOGGER.error("call to {} failed with {}".format(function, json))
            raise RuntimeError(
                "failure {} ({}) for call {} and parameters {}".format(json['error'], json['errno'], function, params))

    def __call_login_by_it_token(self):
        return self.__call_portal_api(self.USERSAPI,'loginByItToken',
                                    {'country': self.meta['country'].upper(),
                                     'resource': self.resource,
                                     'realm': EcoVacsAPI.REALM,
                                     'userId': self.uid,
                                     'token': self.auth_code}
                                    , verify_ssl=self.verify_ssl)

    def getdevices(self):
        return  self.__call_portal_api(self.USERSAPI,'GetDeviceList', {
            'userid': self.uid,
            'auth': {
                'with': 'users',
                'userid': self.uid,
                'realm': EcoVacsAPI.REALM,
                'token': self.user_access_token,
                'resource': self.resource
            }
        }, verify_ssl=self.verify_ssl)['devices']

    def getiotProducts(self):
        return self.__call_portal_api(self.PRODUCTAPI + '/getProductIotMap','', {
            'channel': '',
            'auth': {
                'with': 'users',
                'userid': self.uid,
                'realm': EcoVacsAPI.REALM,
                'token': self.user_access_token,
                'resource': self.resource
            }
        }, verify_ssl=self.verify_ssl)['data']

    def SetIOTDevices(self, devices, iotproducts):
        #Originally added for D900, and not actively used in code now - Not sure what the app checks the items in this list for
        for device in devices: #Check if the device is part of iotProducts
            device['iot_product'] = False
            for iotProduct in iotproducts:
                if device['class'] in iotProduct['classid']:
                    device['iot_product'] = True
                    
        return devices

    def SetIOTMQDevices(self, devices):
        #Added for devices that utilize MQTT instead of XMPP for communication
        for device in devices:
            device['iotmq'] = False
            if device['company'] == 'eco-ng': #Check if the device is part of the list
                device['iotmq'] = True
                    
        return devices

    def devices(self):
        return self.SetIOTMQDevices(self.getdevices())

    @staticmethod
    def md5(text):
        return hashlib.md5(bytes(str(text), 'utf8')).hexdigest()

    @staticmethod
    def encrypt(text):
        from Crypto.PublicKey import RSA
        from Crypto.Cipher import PKCS1_v1_5
        key = RSA.import_key(b64decode(EcoVacsAPI.PUBLIC_KEY))
        cipher = PKCS1_v1_5.new(key)
        result = cipher.encrypt(bytes(text, 'utf8'))
        return str(b64encode(result), 'utf8')

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
        if 'error' in event:
            error = event['error']
        elif 'errs' in event:
            error = event['errs']
        if not error == '':
            self.errorEvents.notify(error)
            _LOGGER.debug("*** error = " + error)

    def _handle_life_span(self, event):
        type = event['type']
        try:
            type = COMPONENT_FROM_ECOVACS[type]
        except KeyError:
            _LOGGER.warning("Unknown component type: '" + type + "'")
        if 'val' in event:
            lifespan = int(event['val']) / 100
            _LOGGER.debug("**********Component " + type + " has lifespan of " + str(lifespan) + ".")
        else:
            lifespan = int(event['left']) / 60  #This works for a D901
        self.components[type] = lifespan
        lifespan_event = {'type': type, 'lifespan': lifespan}
        self.lifespanEvents.notify(lifespan_event)
        _LOGGER.debug("*** life_span " + type + " = " + str(lifespan))

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
            _LOGGER.warning("Unknown cleaning status '" + type + "'")
        self.clean_status = type
        self.vacuum_status = type
        fan = event.get('speed', None)
        if fan is not None:
            try:
                fan = FAN_SPEED_FROM_ECOVACS[fan]
            except KeyError:
                _LOGGER.warning("Unknown fan speed: '" + fan + "'")
        self.fan_speed = fan
        self.statusEvents.notify(self.vacuum_status)
        if self.fan_speed:
            _LOGGER.debug("*** clean_status = " + self.clean_status + " fan_speed = " + self.fan_speed)
        else:
            _LOGGER.debug("*** clean_status = " + self.clean_status + " fan_speed = None")

    def _handle_battery_info(self, iq):
        try:
            self.battery_status = float(iq['power']) / 100
        except ValueError:
            _LOGGER.warning("couldn't parse battery status " + ET.tostring(iq))
        else:
            self.batteryEvents.notify(self.battery_status)
            _LOGGER.debug("*** battery_status = {:.0%}".format(self.battery_status))

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
                _LOGGER.error("Unknown charging status '" + event['errno'] + "'") #Log this so we can identify more errors    
        try:
            status = CHARGE_MODE_FROM_ECOVACS[status]
        except KeyError:
            _LOGGER.warning("Unknown charging status '" + status + "'")
        self.charge_status = status
        if status != 'idle' or self.vacuum_status == 'charging':
            # We have to ignore the idle messages, because all it means is that it's not
            # currently charging, in which case the clean_status is a better indicator
            # of what the vacuum is currently up to.
            self.vacuum_status = status
            self.statusEvents.notify(self.vacuum_status)
        _LOGGER.debug("*** charge_status = " + self.charge_status)

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
            _LOGGER.warning("Ping did not reach VacBot. Will retry.")
            _LOGGER.debug("*** Error type: " + err.etype)
            _LOGGER.debug("*** Error condition: " + err.condition)
            self._failed_pings += 1
            if self._failed_pings >= 4:
                self.vacuum_status = 'offline'
                self.statusEvents.notify(self.vacuum_status)
        except RuntimeError as err:
            _LOGGER.warning("Ping did not reach VacBot. Will retry.")
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
            _LOGGER.warning("Component refresh requests failed to reach VacBot. Will try again later.")
            _LOGGER.debug("*** Error type: " + err.etype)
            _LOGGER.debug("*** Error condition: " + err.condition)

    def refresh_statuses(self):
        try:
            self.run(GetCleanState())
            self.run(GetChargeState())
            self.run(GetBatteryState())
        except XMPPError as err:
            _LOGGER.warning("Initial status requests failed to reach VacBot. Will try again on next ping.")
            _LOGGER.debug("*** Error type: " + err.etype)
            _LOGGER.debug("*** Error condition: " + err.condition)

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