from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import QtCore
from bottle import route, run, request, response
from json import dumps
import threading, queue
from threading import Timer
import logging
import serial
import time
from argparse import ArgumentParser

# > python .\gateout.py -H 0.0.0.0 -P COM17 -WP 8080 -br 9600

logging.basicConfig(filename='gateout.log', filemode='a+', format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')

DEFINITION_OUTPUT = ['!OUT1ONOK|','!OUT1OFFOK|','!TRIG1OK|']
RESPONSE_TIMEOUT = 5.0 #seconds
loop_unlock = False
timer_timeout = None
response_list = []

"""
----------------------------------------------------------------------------------------------------------
REGISTER PARSER
----------------------------------------------------------------------------------------------------------
"""
parser = ArgumentParser()
parser.add_argument("-H", "--hostname", dest="hostname", help="Set hostname")
parser.add_argument("-P", "--port", dest="port", help="set port")
parser.add_argument("-WP", "--webport", dest="webport", type=int, default=8080, help="set web port")
parser.add_argument("-br", "--baudrate", dest="baudrate", help="set device baudrate")
parser.add_argument("-bz", "--bytesize", dest="bytesize", type=int, default=8, help="set bytesize")
parser.add_argument("-pa", "--parity", dest="parity", default='N', help="set parity")
parser.add_argument("-sb", "--stopbits", dest="stopbits", type=int, default=1, help="set stopbits")
parser.add_argument("-to", "--timeout", dest="timeout", default=None, help="set timeout")
parser.add_argument("-xx", "--xonxoff", dest="xonxoff", type=int, default=0, help="set xonxoff")
parser.add_argument("-rc", "--rtscts", dest="rtscts", type=int, default=0, help="set rtscts")
args = parser.parse_args()

""" 
----------------------------------------------------------------------------------------------------------
FUNCTION TO STOP ITERATE (WHILE)
----------------------------------------------------------------------------------------------------------
"""
def release_lock():
    global loop_unlock
    loop_unlock = True

# create the application
app = QApplication([])
app.setQuitOnLastWindowClosed(False)

# create the icon
icon = QIcon("pcless.ico")

# create the tray icon 
tray = QSystemTrayIcon()
tray.setIcon(icon)
tray.setVisible(True)

# create the menu for tray icon
menu = QMenu()

# add exit item to menu 
exitAction = QAction("&Exit")
menu.addAction(exitAction)
exitAction.triggered.connect(exit)

# add the menu to the tray
tray.setContextMenu(menu)

"""
----------------------------------------------------------------------------------------
Serial configuration
----------------------------------------------------------------------------------------
"""
ser = serial.Serial()
ser.port = args.port
ser.baudrate = args.baudrate
ser.bytesize = args.bytesize
ser.parity = args.parity
ser.stopbits = args.stopbits
ser.timeout = args.timeout
ser.xonxoff = args.xonxoff
ser.rtscts = args.rtscts

# connect serial
try :
	ser.open()
except Exception as e :
	logging.error(str(e))

def task_connect():
	global ser
	try  :
		if(ser.isOpen() == False):
			try :
				ser.open()
			except Exception as e :
				print(e)
				logging.error(str(e))
		else :
			bytesToRead = ser.inWaiting()
			serial_decode = ser.read(bytesToRead).decode()
			if (serial_decode != ''):
				response_list.append(serial_decode)
	except Exception as e :
		print(e)
		try :
			print("Close connection and reconnecting device in port "+args.port)
			ser.close()
		except Exception as e_reconnect :
			print(e_reconnect)
			logging.error(str(e_reconnect))
		logging.error(str(e))

	try :
		bytesToRead = ser.inWaiting()
		serial_response += ser.read(bytesToRead).decode()
	except Exception as e :
		pass

# check connection in every 2 seconds
timer_reconnect = QtCore.QTimer()
#timer_reconnect.setSingleShot(True) # only once
timer_reconnect.timeout.connect(task_connect)
timer_reconnect.start(100)

"""
----------------------------------------------------------------------------------------
Microservice controller (Bottle Framework)
----------------------------------------------------------------------------------------
"""

@route('/', method='GET')
def index():
    rv = { "status": "ok", "desc": "ready to communication to devices" }
    response.content_type = 'application/json'
    return dumps(rv)

@route('/cmd', method='POST')
def command():
	global ser
	global loop_unlock
	global timer_timeout

	# clear result
	del response_list[:]

	# reet lock loop
	loop_unlock = False

	# reset timer and start again
	if(timer_timeout != None):
		if(timer_timeout.is_alive()):
			timer_timeout.cancel()

	# timer response
	timer_timeout = Timer(RESPONSE_TIMEOUT, release_lock)
	timer_timeout.start()

	# get request
	cmd = request.forms.get('cmd')
	status = "failed"
	desc = ""

	# send serial command
	ser.write(cmd.encode())

	while True :
		# release lock
		if loop_unlock : break

		stop_loop = False
		for DF in DEFINITION_OUTPUT :
			if DF in response_list :
				desc = "complete"
				status = "ok"
				stop_loop = True
				break

		if stop_loop : break

		time.sleep(0.2)

	try :
		rv = { "status": status, "response": response_list, "description": desc }
		response.content_type = 'application/json'
	except Exception as e :
		print(e)

	return dumps(rv)

webservice = threading.Thread(target=run, kwargs=dict(host=args.hostname,port=args.webport), daemon=True)
webservice.start()

# start application execution 
app.exec_()