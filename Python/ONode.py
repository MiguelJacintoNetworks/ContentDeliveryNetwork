import json
import socket
import threading
import psutil
import time
import base64

class ONode:
    def __init__(self):
        self.ip_address = self._get_active_ip()
        self.neighbors = []
        self.is_alive = True
        self.is_pop = False
        self.lock = threading.Lock()
        self.movies = {}
        self.routing_table = {}

    # OBTAINS THE ACTIVE IP ADDRESS OF THE NODE
    def _get_active_ip(self):
        for addresses in psutil.net_if_addrs().values():
            for address in addresses:
                if address.family == socket.AF_INET and address.address != "127.0.0.1":
                    return address.address
        return None
    
    # SENDS PERIODIC HEARTBEATS TO THE SERVER
    def send_heartbeat(self, server_ip, port):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            while self.is_alive:
                try:
                    s.sendto(b'heartbeat', (server_ip, port))
                    print(f"HEARTBEAT SENT FROM {self.ip_address} TO SERVER {server_ip} ON PORT {port}")
                except Exception as e:
                    print(f"FAILED TO SEND HEARTBEAT FROM {self.ip_address}: {e}")
                time.sleep(10)

    # REQUESTS THE BOOTSTRAP NEIGHBOR LIST FROM THE SERVER
    def request_bootstrap(self, server_ip, port):
        while self.is_alive:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                    client_socket.connect((server_ip, port))
                    request_message = {"message": "bootstraper", "ip_address": self.ip_address}
                    client_socket.sendall(json.dumps(request_message).encode())
                    response = json.loads(client_socket.recv(4096).decode())
                    with self.lock:
                        self.neighbors = response.get("neighbors", [])
                    print(f"BOOTSTRAP NEIGHBORS RECEIVED FOR {self.ip_address}: {self.neighbors}")
            except Exception as e:
                print(f"FAILED TO CONNECT TO SERVER FOR BOOTSTRAP FROM {self.ip_address}: {e}")
            time.sleep(30)

    # CHECKS IF THE NODE IS A POP (POINT OF PRESENCE)
    def request_pop_info(self, server_ip, port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
                client_socket.connect((server_ip, port))
                request_message = {"message": "is_pop", "ip_address": self.ip_address}
                client_socket.sendall(json.dumps(request_message).encode())
                response = json.loads(client_socket.recv(4096).decode())
                self.is_pop = response.get("is_pop", False)
                print(f"NODE {self.ip_address} IS {'A POP' if self.is_pop else 'NOT A POP'}")
        except Exception as e:
            print(f"FAILED TO CONNECT TO SERVER FOR POP INFO FROM {self.ip_address}: {e}")

    def start_pop_server(self, client_pop_port, stream_request_port, stream_receive_port):
        
        # MONITORS CLIENTS' REQUESTS AND RESPONDS TO PING MESSAGES
        def client_monitoring_server():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
                server_socket.bind(("0.0.0.0", client_pop_port))
                while self.is_alive:
                    try:
                        message, client_address = server_socket.recvfrom(1024)
                        if message.decode() == "ping":
                            server_socket.sendto(b'pong', client_address)
                            print(f"RESPONDED TO PING FROM CLIENT {client_address}")
                    except Exception as e:
                        print(f"ERROR RESPONDING TO PING FROM {client_address}: {e}")
        
        # HANDLES STREAM REQUESTS FROM CLIENTS
        def handle_stream_request(client_address, movie_name):
            try:
                if movie_name not in self.movies:
                    self.movies[movie_name] = []
                    self.movies[movie_name].append(client_address)
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                        print(f"REQUESTING STREAM FOR {movie_name} TO {self.routing_table[server_ip]['next_hop']}")
                        if self.routing_table[server_ip]["next_hop"] == server_ip:
                            tcp_socket.connect((server_ip, server_tcp_port))
                        else:
                            tcp_socket.connect((self.routing_table[server_ip]["next_hop"], stream_request_port))

                        tcp_socket.sendall(json.dumps({"message": "stream", "movie": movie_name}).encode())
                    print(f"STREAM REQUEST FOR '{movie_name}' REDIRECTED TO {self.routing_table[server_ip]['next_hop']} FROM CLIENT {client_address}")
                else:
                    self.movies[movie_name].append(client_address)
                    print(f"CLIENT {client_address} ADDED TO STREAM LIST FOR '{movie_name}'")
            except Exception as e:
                print(f"FAILED TO REQUEST STREAM '{movie_name}' VIA TCP FOR CLIENT {client_address}: {e}")

        # HANDLES RECEIVING AND FORWARDING STREAMS TO CLIENTS
        def receive_stream():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                udp_socket.settimeout(5)
                udp_socket.bind(("0.0.0.0", stream_receive_port))
                while self.is_alive:
                    try:
                        json_bytes, address = udp_socket.recvfrom(65535)
                        json_string = json_bytes.decode('utf-8')
                        payload = json.loads(json_string)
                        movie_name = payload["movieName"]
                        if self.is_pop:
                            packet = base64.b64decode(payload["data"])
                            for addr in self.movies[movie_name]:
                                udp_socket.sendto(packet, (addr, stream_receive_port))
                        else:
                            for addr in self.movies[movie_name]:
                                udp_socket.sendto(json_bytes, (addr, stream_receive_port))
                        print(f"FORWARDED RTP PACKET FOR '{movie_name}' TO CLIENTS {self.movies[movie_name]}")
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"ERROR HANDLING STREAM '{movie_name}': {e}")
                        break

        # LISTENS FOR STREAM REQUESTS FROM CLIENTS
        def client_requesting_stream(udp):
            if udp:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                    udp_socket.bind(("0.0.0.0", stream_request_port))
                    while self.is_alive:
                        try:
                            request_data, client_address = udp_socket.recvfrom(4096)
                            request = json.loads(request_data.decode())
                            if request.get("message") == "stream":
                                print(f"STREAM REQUEST RECEIVED FROM CLIENT {client_address} FOR MOVIE '{request.get('movie')}'")
                                threading.Thread(target=handle_stream_request, args=(client_address[0], request.get("movie")), daemon=True).start()
                        except Exception as e:
                            print(f"ERROR HANDLING STREAM REQUEST FROM CLIENT {client_address}: {e}")
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                    tcp_socket.bind(("0.0.0.0", stream_request_port))
                    tcp_socket.listen(5)
                    print(f"TCP SERVER LISTENING ON PORT {stream_request_port}")
                    while self.is_alive:
                        try:
                            client_socket, client_address = tcp_socket.accept()
                            print(f"CONNECTION ACCEPTED FROM {client_address}")
                            request_data = client_socket.recv(4096)
                            request = json.loads(request_data.decode())
                            if request.get("message") == "stream":
                                threading.Thread(target=handle_stream_request, args=(client_address[0], request.get("movie")), daemon=True).start()
                        except Exception as e:
                            print(f"ERROR ACCEPTING CONNECTION: {e}")

        if self.is_pop:
            threading.Thread(target=client_monitoring_server, daemon=True).start()
            threading.Thread(target=client_requesting_stream, args=(True,), daemon=True).start()
        else:
            threading.Thread(target=client_requesting_stream, args=(False,), daemon=True).start()

        threading.Thread(target=receive_stream, daemon=True).start()

    def flood(self):

        # BUILDS A ROUTING TABLE ENTRY BASED ON FLOOD PACKET DATA
        def build_routing_table_entry(json_data, latency):
            data = {
                "n_jumps": json_data["n_jumps"] + 1,
                "latency": latency,
                "next_hop": json_data["next_hop"],
            }
            return data

        # CREATES A FLOOD PACKET FOR TRANSMISSION TO NEIGHBORS
        def build_flood_packet(json_data):
            data = {
                "message": "flood",
                "n_jumps": self.routing_table[json_data["origin"]]["n_jumps"],
                "origin": json_data["origin"],
                "next_hop": self.ip_address,
                "timestamp": time.time(),
                "latency": self.routing_table[json_data["origin"]]["latency"],
            }
            return data
        
        flood_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        flood_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        flood_socket.bind(("0.0.0.0", flood_port))
        flood_socket.listen(5)    
        try:
            while True:
                client_socket, client_address = flood_socket.accept()

                try:
                    with client_socket:
                        data = client_socket.recv(4096)
                        if data:
                            try:
                                # PARSES RECEIVED DATA AS JSON
                                json_data = json.loads(data.decode("utf-8"))
                                latency = time.time() - json_data["timestamp"] + json_data["latency"]
                                # UPDATES OR ADDS ROUTING TABLE ENTRY IF NECESSARY
                                if (
                                    json_data["origin"] not in self.routing_table
                                    or latency < self.routing_table[json_data["origin"]]["latency"]
                                    or (
                                        latency == self.routing_table[json_data["origin"]]["latency"]
                                        and (json_data["n_jumps"] + 1) < self.routing_table[json_data["origin"]]["n_jumps"]
                                    )
                                ):
                                    self.routing_table[json_data["origin"]] = build_routing_table_entry(json_data, latency)
                                print("CURRENT ROUTING TABLE:")
                                print(self.routing_table)
                                # RETRANSMITS FLOOD PACKET TO NEIGHBORS (EXCEPT ORIGINATOR)
                                if not self.is_pop:
                                    for neighbor in self.neighbors:
                                        neighbor_ip = neighbor["ip"]
                                        if neighbor_ip != json_data["next_hop"]:
                                            try:
                                                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                                    s.connect((neighbor_ip, flood_port))
                                                    flood_packet = json.dumps(build_flood_packet(json_data))
                                                    s.sendall(flood_packet.encode("utf-8"))
                                            except Exception as e:
                                                print(f"ERROR SENDING TO {neighbor_ip}: {e}")
                            except json.JSONDecodeError as e:
                                print(f"ERROR DECODING JSON: {e}")
                except Exception as e:
                    print(f"ERROR HANDLING CLIENT {client_address}: {e}")
        except KeyboardInterrupt:
            print("SHUTTING DOWN FLOOD SERVER...")
        finally:
            flood_socket.close()

    def start_node(self, server_ip, server_tcp_port, server_heartbeat_port, client_pop_port, stream_request_port, stream_receive_port):
        # INITIALIZES NODE AND STARTS ALL NECESSARY THREADS FOR COMMUNICATION
        if self.ip_address:
            # STARTS THREAD TO SEND HEARTBEAT MESSAGES TO THE SERVER
            threading.Thread(target=self.send_heartbeat, args=(server_ip, server_heartbeat_port), daemon=True).start()
        
            # STARTS THREAD TO REQUEST BOOTSTRAP INFORMATION FROM THE SERVER
            threading.Thread(target=self.request_bootstrap, args=(server_ip, server_tcp_port), daemon=True).start()
        
            # STARTS THREAD TO DETERMINE IF THE NODE IS A POP
            pop_thread = threading.Thread(target=self.request_pop_info, args=(server_ip, server_tcp_port))
            pop_thread.start()
            pop_thread.join()  # ENSURES POP INFORMATION IS AVAILABLE BEFORE CONTINUING
        
            # STARTS THREAD TO HANDLE FLOODING LOGIC
            threading.Thread(target=self.flood, daemon=True).start()
        
            # STARTS POP SERVER FOR STREAM MANAGEMENT AND CLIENT MONITORING
            self.start_pop_server(client_pop_port, stream_request_port, stream_receive_port)
        
            print(f"[FUNC][START_NODE] - NODE {self.ip_address} INITIALIZED WITH ALL COMMUNICATION THREADS RUNNING")
    
        # KEEPS NODE ACTIVE WHILE IT IS ALIVE
        while self.is_alive:
            time.sleep(1)

# CONFIGURATION VARIABLES FOR SERVER AND CLIENT PORTS
server_ip = "10.0.25.10"
server_tcp_port = 12345
server_heartbeat_port = 45636
client_pop_port = 46668
stream_request_port = 54364
stream_receive_port = 43216
flood_port = 42684

# CREATES AND STARTS THE NODE INSTANCE
node = ONode()
node.start_node(server_ip, server_tcp_port, server_heartbeat_port, client_pop_port, stream_request_port, stream_receive_port)