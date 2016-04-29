"""
Get other data out of the parsed data
"""
import datetime


def getScansPerDevicePerNode(data):
	"""
	Returns data as scans per device per node.
	:param data: Data as returned by the parse functions
	:return: dict with:
		["scansPerDev"]:
			["<device address>"]:
				["<node address>"]:
					["time"]: timestamp
					["rssi"]: rssi
		["minRssi"]: minimal rssi of all scans
		["maxRssi"]: maximal rssi of all scans
	"""
	scans = data["scans"]
	scansPerDev = {}
	minRssi = 127
	maxRssi = -127
	for nodeAddr in scans:
		for scan in scans[nodeAddr]:
			devAddr = scan["address"]
			timestamp = scan["time"]
			rssi = scan["rssi"]
			entry = {"time":timestamp, "rssi":rssi}
			if (devAddr not in scansPerDev):
				scansPerDev[devAddr] = {}

			if (nodeAddr not in scansPerDev[devAddr]):
				scansPerDev[devAddr][nodeAddr] = [entry]
			else:
				scansPerDev[devAddr][nodeAddr].append(entry)
			if (rssi > maxRssi):
				maxRssi = rssi
			if (rssi < minRssi):
				minRssi = rssi
	return {"scansPerDev":scansPerDev, "minRssi":minRssi, "maxRssi":maxRssi}



def getFrequencyPerDevicePerNode(data, windowSize, stepSize):
	"""
	Returns the number of time each device was scanned by each node, over time.
	:param data: Data as returned by the parse functions
	:param windowSize: Size of bucket window in seconds
	:param stepSize: Size of each time step in seconds
	:return dict with:
		["startTimes"]: [timestamp, timestamp, ...]
		["numScansPerDev"]:
			["<device address>"]:
				["<node address>"]: [rssi, rssi, ...]
	"""
	startTimestamp = data["startTimestamp"]
	endTimestamp = data["endTimestamp"]
	data2 = getScansPerDevicePerNode(data)
	scansPerDev = data2["scansPerDev"]
	startTimes = range(int(startTimestamp), int(endTimestamp)-windowSize+1, stepSize)
	numScans = {}
	for devAddr in scansPerDev:
		if (devAddr not in numScans):
			numScans[devAddr] = {}
		for tInd in range(1,len(startTimes)):
			for nodeAddr in scansPerDev[devAddr]:
				if (nodeAddr not in numScans[devAddr]):
					numScans[devAddr][nodeAddr] = [0.0]
				else:
					numScans[devAddr][nodeAddr].append(0.0)
				for scan in scansPerDev[devAddr][nodeAddr]:
					timestamp = scan["time"]
					if (startTimes[tInd] <= timestamp < startTimes[tInd]+windowSize):
						numScans[devAddr][nodeAddr][-1] += 1.0
				# Beacon 0, 5, 9 scan six times faster atm
				if (nodeAddr in ["E8:00:93:4E:7B:D9", "F5:A7:4B:49:8C:7D", "FE:04:85:F9:8F:E9"]):
					numScans[devAddr][nodeAddr][-1] /= 6.0
	return {"numScansPerDev":numScans, "startTimes": startTimes}



def getAverageRssiPerDevicePerNode(data, windowSize, stepSize):
	"""
	Returns the average rssi of each device with each node, over time.
	:param data: Data as returned by the parse functions
	:param windowSize: Size of averaging window in seconds
	:param stepSize: Size of each time step in seconds
	:return dict with:
		["startTimes"]: [timestamp, timestamp, ...]
		["avgRssiPerDev"]:
			["<device address>"]:
				["<node address>"]: [rssi, rssi, ...]
	"""
	startTimestamp = data["startTimestamp"]
	endTimestamp = data["endTimestamp"]
	data2 = getScansPerDevicePerNode(data)
	scansPerDev = data2["scansPerDev"]
	startTimes = range(int(startTimestamp), int(endTimestamp)-windowSize+1, stepSize)
	avgRssi = {}
	for devAddr in scansPerDev:
		avgRssi[devAddr] = {}
		for nodeAddr in scansPerDev[devAddr]:
			avgRssi[devAddr][nodeAddr] = [-105.0]*(len(startTimes))
		for tInd in range(0,len(startTimes)):
			for nodeAddr in scansPerDev[devAddr]:
				rssiSum = 0.0
				numScans = 0
				for scan in scansPerDev[devAddr][nodeAddr]:
					timestamp = scan["time"]
					rssi = scan["rssi"]
					if (startTimes[tInd] <= timestamp < startTimes[tInd]+windowSize):
						rssiSum += rssi
						numScans += 1
				if (numScans > 0):
					avgRssi[devAddr][nodeAddr][tInd] = rssiSum / numScans
	return {"avgRssiPerDev":avgRssi, "startTimes": startTimes}



