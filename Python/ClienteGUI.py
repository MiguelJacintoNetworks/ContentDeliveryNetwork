from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class ClienteGUI:
	
	# INITIALIZATION
	def __init__(self, master, addr, port):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.addr = addr
		self.port = int(port)
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.openRtpPort()
		self.playMovie()
		self.frameNbr = 0
		
	def createWidgets(self):
		# BUILD THE GUI
		# CREATE THE SETUP BUTTON
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# CREATE THE PLAY BUTTON
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# CREATE THE PAUSE BUTTON
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# CREATE THE TEARDOWN BUTTON
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# CREATE A LABEL TO DISPLAY THE VIDEO
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
	
	def setupMovie(self):
		# HANDLE THE SETUP BUTTON
		print("NOT IMPLEMENTED...")
	
	def exitClient(self):
		# HANDLE THE TEARDOWN BUTTON
		self.master.destroy() # CLOSE THE GUI WINDOW
		os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # DELETE THE CACHED VIDEO IMAGE

	def pauseMovie(self):
		# HANDLE THE PAUSE BUTTON
		print("NOT IMPLEMENTED...")
	
	def playMovie(self):
		# HANDLE THE PLAY BUTTON
		# CREATE A NEW THREAD TO LISTEN FOR RTP PACKETS
		threading.Thread(target=self.listenRtp).start()
		self.playEvent = threading.Event()
		self.playEvent.clear()
	
	def listenRtp(self):		
		# LISTEN FOR RTP PACKETS
		while True:
			try:
				data = self.rtpSocket.recv(20480)
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					
					currFrameNbr = rtpPacket.seqNum()
					print("CURRENT SEQUENCE NUMBER: " + str(currFrameNbr))
										
					if currFrameNbr > self.frameNbr: # DISCARD LATE PACKETS
						self.frameNbr = currFrameNbr
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
			except:
				# STOP LISTENING AFTER A PAUSE OR TEARDOWN REQUEST
				if self.playEvent.isSet(): 
					break
				
				self.rtpSocket.shutdown(socket.SHUT_RDWR)
				self.rtpSocket.close()
				break
				
	
	def writeFrame(self, data):
		# WRITE THE RECEIVED FRAME TO A TEMPORARY IMAGE FILE AND RETURN IT
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		# UPDATE THE GUI WITH THE CURRENT VIDEO FRAME
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
	
	def openRtpPort(self):
		# OPEN THE RTP SOCKET AND BIND IT TO THE SPECIFIED PORT
		# CREATE A NEW DATAGRAM SOCKET TO RECEIVE RTP PACKETS FROM THE SERVER
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		
		# SET THE SOCKET TIMEOUT TO 0.5 SECONDS
		self.rtpSocket.settimeout(0.5)
		
		try:
			# BIND THE SOCKET TO THE ADDRESS USING THE RTP PORT
			self.rtpSocket.bind((self.addr, self.port))
			print('\nRTP SOCKET BOUND SUCCESSFULLY\n')
		except:
			tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

	def handler(self):
		# HANDLE MANUAL GUI WINDOW CLOSING
		self.pauseMovie()
		if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # IF THE USER PRESSES CANCEL, RESUME PLAYBACK
			self.playMovie()
