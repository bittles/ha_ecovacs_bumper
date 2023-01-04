# Home Assistant Ecovacs Custom Component with Bumper Support
Replaces built in ecovacs component, with some upgrades and fixes.  Allows SSL verification to be set to false to work with a self-hosted bumper server, https://github.com/bmartin5692/bumper, a replacement for Ecovacs servers to truly get local control.

Works with bumper with my N79 and should work with other XMPP based ecovacs.  Catches some XMPP messages now that the default HASS one misses (at least with my Ecovacs), including some initial queries and also life span for filters and brushes.  Includes MQTT robot support from bmartin's fork that's basically unchanged in this since I don't have one of those robots.

Should work as regular if bumper is false in config but haven't tested yet, goal was to get it all local.  Maybe mess around and test it in future.

## Bumper Setup
Check out bmartin's docs to setup a bumper server, https://bumper.readthedocs.io/.

Based off the regular home assistant ecovacs components and bmartin's fork of sucks, https://github.com/bmartin5692/sucks. 

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
  verify_ssl: true/false, use false if using bumper (optional, defaults true)
```
Any username, password, country, and continent should work if using bumper.  Set verify_ssl to false if using bumper.  If you're not using bumper this SHOULD technically work no different than the Home Assistant ecovacs integration but I haven't tested it.

### Example Config
```
ecovacs:
  username: bumper
  password: bumper
  country: us
  continent: na
  verify_ssl: false
```
Just finished getting this working late 12/13/22 so not sure if everything works yet but will commit changes here if I update it or at least document issues.

### Logging
If your debug logs are throwing errors and the errno is '' then my small fork of bumper may help https://github.com/bittles/bumper-fork, which also includes ability to disable the XMPP or MQTT servers seperately if you don't own one a robot that uses that protocol.
```
logger:
  logs:
    sleekxmpss: debug
    custom_components.ecovacs.sucksbumper: debug  # or whatever level you want
```

### To-Do:
Make component async, use config_flow, create device and clean up some of the hass integration stuff.  Not in that order.

### Misc Info From Making This
Commit history is a bit of a mess.  master branch shows changes from bmartins fork of sucks to v1.3.0 of this custom component.  dev branch shows commits from my attempts at testing and getting this to work.

Added additional catches to sucks because my N79 sends some weird payloads, but attributes all pull in now for brush life spans.  Couple initial queries it also sends weird that I'm in process of catching atm.  As of version 1.3.0 (in the manifest.json) these initial queries and all attributes are working.  Was using an implementation completely mine but saw in the MQTT class there were already catches for child payloads without the main payload having the expected td in its payload.  Kept comments in giving credit and adapted them to work with xmpp.