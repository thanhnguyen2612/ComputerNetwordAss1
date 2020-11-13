from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

import random

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	STOP = 'STOP'
	TEARDOWN = 'TEARDOWN'
	DESCRIBE = 'DESCRIBE'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	clientInfo = {}
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		
	def run(self):
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client."""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:            
			data = connSocket.recv(256)
			if data:
				print("Data received:\n" + data.decode("utf-8"))
				self.processRtspRequest(data.decode("utf-8"))

	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]
		
		# Get the media file name
		filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if requestType == self.SETUP and self.state == self.INIT:
			# Update state
			print("processing SETUP\n")
			
			try:
				self.clientInfo['videoStream'] = VideoStream(filename)
				self.state = self.READY
			except IOError:
				self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
			
			# Generate a randomized RTSP session ID
			self.clientInfo['session'] = randint(100000, 999999)
			
			# Send RTSP reply
			self.replyRtsp(self.OK_200, seq[1])
			
			# Get the RTP/UDP port from the last line
			self.clientInfo['rtpPort'] = request[2].split(' ')[3]
		
		# Process PLAY request
		elif requestType == self.PLAY and self.state == self.READY:
			print("processing PLAY\n")
			self.state = self.PLAYING
			
			# Create a new socket for RTP/UDP
			self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)				
			self.replyRtsp(self.OK_200, seq[1])
			
			# Create a new thread and start sending RTP packets
			self.clientInfo['event'] = threading.Event()
			self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
			self.clientInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE and self.state == self.PLAYING:
			print("processing PAUSE\n")
			self.state = self.READY
			self.clientInfo['event'].set()
			self.replyRtsp(self.OK_200, seq[1])
		
		# Process STOP request
		elif requestType == self.STOP:
			print("processing STOP\n")
			try:
				self.clientInfo['videoStream'] = VideoStream(filename)
				# threading.Thread(target=self.readVideoFile).start()
				self.state = self.READY
			except IOError:
				self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
			self.clientInfo['event'].set()
			self.replyRtsp(self.OK_200, seq[1])

			# Close the RTP socket
			self.clientInfo['rtpSocket'].close()
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")
			self.clientInfo['event'].set()
			self.replyRtsp(self.OK_200, seq[1])

			# Close the RTP socket
			self.clientInfo['rtpSocket'].close()
			
		# Process DESCRIBE request
		elif requestType == self.DESCRIBE:
			print("processing DESCRIBE\n")
			self.clientInfo['description'] = self.getDescription(data)
			self.clientInfo['descPort'] = request[2].split(' ')[1]
			threading.Thread(target=self.sendDescription).start()

			self.replyRtsp(self.OK_200, seq[1])

	# # Testing packet loss function
	# def sendRtp(self):
	# 	"""Send RTP packets over UDP."""
	# 	late_packet = []
	# 	while True:
	# 		self.clientInfo['event'].wait(0.05)

	# 		# Stop sending if request is PAUSE or TEARDOWN
	# 		if self.clientInfo['event'].isSet():
	# 			break
			
	# 		data = self.clientInfo['videoStream'].nextFrame()
	# 		if data:
	# 			if random.random() < 0.2: # Simulate: 20% of packets are late
	# 				frameNumber = self.clientInfo['videoStream'].frameNbr()
	# 				rtpPacket = self.makeRtp(data, frameNumber)
	# 				late_packet.append(rtpPacket)
	# 				continue

	# 			frameNumber = self.clientInfo['videoStream'].frameNbr()
	# 			try:
	# 				address = self.clientInfo['rtspSocket'][1][0]
	# 				port = int(self.clientInfo['rtpPort'])
	# 				self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
	# 			except:
	# 				print("Connection Error")
	# 		else:
	# 			print(len(late_packet))
	# 			while late_packet:
	# 				self.clientInfo['event'].wait(0.05)
	# 				rtpPacket = late_packet.pop()
	# 				try:
	# 					address = self.clientInfo['rtspSocket'][1][0]
	# 					port = int(self.clientInfo['rtpPort'])
	# 					self.clientInfo['rtpSocket'].sendto(rtpPacket,(address,port))
	# 				except:
	# 					print("Connection Error")
	# 			break

	def sendDescription(self):
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as descSocket:
			descSocket.connect((self.clientInfo['rtspSocket'][1][0], int(self.clientInfo['descPort'])))
			descSocket.sendall(self.clientInfo["description"].encode())
			
	def sendRtp(self):
		"""Send RTP packets over UDP."""
		while True:
			self.clientInfo['event'].wait(0.05)
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()
			if data: 
				frameNumber = self.clientInfo['videoStream'].frameNbr()
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
				except:
					print("Connection Error")

	def makeRtp(self, payload, frameNbr):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		marker = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			#print("200 OK")
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())
		
		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
	
	def getDescription(self, data):
		request = data.split('\n')
		line1 = request[0].split(' ')
		description = f"v= {line1[2]}"
		description += f"\nu= {line1[1]}"
		return description

	# def readVideoFile(self):
	# 	while True:
	# 		data = self.clientInfo['videoStream'].nextFrame()
	# 		if not data:
	# 			break
	# 		self.clientInfo['VideoArray'].append(data)