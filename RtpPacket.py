import sys
from time import time
from VideoStream import VideoStream

class RtpPacket:
	
	HEADER_SIZE = 12

	def __init__(self):
		self.header = bytearray(self.HEADER_SIZE)

	def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload):
		"""Encode the RTP packet with header fields and payload."""
		timestamp = int(time())
		print(f"timestamp: {timestamp}")

		#header (12 BYTES) = version + padding + extension + cc + seqnum + marker + pt + ssrc
		self.header = bytearray(self.HEADER_SIZE)

		self.header[0] = version << 6						# 2 bits for version
		self.header[0] = self.header[0] | padding << 5		# 1 bit for padding
		self.header[0] = self.header[0] | extension << 4	# 1 bit for extension
		self.header[0] = self.header[0] | (cc & 0xF)		# 4 remained bits for contributing sources

		self.header[1] = marker << 7						# 1 bit for marker
		self.header[1] = self.header[1] | (pt & 0x7F)		# 7 remained bits for payload type

		# 2 bytes for sequence number
		self.header[2] = (seqnum >> 8) & 0xFF
		self.header[3] = seqnum & 0xFF

		# 4 bytes for timestamp
		self.header[4] = (timestamp >> 24) & 0xFF
		self.header[5] = (timestamp >> 16) & 0xFF
		self.header[6] = (timestamp >> 8) & 0xFF
		self.header[7] = timestamp & 0xFF

		# 4 bytes for synchronization source identifier
		self.header[8] = (ssrc >> 24) & 0xFF
		self.header[9] = (ssrc >> 16) & 0xFF
		self.header[10] = (ssrc >> 8) & 0xFF
		self.header[11] = ssrc & 0xFF

		# Get the payload from the argument
		self.payload = payload

	def decode(self, byteStream):
		"""Decode the RTP packet."""
		self.header = bytearray(byteStream[:self.HEADER_SIZE])
		self.payload = byteStream[self.HEADER_SIZE:]

	def version(self):
		"""Return RTP version."""
		return int(self.header[0] >> 6)

	def seqNum(self):
		"""Return sequence (frame) number."""
		seqNum = self.header[2] << 8 | self.header[3]
		return int(seqNum)

	def timestamp(self):
		"""Return timestamp."""
		timestamp = self.header[4] << 24 | self.header[5] << 16 | self.header[6] << 8 | self.header[7]
		return int(timestamp)

	def payloadType(self):
		"""Return payload type."""
		pt = self.header[1] & 127
		return int(pt)

	def getPayload(self):
		"""Return payload."""
		return self.payload

	def getPacket(self):
		"""Return RTP packet."""
		return self.header + self.payload