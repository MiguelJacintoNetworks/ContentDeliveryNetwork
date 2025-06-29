import os
import socket
import json
import re
import time
import threading
from tkinter import *
import tkinter.messagebox
from RtpPacket import RtpPacket
from PIL import Image, ImageTk

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class PoPMonitor:
    def __init__(self, pops):
        self.pops = pops
        self.latencies = {pop: float('inf') for pop in pops}
        self.last_best_pop = None
        self.best_pop = None
        self.lock = threading.Lock()

    # MEASURE LATENCY TO A GIVEN POP USING UDP PINGS.
    def measure_latency(self, pop):
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(1)
                s.sendto(b'ping', (pop, pop_port))
                s.recvfrom(1024)
            latency = (time.time() - start_time) * 1000  # CONVERT SECONDS TO MILLISECONDS
            return latency
        except socket.timeout:
            print(f"ERROR MEASURING LATENCY FOR {pop}: TIMEOUT OCCURRED")
            return float('inf')
        except Exception as e:
            print(f"ERROR MEASURING LATENCY FOR {pop}: {e}")
            return float('inf')

    # CONTINUOUSLY UPDATE LATENCY INFORMATION FOR ALL POP.        
    def update_latencies(self):
        while True:
            with self.lock:
                for pop in self.pops:
                    latency = self.measure_latency(pop)
                    self.latencies[pop] = latency
                    print(f"UPDATED LATENCY FOR {pop}: {latency} MS")
            time.sleep(5)  # WAIT FOR 5 SECONDS BEFORE UPDATING AGAIN

    # SELECT THE BEST POP BASED ON LOWEST LATENCY.         
    def select_best_pop(self):
        with self.lock:
            self.last_best_pop = self.best_pop
            print(f"CURRENT LATENCIES: {self.latencies}")
            self.best_pop = min(self.latencies, key=self.latencies.get)
            return self.best_pop

class Client:
    def __init__(self, movie):
        self.pop = []
        self.monitor = None
        self.frameNbr = 0
        self.sessionId = self.init_sessionId()
        self.movieName = movie
        self.master = Tk()
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()

    # INITIALIZE SESSION ID BASED ON EXISTING CACHE FILES.
    def init_sessionId(self):
        pattern = re.compile(rf"{re.escape(CACHE_FILE_NAME)}(\d+){re.escape(CACHE_FILE_EXT)}")
        session_ids = []
        # ITERATE THROUGH FILES IN THE CURRENT DIRECTORY.
        for filename in os.listdir('.'):
            match = pattern.match(filename)
            if match:
                session_ids.append(int(match.group(1)))

        return max(session_ids) + 1 if session_ids else 1

    # CREATE GUI WIDGETS FOR THE CLIENT.
    def createWidgets(self):
        # CREATE PLAY BUTTON.
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)
        # CREATE TEARDOWN BUTTON.
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)
        # CREATE A LABEL TO DISPLAY THE MOVIE.
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W + E + N + S, padx=5, pady=5)

    # HANDLE CLIENT TEARDOWN AND EXIT.
    def exitClient(self):
        self.master.destroy()  # CLOSE THE GUI WINDOW.
        os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)  # DELETE THE CACHE IMAGE FILE.

    # HANDLE PLAY MOVIE REQUEST.
    def playMovie(self):
        self.requesting_best_pop_stream()
        threading.Thread(target=self.listen_rtp).start()
        self.playEvent = threading.Event()
        self.playEvent.clear()

    # HANDLE CLOSING THE GUI WINDOW.
    def handler(self):
        self.exitClient()

    # LISTEN FOR RTP PACKETS FROM THE SERVER.
    def listen_rtp(self):
        rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtpSocket.bind(("0.0.0.0", stream_receive_port))
        while True:
            try:
                data = rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    
                    currFrameNbr = rtpPacket.seqNum()
                    # DISCARD LATE PACKETS.
                    if currFrameNbr > self.frameNbr:
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
            except Exception as e:
                print(f"ERROR WHILE RECEIVING RTP PACKET: {e}")
                rtpSocket.shutdown(socket.SHUT_RDWR)
                rtpSocket.close()
                break

    # WRITE THE RECEIVED FRAME TO A TEMPORARY IMAGE FILE.
    def writeFrame(self, data):
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        with open(cachename, "wb") as file:
            file.write(data)
        return cachename
	
    # UPDATE THE GUI WITH THE NEW VIDEO FRAME.
    def updateMovie(self, imageFile):
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image=photo, height=288)
        self.label.image = photo

    # REQUEST THE POP LIST FROM THE SERVER AND START MONITORING.
    def get_POP_List(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
            client_socket.settimeout(5)
            request_message = {"message": "POPs"}
            encoded_message = json.dumps(request_message).encode()
            while True:
                try:
                    print("SENDING 'POPs' REQUEST TO SERVER...")
                    client_socket.sendto(encoded_message, (server_ip, server_pop_port))
                    response_data, _ = client_socket.recvfrom(4096)
                    response = json.loads(response_data.decode())
                    if "POPs" in response:
                        self.pop = response["POPs"]
                        self.monitor = PoPMonitor(self.pop)
                        threading.Thread(target=self.monitor.update_latencies, daemon=True).start()
                        break
                    else:
                        print("INVALID RESPONSE. RETRYING...")
                except socket.timeout:
                    print("NO RESPONSE FROM SERVER. RETRYING...")

    # REQUEST STREAMING FROM THE BEST POP BASED ON LATENCY.
    def requesting_best_pop_stream(self):
        """MONITOR THE BEST POP AND REQUEST STREAM FROM THE MOST SUITABLE POP."""
        def monitor_best_pop():
            best_pop = self.monitor.select_best_pop()
            print(f"BEST POP SELECTED: {best_pop}")
            if best_pop != self.monitor.last_best_pop:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
                    client_socket.settimeout(5)
                    request_message = {"message": "stream", "movie": self.movieName}
                    encoded_message = json.dumps(request_message).encode()
                    client_socket.sendto(encoded_message, (best_pop, stream_request_port))
                    print(f"REQUESTED STREAM FROM {best_pop}")
        threading.Thread(target=monitor_best_pop, daemon=True).start()

# CONFIGURATIONS
server_ip = "10.0.25.10"
server_pop_port = 45635
pop_port = 46668
stream_request_port = 54364
stream_receive_port = 43216

# CHOOSE MOVIE
inputString = """Which movie would you like to watch:
1 - movie1.mjpeg
2 - movie2.mjpeg
"""

while True:
    comando = input(inputString).strip()
    if comando.lower() == "1":
        movie = "movie1.mjpeg"
        break
    if comando.lower() == "2":
        movie = "movie2.mjpeg"
        break
    else:
        print("INVALID OPTION! PLEASE CHOOSE 1 OR 2.")

print("MOVIE SELECTED SUCCESSFULLY: " + movie)

client = Client(movie)
client.get_POP_List()
client.master.mainloop()