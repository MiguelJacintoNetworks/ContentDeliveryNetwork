class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		
	def nextFrame(self):
		# GET THE NEXT FRAME

		# BUFFER USED TO STORE THE CURRENT FRAME
		frame_data = b""
		
		# SEARCH FOR THE START OF IMAGE (SOI) MARKER
		byte = self.file.read(1)
		while byte:
			frame_data += byte

			# CHECK WHETHER THE START OF IMAGE MARKER WAS FOUND
			if frame_data[-2:] == b'\xFF\xD8':  # SOI FOUND
				break
			byte = self.file.read(1)
		
		# CONTINUE READING UNTIL THE END OF IMAGE (EOI) MARKER IS FOUND
		while byte:
			byte = self.file.read(1)
			if not byte:
				break
			frame_data += byte

			# CHECK WHETHER THE END OF IMAGE MARKER WAS FOUND
			if frame_data[-2:] == b'\xFF\xD9':  # EOI FOUND
				self.frameNum += 1
				break

		return frame_data if frame_data else None
		
	def frameNbr(self):
		# RETURN THE FRAME NUMBER
		return self.frameNum
