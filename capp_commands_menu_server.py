# Ищем доступных клиентов

from __future__ import print_function

import urwid

import socket
import time

import asyncio

from datetime import datetime
import sys
import weakref

import urwid
from urwid.raw_display import Screen
from urwid.display_common import BaseScreen

import bottle
import os.path
from os import listdir
from bottle import route, template, static_file

WEB_SERVER_PORT=8988
URWID_SERVER_PORT=8989

import logging
logging.basicConfig()

loop = asyncio.get_event_loop()

def unhandled(key):
    if key == 'ctrl c':
        raise urwid.ExitMainLoop

async def start_broadcast():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    server.settimeout(0.2)
    server.bind(("", 44444))

    server_magic_number=3839055

    message = "%1 server_ping" % (server_magic_number)
    message = message.encode

    while True:
        server.sendto(message, ('<broadcast>', 37020))
        time.sleep(1)

async def start_command_server():
    pass

def build_widgets():
    input1 = urwid.Edit('What is your name? ')
    input2 = urwid.Edit('What is your quest? ')
    input3 = urwid.Edit('What is the capital of Assyria? ')
    inputs = [input1, input2, input3]

    def update_clock(widget_ref):
        widget = widget_ref()
        if not widget:
            # widget is dead; the main loop must've been destroyed
            return

        widget.set_text(datetime.now().isoformat())

        # Schedule us to update the clock again in one second
        loop.call_later(1, update_clock, widget_ref)

    clock = urwid.Text('')
    update_clock(weakref.ref(clock))

    return urwid.Filler(urwid.Pile([clock] + inputs), 'top')

class AsyncScreen(Screen):
    """An urwid screen that speaks to an asyncio stream, rather than polling
    file descriptors.
    This is fairly limited; it can't, for example, determine the size of the
    remote screen.  Fixing that depends on the nature of the stream.
    """
    def __init__(self, reader, writer, encoding="utf-8"):
        self.reader = reader
        self.writer = writer
        self.encoding = encoding

        Screen.__init__(self, None, None)

    _pending_task = None

    def write(self, data):
        self.writer.write(data.encode(self.encoding))

    def flush(self):
        pass

    def hook_event_loop(self, event_loop, callback):
        # Wait on the reader's read coro, and when there's data to read, call
        # the callback and then wait again
        def pump_reader(fut=None):
            if fut is None:
                # First call, do nothing
                pass
            elif fut.cancelled():
                # This is in response to an earlier .read() call, so don't
                # schedule another one!
                return
            elif fut.exception():
                pass
            else:
                try:
                    self.parse_input(
                        event_loop, callback, bytearray(fut.result()))
                except urwid.ExitMainLoop:
                    # This will immediately close the transport and thus the
                    # connection, which in turn calls connection_lost, which
                    # stops the screen and the loop
                    self.writer.abort()

            # create_task() schedules a coroutine without using `yield from` or
            # `await`, which are syntax errors in Pythons before 3.5
            self._pending_task = event_loop._loop.create_task(
                self.reader.read(1024))
            self._pending_task.add_done_callback(pump_reader)

        pump_reader()

    def unhook_event_loop(self, event_loop):
        if self._pending_task:
            self._pending_task.cancel()
            del self._pending_task

class UrwidProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        print("Got a client!")
        self.transport = transport

        # StreamReader is super convenient here; it has a regular method on our
        # end (feed_data), and a coroutine on the other end that will
        # faux-block until there's data to be read.  We could also just call a
        # method directly on the screen, but this keeps the screen somewhat
        # separate from the protocol.
        self.reader = asyncio.StreamReader(loop=loop)
        screen = AsyncScreen(self.reader, transport)

        main_widget = build_widgets()
        self.urwid_loop = urwid.MainLoop(
            main_widget,
            event_loop=urwid.AsyncioEventLoop(loop=loop),
            screen=screen,
            unhandled_input=unhandled,
        )

        self.urwid_loop.start()

    def data_received(self, data):
        self.reader.feed_data(data)

    def connection_lost(self, exc):
        print("Lost a client...")
        self.reader.feed_eof()
        self.urwid_loop.stop()

@route('/')
def index():
    tmpl = """<!DOCTYPE html>
<html>
<head><title>Bottle of Aqua</title></head>
</body>
<h3>List of files:</h3>
<ul>
  % for item in files:
    <li><a href="/files/{{item}}">{{item}}</a></li>
  % end
</ul>
</body>
</html>
"""
    files = [file_name for file_name in listdir(os.path.join(root, 'files'))
                        if os.path.isfile(os.path.join(root, 'files', file_name))]
    return template(tmpl, files=files)


@route('/files/<filename>')
def server_static(filename):
    return static_file(filename, root=os.path.join(root,'files'))


class AquaServer(bottle.ServerAdapter):
    """Bottle server adapter"""
    def run(self, handler):
        import asyncio
        import logging
        from aqua.wsgiserver import WSGIServer
        
        logging.basicConfig(level=logging.ERROR)
        loop = asyncio.get_event_loop()
        server = WSGIServer(handler, loop=loop)
        server.bind(self.host, self.port)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass # Press Ctrl+C to stop
        finally:
            server.unbindAll()
            loop.close()

if __name__ == '__main__':
    bottle.run(server=AquaServer, port=5000)

def start_urwid_server():
    coro = loop.create_server(UrwidProtocol, port=URWID_SERVER_PORT)
    loop.run_until_complete(coro)
    print("OK, good to go!  Try this in another terminal (or two):")
    print()
    print("    socat TCP:127.0.0.1:{0} STDIN,rawer".format(URWID_SERVER_PORT))
    print()
    loop.run_forever()

def main():
    start_broadcast()
    start_command_server()
    start_urwid_server()

main()