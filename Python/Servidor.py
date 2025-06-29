import json
import socket
import threading
import time
import base64
from select import select
from VideoStream import VideoStream
from RtpPacket import RtpPacket

with open("../bootstrap.json", "r") as file:
    bootstrap_data = json.load(file)

class Servidor:
    TCP_PORT = 12345
    UDP_PORT = 45635
    HEARTBEAT_PORT = 45636
    STREAM_RECEIVE_PORT = 43216
    FLOOD_PORT = 42684
    HEARTBEAT_TIMEOUT = 10
    SERVER_IP = "10.0.25.10"

    def __init__(self):
        self.alive_nodes = {}
        self.neighbors = ["10.0.21.2", "10.0.19.1"]
        self.logs = []
        self.sockets = []
        self.active_streams = {}
        self.video_streams = {}
        self.lock = threading.Lock()

    # LOGS A MESSAGE WITH A TIMESTAMP AND CLASS CONTEXT
    def log_message(self, message):
        with self.lock:
            self.logs.append(message)
            if len(self.logs) > 20:
                self.logs.pop(0)
        print(f"[FUNC][{self.__class__.__name__}] - {message}")

    # CHECKS IF THE GIVEN IP ADDRESS BELONGS TO A POP
    def is_pop(self, ip_address):
        return ip_address in bootstrap_data.get("POPs", [])

    # SENDS RTP PACKETS FOR A SPECIFIC MOVIE
    def send_rtp(self, movie_name):
        print(f"STREAMING STARTED FOR MOVIE: {movie_name.upper()}")
        while True:
            time.sleep(0.05)
            data = self.video_streams[movie_name].nextFrame()
            if data:
                frame_number = self.video_streams[movie_name].frameNbr()
                packet = self._make_rtp(data, frame_number)
                packet_base64 = base64.b64encode(packet).decode('utf-8')
                json_payload = {"movieName": movie_name, "data": packet_base64}
                json_bytes = json.dumps(json_payload).encode('utf-8')

                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                    for address in self.active_streams[movie_name]:
                        udp_socket.sendto(json_bytes, (address, self.STREAM_RECEIVE_PORT))
            else:
                with self.lock:
                    del self.video_streams[movie_name]
                    del self.active_streams[movie_name]
                self.log_message(f"STREAMING ENDED FOR MOVIE: {movie_name.upper()}")
                break

    # CREATES AN RTP PACKET
    def _make_rtp(self, payload, frame_nbr):
        rtp_packet = RtpPacket()
        rtp_packet.encode(2, 0, 0, 0, frame_nbr, 0, 26, 0, payload)
        return rtp_packet.getPacket()

    # HANDLES A BOOTSTRAP REQUEST FROM A CLIENT
    def handle_bootstrap_request(self, conn, client_ip):
        neighbors = bootstrap_data.get("nodes", {}).get(client_ip, {}).get("neighbours", [])
        response = {"neighbors": neighbors} if neighbors else {"error": "IP Address Not Found"}
        conn.sendall(json.dumps(response).encode())
        self.log_message(f"BOOTSTRAP REQUEST FROM IP {client_ip} - NEIGHBORS LIST SENT: {neighbors}")

    # LISTENS FOR INCOMING TCP REQUESTS
    def listen_for_tcp_requests(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.bind(("0.0.0.0", self.TCP_PORT))
            tcp_socket.listen(5)
            self.log_message("TCP SERVER LISTENING ON PORT 12345")
            while True:
                conn, _ = tcp_socket.accept()
                threading.Thread(target=self.handle_tcp_request, args=(conn,), daemon=True).start()

    # HANDLES AN INDIVIDUAL TCP REQUEST
    def handle_tcp_request(self, conn):
        try:
            request = json.loads(conn.recv(4096).decode())
            client_ip = request.get("ip_address")
            if request.get("message") == "bootstraper":
                self.handle_bootstrap_request(conn, client_ip)
            elif request.get("message") == "is_pop":
                response = {"is_pop": self.is_pop(client_ip)}
                conn.sendall(json.dumps(response).encode())
                self.log_message(f"POP CHECK REQUEST FROM IP {client_ip} - IS POP: {response['is_pop']}")
            elif request.get("message") == "stream":
                movie_name = request.get("movie")
                self.start_stream(movie_name, conn.getpeername()[0])
            else:
                conn.sendall(json.dumps({"error": "Unknown Request Type"}).encode())
                self.log_message(f"UNKNOWN REQUEST TYPE RECEIVED FROM IP {client_ip}")
        except Exception as e:
            self.log_message(f"ERROR HANDLING TCP REQUEST FROM IP {conn.getpeername()[0]}: {e}")
        finally:
            conn.close()

    # STARTS STREAMING A MOVIE FOR A CLIENT
    def start_stream(self, movie_name, client_address):
        with self.lock:
            if movie_name not in self.active_streams:
                self.active_streams[movie_name] = []
                self.video_streams[movie_name] = VideoStream(movie_name)
                threading.Thread(target=self.send_rtp, args=(movie_name,), daemon=True).start()
            self.active_streams[movie_name].append(client_address)
        self.log_message(f"STREAMING STARTED FOR MOVIE '{movie_name}' TO CLIENT {client_address}")

    # LISTENS FOR INCOMING UDP REQUESTS
    def listen_for_udp_requests(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.bind(("0.0.0.0", self.UDP_PORT))
            self.log_message("UDP SERVER LISTENING ON PORT 45635")
            while True:
                request_data, client_address = udp_socket.recvfrom(4096)
                threading.Thread(target=self.handle_udp_request, args=(request_data, client_address), daemon=True).start()

    # HANDLES AN INDIVIDUAL UDP REQUEST
    def handle_udp_request(self, data, client_address):
        try:
            request = json.loads(data.decode())
            if request.get("message") == "POPs":
                pops_list = bootstrap_data.get("POPs", [])
                response = {"POPs": pops_list}
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                    udp_socket.sendto(json.dumps(response).encode(), client_address)
                self.log_message(f"POPs LIST SENT TO {client_address} - POPs: {pops_list}")
        except Exception as e:
            self.log_message(f"ERROR HANDLING UDP REQUEST FROM {client_address}: {e}")

    # LISTENS FOR HEARTBEATS FROM NODES
    def listen_for_heartbeats(self):
        threading.Thread(target=self.listen_for_heartbeat_requests, daemon=True).start()

    # HANDLES INCOMING HEARTBEAT MESSAGES
    def listen_for_heartbeat_requests(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
            udp_socket.bind(("0.0.0.0", self.HEARTBEAT_PORT))
            self.log_message("HEARTBEAT SERVER LISTENING ON PORT 45636")
            while True:
                readable, _, _ = select([udp_socket], [], [], 0.5)
                for sock in readable:
                    data, addr = sock.recvfrom(4096)
                    self.handle_heartbeat(data, addr)

    # PROCESSES AN INDIVIDUAL HEARTBEAT MESSAGE
    def handle_heartbeat(self, data, addr):
        if data.decode() == "heartbeat":
            with self.lock:
                self.alive_nodes[addr[0]] = time.time()
            self.log_message(f"HEARTBEAT RECEIVED FROM NODE {addr[0]} - NODE MARKED AS ACTIVE")

    # CHECKS FOR INACTIVE NODES AND REMOVES THEM
    def check_alive_nodes(self):
        while True:
            current_time = time.time()
            with self.lock:
                inactive_nodes = [node for node, last_heartbeat in self.alive_nodes.items() if current_time - last_heartbeat > self.HEARTBEAT_TIMEOUT]
                for node in inactive_nodes:
                    del self.alive_nodes[node]
                    self.log_message(f"NODE {node} MARKED AS INACTIVE DUE TO TIMEOUT EXCEEDING {self.HEARTBEAT_TIMEOUT} SECONDS")
            time.sleep(5)

    # SENDS A FLOOD PACKET TO A NEIGHBOR
    def send_flood_packet(self, neighbour_ip):
        data = {
            "message": "flood",
            "n_jumps": 0,
            "origin": self.SERVER_IP,
            "next_hop": self.SERVER_IP,
            "timestamp": time.time(),
            "latency": 0
        }
        json_data = json.dumps(data)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((neighbour_ip, self.FLOOD_PORT))
                s.sendall(json_data.encode('utf-8'))
        except Exception as e:
            print(f"ERROR SENDING FLOOD PACKET TO {neighbour_ip}: {e}")
            
    # INICIATES THE FLOODING PROCESS TO NEIGHBORS
    def flood(self):
        for neighbor in self.neighbors:
            self.send_flood_packet(neighbor)
        print("FLOODING DONE")

    # MAIN FUNCTION TO START THE SERVER
    def main(self):
        threading.Thread(target=self.listen_for_tcp_requests, daemon=True).start()
        threading.Thread(target=self.listen_for_udp_requests, daemon=True).start()
        self.listen_for_heartbeats()
        threading.Thread(target=self.check_alive_nodes, daemon=True).start()
        while True:
            command = input("ENTER A COMMAND: ")
            if command.lower() == "flood":
                self.flood()

if __name__ == "__main__":
    Servidor().main()