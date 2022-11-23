# Здесь находится процес который ловит бродкасты от сервера и подключается к нему

import socket
import httpx

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
client.bind(("", 37020))

server_magic_number=3839055

while True:
    data, addr = client.recvfrom(1024)
    print(addr)
    data = "%s" % data
    if data[0:7] == server_magic_number:
        try:
            while True:
                sADDR = "http://%1/" % addr
                r = httpx.post(sADDR, data={'key': 'value'})
        except:
            pass