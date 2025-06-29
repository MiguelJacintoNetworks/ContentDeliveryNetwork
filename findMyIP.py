import socket
import psutil

def get_active_ip():
    interfaces = psutil.net_if_addrs()  # Obtém todas as interfaces de rede
    for interface_name, addresses in interfaces.items():
        for address in addresses:
            # Verifica se o endereço é IPv4 e não é o endereço local de loopback
            if address.family == socket.AF_INET and address.address != "127.0.0.1":
                # Retorna o nome da interface e o endereço IP
                return interface_name, address.address
    return None, None  # Caso não encontre uma interface ativa

interface, ip = get_active_ip()
if interface:
    print(f"Interface ativa: {interface}")
    print(f"Endereço IP: {ip}")
else:
    print("Não foi encontrada uma interface ativa com IP.")