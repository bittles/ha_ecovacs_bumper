import stringcase
import random
from threading import Event
from sleekxmppfs import ClientXMPP, Callback, MatchXPath
from sleekxmppfs.xmlstream import ET
#from sleekxmppfs.exceptions import XMPPError

import logging
LOGGER = logging.getLogger(__name__)

#This is used by EcoVacsIOTMQ and EcoVacsXMPP for _ctl_to_dict
def RepresentsInt(stringvar):
    try: 
        int(stringvar)
        return True
    except ValueError:
        return False

class EcoVacsXMPP(ClientXMPP):
    def __init__(self, user, domain, resource, secret, continent, vacuum, server_address=None ):
        ClientXMPP.__init__(self, "{}@{}/{}".format(user, domain,resource), '0/' + resource + '/' + secret) #Init with resource to bind it
        self.user = user
        self.domain = domain
        self.boundjid.resource = resource
        self.continent = continent
        self.vacuum = vacuum
        self.credentials['authzid'] = user
        if server_address is None:
            self.server_address = ('msg-{}.ecouser.net'.format(self.continent), '5223')
        else:
            self.server_address = server_address
        self.add_event_handler("session_start", self.session_start)
        self.ctl_subscribers = []
        self.ready_flag = Event()

    def wait_until_ready(self):
        self.ready_flag.wait()

    def session_start(self, event):
        LOGGER.debug("----------------- starting session ----------------")
        LOGGER.debug("event = {}".format(event))
        self.register_handler(Callback("general",
                                       MatchXPath('{jabber:client}iq/{com:ctl}query/{com:ctl}'),
                                       self._handle_ctl))
        # register a ping handler, not really needed but keeps from errors being thrown
        self.register_handler(Callback("Ping",
                                       MatchXPath('{jabber:client}iq/{urn:xmpp:ping}ping/{urn:xmpp:ping}'),
                                       self._handle_ping))
        self.ready_flag.set()

    def subscribe_to_ctls(self, function):
        self.ctl_subscribers.append(function)

    def _handle_ctl(self, message):
        the_good_part = message.get_payload()[0][0]
        as_dict = self._ctl_to_dict(the_good_part)
        if as_dict is not None:
            for s in self.ctl_subscribers:
                s(as_dict)

    def _ctl_to_dict(self, xml):
        #Including changes from jasonarends @ 28da7c2 below
        result = xml.attrib.copy()
        childxml = None
        try: # check for child xml
            childxml = xml[0]
        except IndexError:
            LOGGER.debug("No child xml")
        if 'td' not in result:
            # Handle response data with no 'td'
            if 'type' in result: # single element with type and val
                result['event'] = "LifeSpan" # seems to always be LifeSpan type
            else:
                if childxml is not None:
                    if 'clean' in childxml.tag:
                        result['event'] = "CleanReport"
                    elif 'charge' in childxml.tag:
                        result['event'] = "ChargeState"
                    elif 'battery' in childxml.tag:
                        result['event'] = "BatteryInfo"
                    else:
                        return
                    result.update(childxml.attrib)
                else: # for non-'type' result with no child element, e.g., result of PlaySound
                    return
        else: # response includes 'td'
            result['event'] = result.pop('td')
            if xml:
                result.update(xml[0].attrib) # reponses with td seem to always have child component
        for key in result:
            #Check for RepresentInt to handle negative int values, and ',' for ignoring position updates
            if not RepresentsInt(result[key]) and ',' not in result[key]:
                result[key] = stringcase.snakecase(result[key])
        return result

    def register_callback(self, userdata, message):
        self.register_handler(Callback(kind,
                                       MatchXPath('{jabber:client}iq/{com:ctl}query/{com:ctl}ctl[@td="' + kind + '"]'),
                                       function))

    def send_command(self, xml, recipient):
        c = self._wrap_command(xml, recipient)
        LOGGER.debug('Sending command {0}'.format(c))
        c.send()

    def _wrap_command(self, ctl, recipient):
        q = self.make_iq_query(xmlns=u'com:ctl', ito=recipient, ifrom=self._my_address())
        q['type'] = 'set'
        if not "id" in ctl.attrib:
            ctl.attrib["id"] = self.getReqID() #If no ctl id provided, add an id to the ctl. This was required for the ozmo930 and shouldn't hurt others
        for child in q.xml:
            if child.tag.endswith('query'):
                child.append(ctl)
                return q

    def getReqID(self, customid="0"): #Generate a somewhat random string for request id, with minium 8 chars. Works similar to ecovacs app.
        if customid != "0":
            return "{}".format(customid) #return provided id as string
        else:            
            rtnval = str(random.randint(1,50))
            while len(str(rtnval)) <= 8:
                rtnval = "{}{}".format(rtnval,random.randint(0,50))
            return "{}".format(rtnval) #return as string

    def _my_address(self):
        if not self.vacuum['iotmq']:
            return self.user + '@' + self.domain + '/' + self.boundjid.resource
        else:
            return self.user + '@' + self.domain + '/' + self.resource

    def send_ping(self, to):
        q = self.make_iq_get(ito=to, ifrom=self._my_address())
        q.xml.append(ET.Element('ping', {'xmlns': 'urn:xmpp:ping'}))
        LOGGER.debug("*** sending ping ***")
        q.send()

    # used some code from a sleekxmppfs plugin, seems to work fine
    def _handle_ping(self, iq):
        LOGGER.debug("Pinged by %s", iq['from'])
        iq.reply().send()

    def connect_and_wait_until_ready(self):
        self.connect(self.server_address)
        self.process()
        self.wait_until_ready()