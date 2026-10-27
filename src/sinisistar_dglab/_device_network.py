"""Read interface addresses without changing routes or contacting the Internet."""
from .dglab import discover_lan_ips

def ipv4_interfaces():
    return [dict(address=address,name=address) for address in discover_lan_ips()]
