class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		
	def nextFrame(self):
		"""Get next frame."""
		# Buffer para armazenar o quadro atual
		frame_data = b""
		
		# Procurar pelo marcador de início de quadro (SOI)
		byte = self.file.read(1)
		while byte:
			frame_data += byte
			# Verificar se é o marcador de início de quadro
			if frame_data[-2:] == b'\xFF\xD8':  # Encontrou SOI
				break
			byte = self.file.read(1)
		
		# Continuar lendo até encontrar o marcador de final de quadro (EOI)
		while byte:
			byte = self.file.read(1)
			if not byte:
				break
			frame_data += byte
			# Verificar se é o marcador de final de quadro
			if frame_data[-2:] == b'\xFF\xD9':  # Encontrou EOI
				self.frameNum += 1
				break

		return frame_data if frame_data else None
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	