def getPathPerDevice(data, windowSize, stepSize, nodeLocations):
	"""
	Returns the estimated positions of each device, over time.
	:param data: Data as returned by the parse functions
	:param windowSize: Size of averaging window in seconds
	:param nodeLocations: position of each scanning node
	:return dict with:
		["startTimes"]: [timestamp, timestamp, ...]
		["pathPerDevice"]:
			["<device address>"]:
				["x"]: [float, float, float, ...]
				["y"]: [float, float, float, ...]
	"""
	data2 = getFrequencyPerDevicePerNode(data, windowSize, stepSize)
	numScans = data2["numScansPerDev"]
	startTimes = data2["startTimes"]
	data3 = getAverageRssiPerDevicePerNode(data, windowSize, stepSize)
	avgRssi = data3["avgRssiPerDev"]

	paths = {}
	for dev in numScans:
		pathX = [0.0]*len(startTimes)
		pathY = [0.0]*len(startTimes)
		paths[dev] = {"x":pathX, "y":pathY}

		for tInd in range(0, len(startTimes)):
			weightSum = 0
			weights = {}
			for nodeAddr in numScans[dev]:
#				weights[nodeAddr] = numScans[dev][nodeAddr][tInd] - 0.0
				weights[nodeAddr] = (avgRssi[dev][nodeAddr][tInd] + 105.0)**2
				weightSum += weights[nodeAddr]

#			# If almost no node scanned the device, assume it stayed on the same location?
#			if (weightSum < 1.0 and tInd > 0):
#				pathX[tInd] = pathX[tInd-1]
#				pathY[tInd] = pathY[tInd-1]
			# If almost no node scanned the device, assume it's not here
			if (weightSum < 1.0):
				pathX[tInd] = float("NaN")
				pathY[tInd] = float("NaN")
				continue

			for nodeAddr in numScans[dev]:
				weight = weights[nodeAddr] / weightSum
				pathX[tInd] += weight * nodeLocations[nodeAddr]["x"]
				pathY[tInd] += weight * nodeLocations[nodeAddr]["y"]
	return {"pathPerDevice":paths, "startTimes":startTimes}


def getTimedMeasurements(*data, **kwargs):
	"""
	Returns data as a list of timestamps with corresponding measurements.
	:param *data: One or more data structures as returned by the parse functions
	:return: dict with:
		["data"]:
			["<timestamp>"]:
				["<node address>"]:
					["<device address>"]: [rssi, rssi, ...]
		["startTimestamp"]
		["endTimestamp"]
	"""
	output = {
		"data":{}
	}
	startTimestamp = -1
	endTimestamp = -1
	for d in data:
		for node in d["scans"]:
			for entry in d["scans"][node]:
				if "start" in kwargs and entry["time"] < kwargs["start"]:
					continue
				if "end" in kwargs and entry["time"] > kwargs["end"]:
					continue

				if entry["time"] < startTimestamp or startTimestamp == -1:
					startTimestamp = entry["time"]
				if entry["time"] > endTimestamp or endTimestamp == -1:
					endTimestamp = entry["time"]

				timeStamp = str(round(entry["time"],1))
				device = entry["address"]
				if timeStamp not in output["data"]:
					output["data"][timeStamp] = {}
				if node not in output["data"][timeStamp]:
					output["data"][timeStamp][node] = {}
				if device not in output["data"][timeStamp][node]:
					output["data"][timeStamp][node][device] = []
				output["data"][timeStamp][node][device].append(entry["rssi"])
	output["startTimestamp"] = startTimestamp
	output["endTimestamp"] = endTimestamp
	return output



if __name__ == '__main__':
	print "File not intended as main."