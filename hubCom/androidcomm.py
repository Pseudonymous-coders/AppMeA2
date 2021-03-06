#!/usr/bin/python3.5

"""
Creators: Pseudonymous
Date: November 1, 2016
License: GPLv3 (General Public License version 3)

File: androidcomm.py
Description: Asynchronous server/client to handle android accessory mode

"""

import usb.core
import usb.util
import fcntl
import struct
import time
import threading
import os
import sys
import socket
import json

sys.path.append("/usr/local/lib/python3.5/dist-packages")

import pyudev
import subprocess



try:
    from androidconfig import *
except (ImportError, SystemError):
    from .androidconfig import *

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
for i in range(0, 6):
    try:
        server.bind((TCP_BIND, TCP_PORT))
        break
    except OSError:
        print("Failed binding to port")
        time.sleep(0.5)
server.listen(TCP_CONN)

reading = True

context = pyudev.Context()


def get_phone_dev_path():
    for device in context.list_devices(subsystem='usb', ID_BUS='usb'):
        device_details = dict(device)

        id_vendor = ""
        dev_name = ""

        try:
            id_vendor = device_details["ID_VENDOR"]
            dev_name = device_details["DEVNAME"]
        except KeyError:
            pass

        if id_vendor == "BLU":
            # print("DEV PATH: %s" % dev_name)
            # pprint.pprint(dict(device))
            return dev_name
    return None


def reset_phone_usb_back():
    print("Attempting to find BLU phone")
    dev_path = get_phone_dev_path()

    if dev_path is None:
        print("No BLU phone plugged in")
        return False

    print("Found BLU phone path at: %s" % dev_path)

    try:
        proc = subprocess.Popen("resetusb %s" % dev_path, shell=True)

        proc.communicate()
        if proc.returncode != 0:
            raise ValueError("Could load usb device")
    except Exception as err:
        print("Failed reseting device! %s" % str(err))
        return False
    return True


def reset_phone_usb():
    phone_thread = threading.Thread(target=reset_phone_usb_back)
    phone_thread.setDaemon(True)
    phone_thread.start() 
    time.sleep(2)
    return True

def phone_daemon():
    task_num = 0
    while True:
        print("Starting phone search... daemon")
        try:
            sock = socket.socket(socket.AF_NETLINK,
                                 socket.SOCK_RAW,
                                 NETLINK_KOBJECT_UEVENT
                                 )

            sock.bind((os.getpid(), -1))
            vid = 0
            while True:
                data = sock.recv(512)
                try:
                    vid = parse_uevent(data)
                    print("VID: " + str(vid))
                    if vid is not None:
                        break
                except ValueError:
                    print("Failed parsing uevent")

            sock.close()
            with open("/home/udooer/Slumber/androidusbpy/PhoneVID.txt", "w") as vid_file:
                vid_file.write("%04X" % vid)
            accessory_task(vid)
        except ValueError as err:
            print("Error starting daemon: %s" % str(err))

        task_num += 1
        print("Task %d Completed" % task_num)


def check_vid_main():
    reset_phone_usb()

    time.sleep(1)  # Wait for driver reload

    vid_int = None
    with open("/home/udooer/Slumber/androidusbpy/PhoneVID.txt", "r") as vid_file:
        try:
            vid_temp = vid_file.readline().replace("\n", "")
            vid_int = int(vid_temp, 16)
        except Exception as err:
            print("Failed loading VID: %s" % str(err))

    access_test = accessory_task(vid_int) if vid_int is not None else "FAIL"

    if isinstance(access_test, str) or isinstance(access_test, bytes):
        if str(access_test) == "FAIL":
            print("Failed finding phone via pre-configured VID %04X" % (vid_int if vid_int is not None else int("0")))
            phone_daemon()


def parse_uevent(data: bytes):
    lines = data.split(b'\0')
    keys = []
    for line in lines:
        val = line.split(b'=')
        if len(val) == 2:
            keys.append((val[0], val[1]))

    attributes = dict(keys)
    if b'ACTION' in attributes and b'PRODUCT' in attributes:
        if attributes[b'ACTION'] == b'add':
            parts = attributes[b'PRODUCT'].split(b'/')
            return int(parts[0], 16)

    return None


def readbuffer(frombuff: list):
    startstr = ""
    for ind in frombuff:
        startstr += chr(ind)
    return startstr


def sendbuffer(toarr: str):
    for ind in list(toarr):
        yield ord(ind)


