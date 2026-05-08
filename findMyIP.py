import socket
import psutil

def get_active_ip():
    interfaces = psutil.net_if_addrs()
    for interface_name, addresses in interfaces.items():
        for address in addresses:
            if address.family == socket.AF_INET and address.address != "127.0.0.1":
                return interface_name, address.address
    return None, None

interface, ip = get_active_ip()
if interface:
    print(f"ACTIVE INTERFACE: {interface}")
    print(f"IP ADDRESS: {ip}")
else:
    print("NO ACTIVE NETWORK INTERFACE WITH AN IP ADDRESS WAS FOUND.")
