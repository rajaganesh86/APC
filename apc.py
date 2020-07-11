#!/usr/bin/env python
'''
APC IP Power Controller

'''

import pexpect
import os
import re
import time
import sys
import pdb

from argparse import ArgumentParser
from lockfile import FilesystemLock

APC_ESCAPE = '\033'

APC_LOGOUT = 'bye'

APC_VERSION_PATTERN = re.compile(' v(\d+\.\d+\.\d+)')

APC_DEFAULT_HOST     = os.environ.get('APC_HOST',     '192.168.9.6')
APC_DEFAULT_USER     = os.environ.get('APC_USER',     'apc')
APC_DEFAULT_PASSWORD = os.environ.get('APC_PASSWORD', 'apc')

LOCK_PATH = '/tmp/apc.lock'
LOCK_TIMEOUT = 60

class APC:
    def __init__(self, options):
        self.host = options.host
        self.user = options.user
        self.password = options.password
        self.verbose = options.verbose
        self.quiet = options.quiet
        self.connect()

    def info(self, msg):
        if not self.quiet:
            print(msg)

    def notify(self, outlet_name, state):
        print('APC %s: %s %s' % (self.host, outlet_name, state))

    def sendnl(self, a):
        self.child.send(a + '\r')
        if self.verbose:
            print(self.child.before)

    def _lock(self):
        self.info('Acquiring lock %s' % (LOCK_PATH))

        self.apc_lock = FilesystemLock(LOCK_PATH)

        count = 0
        while not self.apc_lock.lock():
            time.sleep(1)
            count += 1
            if count >= LOCK_TIMEOUT:
                raise SystemError('Cannot acquire %s\n' % (LOCK_PATH))

    def _unlock(self):
        self.apc_lock.unlock()

    def connect(self):
        self._lock()

        self.info('Connecting to APC @ %s' % self.host)
        self.child = pexpect.spawn('telnet %s' % self.host)

        self.child.timeout = 10
        self.child.setecho(True)

        self.child.expect('User Name : ')
        time.sleep(1)
        self.child.send(self.user + '\r')
        time.sleep(1)
        self.child.expect('Password  : ')
        self.child.send(self.password + '\r')
        self.child.send('\r\n')
        time.sleep(2)
        self.child.expect('apc>')
        header = self.child.before
        match = APC_VERSION_PATTERN.search(str(header))

    def get_outlet(self, outlet):
        if str(outlet) in ['*', '+', 'all']:
            return ('all', 'ALL outlets')
        else:
            # Assume integer outlet
            try:
                outlet = int(outlet)
                return (outlet, 'Outlet #%d' % outlet)

            except:
                raise SystemExit('Bad outlet: [%s]' % outlet)

    def get_command_result(self):
        self.child.expect('E000: Success')
        print(self.child.after)

    def get_result(self, outlet):
        try: 
            self.child.logfile=sys.stdout
            self.child.expect('%d:' %outlet)
        except:
            self.child.expect('E102:')
            raise SystemExit('Bad outlet: [%s]' % outlet)

    def _escape_to_main(self):
        for i in range(6):
            self.child.send(APC_ESCAPE)

    def reboot(self, outlet, secs):
        (outlet, outlet_name) = self.get_outlet(outlet)

        if secs in range(5, 61):
            cmd1 = 'olRbootTime %d %d' %(outlet, secs)
        else:
            print("Enter time delay in seconds between 5 and 60")
            raise SystemExit(1)
        cmd2 = 'olReboot %d' %outlet

        self.sendnl(cmd1)
        self.sendnl(cmd2)

        self.get_command_result()

        self.notify(outlet_name, 'Rebooted')

    def on_off(self, outlet, on):
        (outlet, outlet_name) = self.get_outlet(outlet)

        if on:
            cmd = 'olOn %d' %outlet
            str_cmd = 'On'
        else:
            cmd = 'olOff %d' %outlet
            str_cmd = 'Off'

        self.sendnl(cmd)

        self.get_command_result()

        self.notify(outlet_name, str_cmd)

    def get(self, outlet):
        (outlet, outlet_name) = self.get_outlet(outlet)

        if outlet == 'all': 
            cmd = 'olStatus %s' %outlet
            self.child.logfile=sys.stdout
            self.child.send(cmd + '\r')
            time.sleep(2)
            self.child.expect('apc>')
            print(self.child.readline())
        else:
            cmd = 'olStatus %d' %outlet
            self.sendnl(cmd)
            self.get_result(outlet)

    def on(self, outlet):
        self.on_off(outlet, True)

    def off(self, outlet):
        self.on_off(outlet, False)

    def debug(self):
        self.child.interact()

    def disconnect(self):
        # self._escape_to_main()

        self.sendnl(APC_LOGOUT)
        self.child.sendeof()
        if not self.quiet:
            print('DISCONNECTED from %s' % self.host)

        if self.verbose:
            print('[%s]' % ''.join(self.child.readlines()))

        self.child.close()
        self._unlock()


def main():
    parser = ArgumentParser(description='APC Python CLI')
    parser.add_argument('--host', action='store', default=APC_DEFAULT_HOST,
                        help='Override the host')
    parser.add_argument('--user', action='store', default=APC_DEFAULT_USER,
                        help='Override the username')
    parser.add_argument('--password', action='store', default=APC_DEFAULT_PASSWORD,
                        help='Override the password')

    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose messages')
    parser.add_argument('--quiet', action='store_true',
                        help='Quiet')
    parser.add_argument('--debug', action='store_true',
                        help='Debug mode')
    parser.add_argument('--reboot', action='store',
                        help='Reboot an outlet')
    parser.add_argument('--off', action='store',
                        help='Turn off an outlet')
    parser.add_argument('--on', action='store',
                        help='Turn on an outlet')
    parser.add_argument('--get', action='store',
                        help='Get the status of an outlet. Enter number 1 to 8 or all')
    args = parser.parse_args()

    is_command_specified = (args.reboot or args.debug or args.on or args.off or args.get)

    if not is_command_specified:
        parser.print_usage()
        raise SystemExit(1)

    try:
        apc = APC(args)
    except pexpect.TIMEOUT as e:
        raise SystemExit('ERROR: Timeout connecting to APC')

    if args.debug:
        apc.debug()
    else:
        try:
            if args.reboot:
                apc.reboot(args.reboot)
            elif args.on:
                apc.on(args.on)
            elif args.off:
                apc.off(args.off)
            elif args.get:
                apc.get(args.get)
        except pexpect.TIMEOUT as e:
            raise SystemExit('APC failed!  Pexpect result:\n%s' % e)
        finally:
            apc.disconnect()


if __name__ == '__main__':
    main()