# noinspection PyBroadException
def send_error(conn: socket.socket, code: int, message: str, close: bool = False):
    try:
        conn.send(json.dumps(ERROR_JSON).encode('utf-8'))
    except Exception as err:
        print("Failed sending error: %s" % str(err))
        raise ValueError("Broken pipe")
    finally:
        try:
            if close:
                conn.close()
        except Exception:
            print("Failed closing the connection")


def start_accessory_mode(dev: usb.core, vid):
    print("Phone not yet in accessory mode,  VID %04X" % vid)

    accessory(dev)
    dev = usb.core.find(idVendor=ACCESSORY_VID)
    if dev is None:
        raise ValueError("Phone not found!")

    if dev.idProduct in ACCESSORY_PID:
        print("Phone is in accessory mode")
    else:
        raise ValueError("")


# noinspection PyBroadException
def accessory_task(vid):
    global reading
    try:
        dev = None
        tries_count = 0
        while dev is None and tries_count < 5:
            print("No Phone found... Tries: %d" % tries_count)
            dev = usb.core.find(idVendor=vid)
            time.sleep(0.5)
            tries_count += 1

        if dev is None:
            return "FAIL"

        print("Phone found! Continuing...")

        if dev.idProduct in ACCESSORY_PID:
            print("Phone is already in accessory mode")
        else:
            tries_count = 0
            while tries_count < TRY_ACCESS:
                try:
                    start_accessory_mode(dev, vid)
                    break
                except ValueError:
                    time.sleep(0.5)
                    tries_count += 1
                    print("Failed starting accessory mode!... Tries: %d" % tries_count)
            print("Attempting to continue with current state")

        tries_count = 0
        while tries_count < TRY_ACCESS:
            try:
                dev.set_configuration()
                break
            except Exception:
                print("Couldn't set phone configuration")
                tries_count += 1
                time.sleep(1)

        # Wait for the intent to finish... This is necessary
        time.sleep(1)

        dev = usb.core.find(idVendor=ACCESSORY_VID)

        if dev is None:
            dev = usb.core.find(idVendor=vid)

        if dev is None:
            print("The Phone is set to accessory mode but VID %04X not found" % vid)

        cfg = dev.get_active_configuration()
        if_num = cfg[(0, 0)].bInterfaceNumber
        intf = usb.util.find_descriptor(cfg, bInterfaceNumber=if_num)

        while True:
            conn, addr = server.accept()
            print("Connection established with", addr)

            # Output stream
            ep_out = usb.util.find_descriptor(
                intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            )

            # Input stream
            ep_in = usb.util.find_descriptor(
                intf, custom_match=lambda er: usb.util.endpoint_direction(er.bEndpointAddress) == usb.util.ENDPOINT_IN
            )

            try:
                conn.send(json.dumps(READY_JSON).encode('utf-8'))
            except Exception:
                print("Failed sending initial ready packet")

            writer_thread = threading.Thread(target=writer, args=(ep_out, conn,))
            writer_thread.setDaemon(True)
            writer_thread.start()

            last_print = False

            while reading:
                try:
                    try:
                        size_sent = int(str(readbuffer(ep_in.read(SIZEBUFFER, timeout=TIMEOUT))))
                    except Exception as err:
                        if not last_print:
                            print("Failed getting size of packet: %s" % str(err))
                            last_print = True
                        continue

                    last_print = False
                    got_data = str(readbuffer(ep_in.read(size_sent, timeout=TIMEOUT)))
                    print("Got data:\nSIZE: %d\nDATA: %s" % (size_sent, got_data))
                    try:
                        conn.send(got_data.encode('utf-8'))
                        print("Wrote: %s" % got_data)
                    except socket.error:
                        print("Failed getting data")
                        try:
                            send_error(conn, code=5, message="Failed receiving data from the phone", close=False)
                        except ValueError:
                            break
                except (KeyboardInterrupt, InterruptedError):
                    break
                except usb.core.USBError as err:
                    try:
                        send_error(conn, code=6, message="Failed receiving data from the phone", close=False)
                    except ValueError:
                        break
                    print("Failed reading from app: %s" % str(err))
            print("Finished reading from device\nAttempting to quit writer")
            reading = False
            writer_thread.join()
            print("Finishing with android phone")

            try:
                conn.close()
            except socket.error:
                print("Failed closing tcp connection")

            reading = True
    except Exception as err:
        print("Error %s\n\n\nClosing server!" % str(err))
        server.close()
        exit(1)


