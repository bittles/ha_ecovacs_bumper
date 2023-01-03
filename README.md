# Home Assistant Ecovacs Custom Component with Bumper Support
Replaces built in ecovacs component.  Designed to work with bumper, https://github.com/bmartin5692/bumper, a replacement for Ecovacs servers to truly get local control.

Works with bumper with my N79 and should work with at least other XMPP based ecovacs.  Don't know if changes will work with MQTT based ones.

Should work as regular if bumper is false in config but haven't tested yet, goal was to get it all local.  Maybe mess around and test it in future.

With bumper, my N79 commands would work but some queries had responses that included errno='', which bumper would flag as an error even though the full response was there. It never created attributes for the filters as one of the results.  If your debug logs are throwing errors and the errno is '' then my small fork of bumper may help https://github.com/bittles/bumper-fork 

Based off the regular home assistant ecovacs config and bmartin's fork of sucks, https://github.com/bmartin5692/sucks. 
I'm using the docker-compose example from my bumper forked from bmartin5692's, https://github.com/bmartin5692/bumper on an odroid-n2+.

### DNS
For DNS routing I have an Asus AX88u with asus-merlin installed running Adguard.  DNS rewrites in AdGuard for domains:
```
*.ecouser.net
*.ecovacs.com
*.ecovacs.net 
```
pointing to my bumper server.

## Home Assistant Install & Config
### HACS Install
You can add this repository to your HACS: https://github.com/bittles/ha_ecovacs_bumper

Then download with HACS, HACS -> Integrations -> Explore & Download Repositories -> EcovacsBumper

Restart HASS.

### Manually Install
Drop the ecovacs folder into your custom_components folder. 

Restart HASS.

### Config
In your configuration.yaml:
```
ecovacs:
  username: 
  password: 
  country: 
  continent: 
  bumper: true/false (optional, defaults false)
  bumper_server: (optional, defaults null)
  verify_ssl: true/false, false if using bumper (optional, defaults true)
```
Any username, password, country, and continent should work if bumper is true.  Set bumper_server to the ip_address where you're running bumper and set verify_ssl to false for bumper.  If you're not using bumper this SHOULD technically work no different than the Home Assistant ecovacs integration but I haven't looked at it enough to be sure and I haven't tested it.

### Example Config
```
ecovacs:
  username: bumper
  password: bumper
  country: us
  continent: na
  bumper: true
  bumper_server: "192.168.1.55"
  verify_ssl: false
```
Just finished getting this working late 12/13/22 so not sure if everything works yet but will commit changes here if I update it or at least document issues.

### Logging
```
logger:
  logs:
    custom_components.ecovacs.sucksbumper: debug  # or whatever level you want
```

### To-Do:
Make component async, use config_flow, create device and clean up some of the hass integration stuff.

### Misc Info From Making This
Commit history is a bit of a mess.  master branch shows changes from bmartins fork of sucks to v1.3.0 of this custom component.  dev branch shows commits from my attempts at testing and getting this to work.

Added additional catches to sucks because my N79 sends some weird payloads, but attributes all pull in now for brush life spans.  Couple initial queries it also sends weird that I'm in process of catching atm.  As of version 1.3.0 (in the manifest.json) these initial queries and all attributes are working.  Was using an implementation completely mine but saw in the MQTT class there were already catches for child payloads without the main payload having the expected td in its payload.  Kept comments in giving credit and adapted them to work with xmpp.