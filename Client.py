from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	STOP = 3
	TEARDOWN = 4
	DESCRIBE = 5
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr			# IP address of the server
		self.serverPort = int(serverport)		# Port number of the server
		self.rtpPort = int(rtpport)				# Port number for RTP Packet Listener
		self.fileName = filename
		self.rtspSeq = 0						# Current request sequence number
		self.sessionId = 0						# Client session ID
		self.requestSent = -1					# Request code
		self.teardownAcked = 0					# Flag to teardown all conections and stop client
		self.frameNbr = 0						# The latest frame number

		# Connect and automatically setup the movie
		self.connectToServer()
		self.setupMovie()

		# Keep track of lost packet if any
		self.lostPacket = 0

		# Timer and total bytes receive
		self.timer = 0.0
		self.totalDataRecvInBits = 0.0

	def createWidgets(self):
		"""Build GUI."""
		# Create Play button
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Stop"
		self.teardown["command"] =  self.stopMovie
		self.teardown.grid(row=1, column=2, padx=2, pady=2)

		# Create Describe button
		self.describe = Button(self.master, width=20, padx=3, pady=3)
		self.describe["text"] = "Describe"
		self.describe["command"] =  self.getDescription
		self.describe.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=20)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)

	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning("Connection Failed",
									f"Connection to \'{self.serverAddr}\' failed.")
	################################## HANDLER FUNCTION FOR BUTTONS ################################
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			# Create thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
	
	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def stopMovie(self):
		self.sendRtspRequest(self.STOP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)
		# Close GUI
		self.master.destroy()
		# Delete cache file
		try:
			os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
		except:
			print("Error while deleting image cache file")
	
	def getDescription(self):
		"""Describe button handler."""
		self.sendRtspRequest(self.DESCRIBE)

	############################### RTP PACKET LISTENER ############################################
	def listenRtp(self):		
		"""Listen for RTP packets."""
		while True:
			try:
				tic = time.perf_counter() # Begin timing when start receiving data from server
				data, addr = self.rtpSocket.recvfrom(20480)
				if data:
					toc = time.perf_counter() # Stop timing when successfully received data from server
					self.timer += toc - tic

					print("LISTENING...")
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
					self.totalDataRecvInBits += len(rtpPacket.getPayload())
					currFrameNbr = rtpPacket.seqNum()
					print(f"CURRENT SEQUENCE NUMBER: {currFrameNbr}")

					# Ignore late packets
					if currFrameNbr > self.frameNbr:
						if self.frameNbr + 1 != currFrameNbr: # Keep track of lost packet
							self.lostPacket += (currFrameNbr - self.frameNbr) - 1
						self.frameNbr = currFrameNbr
						self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
			except:
				# Stop listening if PAUSE or TEARDOWN
				if self.playEvent.isSet():
					break

				# If teardown, close the RTP socket
				if self.teardownAcked == 1:
					try:
						self.rtpSocket.shutdown(socket.SHUT_RDWR)
						self.rtpSocket.close()
						break
					except:
						break
	
	######################### WRITE FRAME TO CACHE AND DISPLAY IMAGES AS MOVIE #####################
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		with open(cachename, "wb") as f:
			f.write(data)
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		image = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image=image, height=288)
		self.label.image = image
	
	################################################################################################
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		# SETUP request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()

			# Update RTSP sequence number
			self.rtspSeq += 1

			# Write the RTSP request to be sent
			request = f"SETUP {self.fileName} RTSP/1.0"
			request += f"\nCSeq: {self.rtspSeq}"
			request += f"\nTransport: RTP/UDP; client_port= {self.rtpPort}"

			# Keep track of the sent request
			self.requestSent = self.SETUP

			# Send the RTSP request using rtspSocket
			self.rtspSocket.send(request.encode())
			print("\nData Sent:\n" + request)
		
		# PLAY request
		elif requestCode == self.PLAY and self.state == self.READY:

			# Update RTSP sequence number
			self.rtspSeq += 1

			# Write the RTSP request to be sent
			request = f"PLAY {self.fileName} RTSP/1.0"
			request += f"\nCSeq: {self.rtspSeq}"
			request += f"\nSession: {self.sessionId}"

			# Keep track of the sent request
			self.requestSent = self.PLAY

			# Send the RTSP request using rtspSocket
			self.rtspSocket.send(request.encode())
			print("\nData Sent:\n" + request)
		
		# PAUSE request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:

			# Update RTSP sequence number
			self.rtspSeq += 1

			# Write the RTSP request to be sent
			request = f"PAUSE {self.fileName} RTSP/1.0"
			request += f"\nCSeq: {self.rtspSeq}"
			request += f"\nSession: {self.sessionId}"

			# Keep track of the sent request
			self.requestSent = self.PAUSE

			# Send the RTSP request using rtspSocket
			self.rtspSocket.send(request.encode())
			print("\nData Sent:\n" + request)
		
		# STOP request
		elif requestCode == self.STOP and not self.state == self.READY:

			# Update RTSP sequence number
			self.rtspSeq += 1

			# Write the RTSP request to be sent
			request = f"STOP {self.fileName} RTSP/1.0"
			request += f"\nCSeq: {self.rtspSeq}"
			request += f"\nSession: {self.sessionId}"

			# Keep track of the sent request
			self.requestSent = self.STOP

			# Send the RTSP request using rtspSocket
			self.rtspSocket.send(request.encode())
			print("\nData Sent:\n" + request)

		# TEARDOWN request
		elif requestCode == self.TEARDOWN and not self.state == self.READY:

			# Update RTSP sequence number
			self.rtspSeq += 1

			# Write the RTSP request to be sent
			request = f"TEARDOWN {self.fileName} RTSP/1.0"
			request += f"\nCSeq: {self.rtspSeq}"
			request += f"\nSession: {self.sessionId}"

			# Keep track of the sent request
			self.requestSent = self.TEARDOWN

			# Send the RTSP request using rtspSocket
			self.rtspSocket.send(request.encode())
			print("\nData Sent:\n" + request)
		
		# DESCRIBE request
		elif requestCode == self.DESCRIBE:
			self.descPort = 1024
			threading.Thread(target=self.recvDescription).start()

			# Update RTSP sequence number
			self.rtspSeq += 1

			# Write the RTSP request to be sent
			request = f"DESCRIBE {self.fileName} RTSP/1.0"
			request += f"\nCSeq: {self.rtspSeq}"
			request += f"\nDescPort: {self.descPort}"

			# Keep track of the sent request
			self.requestSent = self.DESCRIBE

			# Send the RTSP request using rtspSocket
			self.rtspSocket.send(request.encode())
			print("\nData Sent:\n" + request)

	def recvDescription(self):
		description = ""
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as descSocket:
			descSocket.bind(('', self.descPort))
			descSocket.listen(5)
			conn, addr = descSocket.accept()
			with conn:
				while True:
					data = conn.recv(1024)
					if not data:
						break
					description += data.decode('utf-8')
		print(description)

	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)

			if reply:
				self.parseRtspReply(reply)
			
			# Close the RTSP socket if TEARDOWN
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break		
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.decode("utf-8").split('\n')
		seqNum = int(lines[1].split(' ')[1])

		# Process only if the match seqNum between server and client
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])

			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200:
					if self.requestSent == self.SETUP:

						# Update RTSP state.
						self.state = self.READY

						# Open RTP port.
						self.openRtpPort()

					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING

					elif self.requestSent == self.PAUSE:
						# Print video data rate at PAUSE moment
						print(f"Video data rate: {self.totalDataRecvInBits/self.timer} bits per second")

						self.state = self.READY
						# The play thread exits. A new thread is created on resume.
						self.playEvent.set()
						
					elif self.requestSent == self.STOP:
						# Print packet statistic and video data rate
						print(f"Packet loss: {self.lostPacket}")
						print(f"Packet total: {self.frameNbr}")
						if self.frameNbr != 0:
							print(f"Packet loss rate: {self.lostPacket/self.frameNbr}")
						if self.timer != 0:
							print(f"Video data rate: {self.totalDataRecvInBits/self.timer} bits per second")

						# Change state
						self.state = self.READY
						
						# Reset everything
						self.frameNbr = 0
						self.timer = 0.0
						self.lostPacket = 0
						self.totalDataRecvInBits = 0

					elif self.requestSent == self.TEARDOWN:
						# Print packet statistic and video data rate
						print(f"Packet loss: {self.lostPacket}")
						print(f"Packet total: {self.frameNbr}")
						if self.frameNbr != 0:
							print(f"Packet loss rate: {self.lostPacket/self.frameNbr}")
						if self.timer != 0:
							print(f"Video data rate: {self.totalDataRecvInBits/self.timer} bits per second")

						# Flag the teardownAcked to close the socket
						self.state = self.INIT
						self.teardownAcked = 1
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		
		# Set the timeout value of the socket to 0.5sec
		self.rtpSocket.settimeout(0.5)
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.state = self.READY
			self.rtpSocket.bind(('', self.rtpPort))
		except:
			tkinter.messagebox.showwarning("Unable to Bind",
										f"Unable to bind PORT={self.rtpPort}")

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else:
			self.playMovie()