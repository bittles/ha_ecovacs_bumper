import hashlib
import time
import requests
#import os
from base64 import b64decode, b64encode
from collections import OrderedDict
#from sleekxmppfs.xmlstream import ET
#from sleekxmppfs.exceptions import XMPPError

#from .sucks_mqtt import EcoVacsIOTMQ
#from .sucks_xmpp import EcoVacsXMPP
from .sucks_api_const import *

import logging
LOGGER = logging.getLogger(__name__)

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
    CLIENT_KEY = API_CLIENT_KEY
    SECRET = API_SECRET
    PUBLIC_KEY = API_PUBLIC_KEY
    MAIN_URL_FORMAT = API_MAIN_URL_FORMAT
    USER_URL_FORMAT = API_USER_URL_FORMAT
    PORTAL_URL_FORMAT = API_PORTAL_URL_FORMAT
    USERSAPI = API_USERSAPI
    IOTDEVMANAGERAPI = API_IOTDEVMANAGERAPI # IOT Device Manager - This provides control of "IOT" products via RestAPI, some bots use this instead of XMPP
    PRODUCTAPI = API_PRODUCTAPI # Leaving this open, the only endpoint known currently is "Product IOT Map" -  pim/product/getProductIotMap - This provides a list of "IOT" products.  Not sure what this provides the app.
    REALM = API_REALM

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
        LOGGER.debug("Setting up EcoVacsAPI")
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
            LOGGER.debug("Switching to shorter UID " + login_response['userId'])
            self.uid = login_response['userId']
        LOGGER.debug("EcoVacsAPI connection complete")

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
        LOGGER.debug("calling main api {} with {}".format(function, args))
        params = OrderedDict(args)
        params['requestId'] = self.md5(time.time())
        url = (EcoVacsAPI.MAIN_URL_FORMAT + "/" + function).format(**self.meta)
        api_response = requests.get(url, self.__sign(params), verify=self.verify_ssl)
        json = api_response.json()
        LOGGER.debug("got {}".format(json))
        if json['code'] == '0000':
            return json['data']
        elif json['code'] == '1005':
            LOGGER.error("incorrect email or password")
            raise ValueError("incorrect email or password")
        else:
            LOGGER.error("call to {} failed with {}".format(function, json))
            raise RuntimeError("failure code {} ({}) for call {} and parameters {}".format(
                json['code'], json['msg'], function, args))

    def __call_user_api(self, function, args):
        LOGGER.debug("calling user api {} with {}".format(function, args))
        params = {'todo': function}
        params.update(args)
        response = requests.post(EcoVacsAPI.USER_URL_FORMAT.format(continent=self.continent), json=params, verify=self.verify_ssl)
        json = response.json()
        LOGGER.debug("got {}".format(json))
        if json['result'] == 'ok':
            return json
        else:
            LOGGER.error("call to {} failed with {}".format(function, json))
            raise RuntimeError(
                "failure {} ({}) for call {} and parameters {}".format(json['error'], json['errno'], function, params))

    def __call_portal_api(self, api, function, args, verify_ssl=True, **kwargs):
        if api == self.USERSAPI:
            params = {'todo': function}
            params.update(args)
        else:
            params = {}
            params.update(args)
        LOGGER.debug("calling portal api {} function {} with {}".format(api, function, params))
        continent = self.continent
        if 'continent' in kwargs:
            continent = kwargs.get('continent')
        url = (EcoVacsAPI.PORTAL_URL_FORMAT + "/" + api).format(continent=continent, **self.meta)
        response = requests.post(url, json=params, verify=verify_ssl)
        json = response.json()
        LOGGER.debug("got {}".format(json))
        if api == self.USERSAPI:
            if json['result'] == 'ok':
                return json
            elif json['result'] == 'fail':
                if json['error'] == 'set token error.': # If it is a set token error try again
                    if not 'set_token' in kwargs:      
                        LOGGER.debug("loginByItToken set token error, trying again (2/3)")
                        return self.__call_portal_api(self.USERSAPI, function, args, verify_ssl=verify_ssl, set_token=1)
                    elif kwargs.get('set_token') == 1:
                        LOGGER.debug("loginByItToken set token error, trying again with ww (3/3)")
                        return self.__call_portal_api(self.USERSAPI, function, args, verify_ssl=verify_ssl, set_token=2, continent="ww")
                    else:
                        LOGGER.debug("loginByItToken set token error, failed after 3 attempts")
        if api.startswith(self.PRODUCTAPI):
            if json['code'] == 0:
                return json

        else:
            LOGGER.error("call to {} failed with {}".format(function, json))
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