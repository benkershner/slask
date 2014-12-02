#!/usr/bin/env python
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from flask import Flask, request, make_response
from json import dumps, loads
from requests import post
from sys import exit


def parse_args():
    epilog = None

    parser = ArgumentParser(description='A Flask app to republish to Slack',
                            epilog=epilog,
                            formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument('--host',
                        default='0.0.0.0',
                        help='listen host')
    parser.add_argument('-p', '--port',
                        default=8080,
                        type=int,
                        help='listen port')
    parser.add_argument('--install-service',
                        choices=['upstart'],
                        help='install service wrapper')
    parser.add_argument('--private-key',
                        help='SSL private key file')
    parser.add_argument('--certificate',
                        help='SSL certificate file')
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='print verbose output')
    args = parser.parse_args()

    return (args._get_args(), dict(args._get_kwargs()))


def _post_message(token, text, channel='#general', username='Slask', payload={}):
    payload.update({'token': token,
                    'channel': channel,
                    'text': text,
                    'username': username})
    return post("https://slack.com/api/chat.postMessage", params=payload)


class slask():
    def _install_service(self):
        script = None
        location = None
        if self.install_service == 'upstart':
            script = '''\
description "Slask"

start on runlevel [2345]
stop on runlevel [016]

respawn
respawn limit 10 5

exec slask %s''' % ' '.join(['--%s %s' % (kwarg, getattr(self, kwarg))
                             for kwarg in dir(self)
                             if kwarg in ['host', 'port']])
            location = '/etc/init/slask.conf'
        else:
            raise RuntimeError('Invalid service type')
    
        with open(location, 'w') as f:
            f.write(script)


    def __init__(self, *args, **kwargs):
        for kwarg in kwargs:
            setattr(self, kwarg, kwargs[kwarg])

        if self.install_service is not None:
            self._install_service()
            exit(0)

        self.app = Flask(__name__)

        @self.app.route("/slask/help", methods=['GET'])
        def _handle_help():
            response = [{attr: list(getattr(rule, attr))
                         if isinstance(getattr(rule, attr), set)
                         else str(getattr(rule, attr))
                         for attr in dir(rule)
                         if attr in ['methods', 'rule']}
                        for rule in self.app.url_map._rules
                        if rule.rule.startswith('/slask/')]
            return make_response(dumps(response, indent=4), 200)

        @self.app.route("/slask/<token>", methods=['POST'])
        def _handle_one(token):
            r = _post_message(token, request.get_data())
            return make_response(r.text, r.status_code)

        @self.app.route("/slask/<token>/<channel>", methods=['POST'])
        def _handle_two(token, channel):
            r = _post_message(token, request.get_data(), channel)
            return make_response(r.text, r.status_code)

        @self.app.route("/slask/<token>/<channel>/<username>", methods=['POST'])
        def _handle_three(token, channel, username):
            r = _post_message(token, request.get_data(), channel, username)
            return make_response(r.text, r.status_code)

        @self.app.route("/slask/<token>/<channel>/<username>/<options>", methods=['POST'])
        def _handle_four(token, channel, username, options):
            if options.lower().startswith("0x"):
                options = int(options, 16)
            elif options.startswith("0"):
                options = int(options, 8)
            else:
                options = int(options)

            text = request.get_data()
            if options & (1 << 1):
                text = dumps(loads(text), indent=4)
            if options & (1 << 0):
                text = '```%s```' % text

            payload = {}
            payload['link_names'] = 1 if options & (1 << 2) else 0

            r = _post_message(token, text, channel, username, payload)
            return make_response(r.text, r.status_code)

    def run(self):
        context = None
        if self.private_key is not None and self.certificate is not None:
            from OpenSSL import SSL
            context = SSL.Context(SSL.TLSv1_2_METHOD)
            context.use_privatekey_file(self.private_key)
            context.use_certificate_file(self.certificate)

        self.app.run(host=self.host, port=self.port, debug=True, ssl_context=context)
