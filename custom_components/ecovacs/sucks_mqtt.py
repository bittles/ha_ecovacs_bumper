import time
import sched
import threading
import ssl
import requests
import stringcase
from threading import Event
from paho.mqtt.client import Client  as ClientMQTT
from paho.mqtt import publish as MQTTPublish
from paho.mqtt import subscribe as MQTTSubscribe
from sleekxmppfs.xmlstream import ET

from .sucks_api_const import API_REALM, API_IOTDEVMANAGERAPI, API_PORTAL_URL_FORMAT

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

#This is used by EcoVacsIOTMQ and EcoVacsXMPP for _ctl_to_dict
def RepresentsInt(stringvar):
    try: 
        int(stringvar)
        return True
    except ValueError:
        return False

class EcoVacsIOTMQ(ClientMQTT):
    def __init__(self, user, domain, resource, secret, continent, vacuum, server_address=None, verify_ssl=True):
        ClientMQTT.__init__(self)
        self.ctl_subscribers = []
        self.user = user
        self.domain = str(domain).split(".")[0] #MQTT is using domain without tld extension
        self.resource = resource
        self.secret = secret
        self.continent = continent
        self.vacuum = vacuum
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.scheduler_thread = threading.Thread(target=self.scheduler.run, daemon=True, name="mqtt_schedule_thread")
        self.verify_ssl = str_to_bool_or_cert(verify_ssl)
        if server_address is None:            
            self.hostname = ('mq-{}.ecouser.net'.format(self.continent))
            self.port = 8883
        else:
            saddress = server_address.split(":")
            if len(saddress) > 1:
                self.hostname = saddress[0]
                if RepresentsInt(saddress[1]):
                    self.port = int(saddress[1])
                else:
                    self.port = 8883
        self._client_id = self.user + '@' + self.domain.split(".")[0] + '/' + self.resource
        self.username_pw_set(self.user + '@' + self.domain, secret)
        self.ready_flag = Event()

    def connect_and_wait_until_ready(self):
        #self._on_log = self.on_log #This provides more logging than needed, even for debug
        self._on_message = self._handle_ctl_mqtt
        self._on_connect = self.on_connect
        #TODO: This is pretty insecure and accepts any cert, maybe actually check?
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        self.tls_set_context(ssl_ctx)
        self.tls_insecure_set(True)
        self.connect(self.hostname, self.port)
        self.loop_start()
        self.wait_until_ready()

    def subscribe_to_ctls(self, function):
        self.ctl_subscribers.append(function)   

    def _disconnect(self):
        self.disconnect() #disconnect mqtt connection
        self.scheduler.empty() #Clear schedule queue

    def _run_scheduled_func(self, timer_seconds, timer_function):
        timer_function()
        self.schedule(timer_seconds, timer_function)

    def schedule(self, timer_seconds, timer_function):
        self.scheduler.enter(timer_seconds, 1, self._run_scheduled_func,(timer_seconds, timer_function))
        if not self.scheduler_thread.is_alive():
            self.scheduler_thread.start()
        
    def wait_until_ready(self):
        self.ready_flag.wait()

    def on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            LOGGER.error("EcoVacsMQTT - error connecting with MQTT Return {}".format(rc))
            raise RuntimeError("EcoVacsMQTT - error connecting with MQTT Return {}".format(rc))    
        else:
            LOGGER.debug("EcoVacsMQTT - Connected with result code "+str(rc))
            LOGGER.debug("EcoVacsMQTT - Subscribing to all")        
            self.subscribe('iot/atr/+/' + self.vacuum['did'] + '/' + self.vacuum['class'] + '/' + self.vacuum['resource'] + '/+', qos=0)
            self.ready_flag.set()

    #def on_log(self, client, userdata, level, buf): #This is very noisy and verbose
    #    LOGGER.debug("EcoVacsMQTT Log: {} ".format(buf))
   
    def send_ping(self):
        LOGGER.debug("*** MQTT sending ping ***")
        rc = self._send_simple_command(MQTTPublish.paho.PINGREQ)
        if rc == MQTTPublish.paho.MQTT_ERR_SUCCESS:
            return True
        else:
            return False

    def send_command(self, action, recipient):
        if action.name == "Clean": #For handling Clean when action not specified (i.e. CLI)
            action.args['clean']['act'] = CLEAN_ACTION_TO_ECOVACS['start'] #Inject a start action
        c = self._wrap_command(action, recipient)
        LOGGER.debug('Sending command {0}'.format(c))
        self._handle_ctl_api(action, 
            self.__call_iotdevmanager_api(c ,verify_ssl=self.verify_ssl )
            )
        
    def _wrap_command(self, cmd, recipient):
        #Remove the td from ctl xml for RestAPI
        payloadxml = cmd.to_xml()
        payloadxml.attrib.pop("td") 
        return {
            'auth': {
                'realm': API_REALM,
                'resource': self.resource,
                'token': self.secret,
                'userid': self.user,
                'with': 'users',
            },
            "cmdName": cmd.name,
            "payload": ET.tostring(payloadxml).decode(),  
                      
            "payloadType": "x",
            "td": "q",
            "toId": recipient,
            "toRes": self.vacuum['resource'],
            "toType": self.vacuum['class']
        }     

    def __call_iotdevmanager_api(self, args, verify_ssl=True):
        LOGGER.debug("calling iotdevmanager api with {}".format(args))
        params = {}
        params.update(args)
        url = (API_PORTAL_URL_FORMAT + "/" + API_IOTDEVMANAGERAPI).format(continent=self.continent)
        response = None        
        try: #The RestAPI sometimes doesnt provide a response depending on command, reduce timeout to 3 to accomodate and make requests faster
            response = requests.post(url, json=params, timeout=3, verify=verify_ssl) #May think about having timeout as an arg that could be provided in the future
        except requests.exceptions.ReadTimeout:
            LOGGER.debug("call to iotdevmanager failed with ReadTimeout")
            return {}
        json = response.json()
        if json['ret'] == 'ok':
            return json
        elif json['ret'] == 'fail':
            if 'debug' in json:
                if json['debug'] == 'wait for response timed out': 
                    #TODO - Maybe handle timeout for IOT better in the future
                    LOGGER.error("call to iotdevmanager failed with {}".format(json))
                    return {}
            else:
                #TODO - Not sure if we want to raise an error yet, just return empty for now
                LOGGER.error("call to iotdevmanager failed with {}".format(json))
                return {}
                #raise RuntimeError(
                #"failure {} ({}) for call {} and parameters {}".format(json['error'], json['errno'], function, params))

    def _handle_ctl_api(self, action, message):
        if not message == {}:
            resp = self._ctl_to_dict_api(action, message['resp'])
            if resp is not None:
                for s in self.ctl_subscribers:
                    s(resp)

    def _ctl_to_dict_api(self, action, xmlstring):
        xml = ET.fromstring(xmlstring)
        xmlchild = list(xml)
        if len(xmlchild) > 0:
            result = xmlchild[0].attrib.copy()
            #Fix for difference in XMPP vs API response
            #Depending on the report will use the tag and add "report" to fit the mold of sucks library
            if xmlchild[0].tag == "clean":
                result['event'] = "CleanReport"
            elif xmlchild[0].tag == "charge":
                result['event'] = "ChargeState"
            elif xmlchild[0].tag == "battery":
                result['event'] = "BatteryInfo"
            else: #Default back to replacing Get from the api cmdName
                result['event'] = action.name.replace("Get","",1) 
        else:
            result = xml.attrib.copy()
            result['event'] = action.name.replace("Get","",1)
            if 'ret' in result: #Handle errors as needed
                if result['ret'] == 'fail':
                    if action.name == "Charge": #So far only seen this with Charge, when already docked
                        result['event'] = "ChargeState"
        for key in result:
            if not RepresentsInt(result[key]): #Fix to handle negative int values
                result[key] = stringcase.snakecase(result[key])
        return result

    def _handle_ctl_mqtt(self, client, userdata, message):
        #LOGGER.debug("EcoVacs MQTT Received Message on Topic: {} - Message: {}".format(message.topic, str(message.payload.decode("utf-8"))))
        as_dict = self._ctl_to_dict_mqtt(message.topic, str(message.payload.decode("utf-8")))
        if as_dict is not None:
            for s in self.ctl_subscribers:
                s(as_dict)

    def _ctl_to_dict_mqtt(self, topic, xmlstring):
        #I haven't seen the need to fall back to data within the topic (like we do with IOT rest call actions), but it is here in case of future need
        xml = ET.fromstring(xmlstring) #Convert from string to xml (like IOT rest calls), other than this it is similar to XMPP
        #Including changes from jasonarends @ 28da7c2 below
        result = xml.attrib.copy()
        if 'td' not in result:
            # This happens for commands with no response data, such as PlaySound
            # Handle response data with no 'td'
            if 'type' in result: # single element with type and val
                result['event'] = "LifeSpan" # seems to always be LifeSpan type
            else:
                if len(xml) > 0: # case where there is child element
                    if 'clean' in xml[0].tag:
                        result['event'] = "CleanReport"
                    elif 'charge' in xml[0].tag:
                        result['event'] = "ChargeState"
                    elif 'battery' in xml[0].tag:
                        result['event'] = "BatteryInfo"
                    else:
                        return
                    result.update(xml[0].attrib)
                else: # for non-'type' result with no child element, e.g., result of PlaySound
                    return
        else: # response includes 'td'
            result['event'] = result.pop('td')
            if xml:
                result.update(xml[0].attrib)
        for key in result:
            #Check for RepresentInt to handle negative int values, and ',' for ignoring position updates
            if not RepresentsInt(result[key]) and ',' not in result[key]:
                result[key] = stringcase.snakecase(result[key])
        return result