# noinspection PyBroadException
def writer(ep_out: usb.util, conn: socket.socket):
    global reading
    while reading:
        try:
            data_recv = conn.recv(TCP_BUFF).decode('utf-8')
            #all_packs = []
            #all_packs.append(data_recv)
            #packets = 0
            '''
            is_large = False

            if "response" in data_recv and "nightUpdate" in data_recv: 
                is_large = True
                while not "]}}" in data_recv: 
                    data_recv_temp = conn.recv(TCP_BUFF).decode('utf-8')
                    data_recv += data_recv_temp
                    if data_recv is None or len(str(data_recv)) == 0:
                        break
                    packets += 1
                    all_packs.append(data_recv_temp)
                    print("Got the packet number: %d" % packets)

            print("GOT THE TOTAL PACKET")
            '''

            # check_resp = {"check": data_recv}
            # conn.send(json.dumps(check_resp).encode('utf-8'))
            print("RAW DATA FROM NODE: %s" % data_recv)
        except Exception:
            print("Failed reading from socket")
            try:
                send_error(conn, code=2, message="Failed sending to phone", close=False)
            except ValueError:
                break
            continue

        try:
            if str(data_recv)[-1] is not "}" and str(data_recv).count("response") > 1:
                try:
                    send_error(conn, code=4, message="Failed malformed json", close=False)
                except ValueError:
                    break
        except Exception:
            try:
                send_error(conn, code=4, message="Failed nothing send", close=False)
            except ValueError:
                break

        '''
        # Double check json before sending to the phone
        try:
            json_data = json.loads(str(data_recv))
        except json.JSONDecodeError as error:
            print("Error decoding json %s" % str(error))
            try:
                send_error(conn, code=4, message="Failed parsing json", close=False)
            except ValueError:
                break
            continue
        '''

        #if not is_large:
        buffer_send = list(sendbuffer(data_recv))

        try:
            ep_out.write(list(sendbuffer(str(len(buffer_send)))), timeout=TIMEOUT)
            print("Wrote size %d" % len(buffer_send))
        except usb.core.USBError:
            print("Failed sending package size to phone")
            continue
    
        '''else:
            cur_packet = 0
            for pack in all_packs:
                buffer_send = list(sendbuffer(str(pack)))
                
                print("Writing packet %s" % pack)


                try:
                    ep_out.write(list(sendbuffer(str(len(buffer_send)))), timeout=TIMEOUT)
                    print("Wrote expected, size, size of %d on packet %d" % (len(buffer_send), cur_packet))
                except usb.core.USBError:
                    print("Failed sending size packet %d" % cur_packet)
                    continue

                try:
                    length = ep_out.write(buffer_send, timeout=TIMEOUT)
                    print("Sent to phone packet %d" % cur_packet)
                except usb.core.USBError:
                    print("Error sending full packet (%d) to phone" % cur_packet)

                cur_packet += 1
        '''

        #if not is_large:
        try:
            length = ep_out.write(buffer_send, timeout=TIMEOUT)
            #print("Sent %d" % length)
            #print("Sending %s to phone, length %d" % (str(json_data), length))
        except usb.core.USBError:
            print("Error sending to phone")
            try:
                send_error(conn, code=3, message="Failed sending to phone", close=False)
            except ValueError:
                break
    print("Finished writing")
    reading = False


def accessory(dev: usb.util):
    version = dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_IN,
        51, 0, 0, VERSION_CONTROLLER)

    print("Version is: %d" % struct.unpack('<H', version))

    # Test version usb core outputs with original size
    assert dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT,
        52, 0, 0, MANUFACTURE) == len(MANUFACTURE)

    assert dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT,
        52, 0, 1, MODEL) == len(MODEL)

    assert dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT,
        52, 0, 2, DESCRIPTION) == len(DESCRIPTION)

    assert dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT,
        52, 0, 3, VERSION) == len(VERSION)

    assert dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT,
        52, 0, 4, URL) == len(URL)

    assert dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT,
        52, 0, 5, SERIAL) == len(SERIAL)

    dev.ctrl_transfer(
        usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_OUT,
        53, 0, 0, None)

    time.sleep(1)


if __name__ == "__main__":
    pid_file = '/root/androidcomm.pid'
    fp = open(pid_file, 'w')
    try:
        fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        exit(0)

    check_vid_main()
