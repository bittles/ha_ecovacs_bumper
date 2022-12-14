# Home Assistant Ecovacs Custom Component with Bumper Support
Replaces built in ecovacs component.

Works with bumper with my N79 and should work with at least other XMPP based ecovacs.  Don't know if changes will work with MQTT based ones.

Should work as regular if bumper isn't used in config but haven't tested yet, goal was to get it all local.  Maybe mess around and test it in future.

I'm using the docker-compose example for bumper by bmartin5692, https://github.com/bmartin5692/bumper on an odroid-n2+.

For DNS routing I have an Asus AX88u with asus-merlin installed running Adguard.  DNS rewrites in AdGuard for domains:
```
*.ecouser.net
*.ecovacs.com
*.ecovacs.net 
```
pointing to my bumper server.

Big credits to bmartin5692 for his fork of sucks to base this off of as well.

## Home Assistant Install & Config
Drop the ecovacs folder into your custom_components folder.  If I polish this up I'll add hacs support.
Restart HASS.

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