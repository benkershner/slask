#!/usr/bin/env python
from boto.sns import connect_to_region
from boto.exception import BotoServerError
from json import dumps, loads
from re import match
from sys import stdin, stderr
import boto
from argparse import ArgumentParser, RawDescriptionHelpFormatter


class consul2sns():
    # Turn the `consul watch` array into a dictionary, with 'Node' as the primary
    # key and 'CheckID' as the secondary key.
    def _ingest_state(array):
        state = {}
        for check in array:
            state.setdefault(check['Node'], {}).update({check['CheckID']: check})
        return state
    
    
    def _status_delta(then, now):
        return [dict(now[node][checkid].items() +
                     [("PreviousStatus", then[node][checkid]["Status"])])
                for node in now
                for checkid in now[node]
                if now[node][checkid]['Status'] != then[node][checkid]['Status']]
    
    
    def _get_arn(args):
        # arn:aws:sns:us-east-1:019661432785:dev-alerts
        # No easy wqy to get owner_id :(
        arn = args.topic.split(':')
        if len(arn) == 1:
            arn.insert(0, _get_account_id())
        if len(arn) == 2:
            arn.insert(0, args.region)
        if len(arn) == 3:
            arn[0:0] = ['sns']
        if len(arn) == 4:
            arn[0:0] = ['aws']
        if len(arn) == 5:
            arn[0:0] = ['arn']
        if len(arn) != 6 or arn[0:3] != ['arn', 'aws', 'sns']:
            raise RuntimeError("%s doesn't look like a valid SNS ARN" % ':'.join(arn))
    
        return ':'.join(arn)
    
    
    # This is a mervelous little hack
    def _get_account_id():
        try:
            arn = boto.connect_iam().get_user().arn
        except boto.exception.BotoServerError as e:
            # The ARN is in the error message
            arn = e.error_message.split(' ')[-1]
    
        # The account ID is the 5th field.
        account_id = arn.split(':')[4]
    
        if match(r'^[0-9]{12}$', account_id) is None:
            raise RuntimeError("%s doesn't look like an account ID" % account_id)
    
        return account_id
    
    
    def _get_transitions(args):
        transitions = {'passing': set(),
                       'warning': set(),
                       'critical': set()}
    
        # Default case. Everything is passed.
        if args.filter is None and not args.escalation and not args.de_escalation:
            for state in transitions:
                transitions[state].update(transitions.keys())
                transitions[state].discard(state)
    
        if args.escalation:
            transitions['passing'].update(['warning', 'critical'])
            transitions['warning'].update(['critical'])
        if args.de_escalation:
            transitions['critical'].update(['passing', 'warning'])
            transitions['warning'].update(['passing'])
    
        if args.filter is not None:
            filters = loads(args.filter)
    
            if not isinstance(filters, dict):
                raise RuntimeError("filter must be a dictionary")
    
            for state in filters:
                if not isinstance(state, basestring):
                    raise RuntimeError("state must be a string")
                state = state.lower()
                if state not in transitions:
                    raise RuntimeError("'%s' is not a valid state" % state)
                if not isinstance(filters[state], list):
                    raise RuntimeError("value of '%s' must be an array" % state)
    
                for value in filters[state]:
                    if not isinstance(value, basestring):
                        raise RuntimeError("all values of '%s' must be strings" % state)
                    value = value.lower()
                    if value not in transitions:
                        raise RuntimeError("value '%s' of '%s' is not a valid state" % (value, state))
                    transitions[state].update([value])
    
        return transitions
    
    def _parse_args():
        epilog = '''\
  usage:
    The script will take an input from STDIN and parse it line-by-line. The best
    way to do this on a *nix-y system is:

    consul watch -type=check cat | consul2sns -t foo-bar

    Why use `cat` as the command instead of consul2sns? Because something about
    newline and EOF process directly sucks. Dunno.

  additional info:
    TOPIC - The topic is the ARN of the SNS topic. If it is an incomplete ARN, the
            script will attempt to build the ARN itself:

            [arn:[aws:[sns:[<REGION>:[<account ID>:]]]]]<TOPIC>

            <REGION> - Specified by --region
            <account ID> - The account ID of the Boto IAM user

    FILTER - A JSON dictionary of state changes to pass to SNS. The valid states
             are "passing", "warning", "critical". Example:

             {"warning": ["critical", "passing"], "critical": ["passing"]}

             This would only forward state transitions from warning to critical
             or passing, and from critical to passing.

             By default it passes all.
        '''
    
        parser = ArgumentParser(description='Publish Consul state change events to AWS SNS', epilog=epilog, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument('-t', '--topic',
                            required=True,
                            help='AWS SNS topic ARN to publish to')
        parser.add_argument('-r', '--region',
                            default='us-east-1',
                            help='AWS region to connect to')
        parser.add_argument('-f', '--filter',
                            default=None,
                            help='state transition filter')
        parser.add_argument('--escalation',
                            action='store_true',
                            help='forward escalating states')
        parser.add_argument('--de-escalation',
                            action='store_true',
                            help='forward de-escalating states')
        parser.add_argument('--access-key-id',
                            default=None,
                            help='AWS IAM access key ID')
        parser.add_argument('--secret-access-key',
                            default=None,
                            help='AWS IAM secret access key')
        parser.add_argument('-v', '--verbose',
                            action='store_true',
                            help='print verbose output')
        args = parser.parse_args()
    
        return parse_stdin(args)
    
    def run():
        args = _parse_args()
        access_args = {"aws_access_key_id": args.access_key_id,
                       "aws_secret_access_key": args.secret_access_key}
        sns = connect_to_region(args.region, **access_args)
        topic = _get_arn(args)
        transitions = _get_transitions(args)
    
        # Get topic attributes and trash them. A simple test to see if the topic
        # actually exists. Let the exception bubble up.
        sns.get_topic_attributes(topic)
    
        print >> stderr, "INFO: Republishing to SNS topic:", topic
        print >> stderr, "INFO: Valid state transitions are:", transitions
    
        # Infinite loop, sorry Mom
        then = None
        while True:
            try:
                # stdin.readline() blocks until the next newline
                line_in = stdin.readline()
                try:
                    now = ingest_state(loads(line_in))
                except ValueError as e:
                    print >> stderr, "WARN: %s" % dumps({"unparsable line": line_in})
                    continue
    
                # If this just started, get base-state data
                if then is None:
                    then = now
                    continue
    
                # Calculate the delta
                delta = status_delta(then, now)
                if args.verbose:
                    print dumps(delta, indent=4)
    
                # Publish each delta *indiviually*
                for check in delta:
                    if check['Status'] in transitions[check['PreviousStatus']]:
                        sns.publish(topic, dumps(check))
    
                then = now
            except KeyboardInterrupt:
                print >> stderr, "INFO: Caught keyboard interrupt, exiting..."
                return 0
