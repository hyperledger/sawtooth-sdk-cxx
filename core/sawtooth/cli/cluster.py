# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------

import logging
import os
import yaml

from sawtooth.exceptions import ManagementError

from sawtooth.manage.daemon import DaemonNodeController
from sawtooth.manage.docker import DockerNodeController
from sawtooth.manage.simple import SimpleNodeCommandGenerator
from sawtooth.manage.vnm import ValidatorNetworkManager

from sawtooth.cli.exceptions import CliException


LOGGER = logging.getLogger(__name__)


def add_cluster_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('cluster', parents=[parent_parser])

    cluster_subparsers = parser.add_subparsers(
        title='subcommands',
        dest='cluster_command')

    add_cluster_start_parser(cluster_subparsers, parent_parser)
    add_cluster_status_parser(cluster_subparsers, parent_parser)
    add_cluster_stop_parser(cluster_subparsers, parent_parser)


def add_cluster_status_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('status', parents=[parent_parser])

    parser.add_argument(
        'node_names',
        metavar='NODE_NAME',
        help='report status of specific node(s)',
        nargs='*')

    parser.add_argument(
        '-m', '--manage',
        help='style of validator management',
        choices=['daemon', 'docker'],
        default='daemon')


def add_cluster_start_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('start', parents=[parent_parser])

    parser.add_argument(
        '--count',
        help='number of nodes to start',
        type=int,
        default=10)

    parser.add_argument(
        '-m', '--manage',
        help='style of validator management',
        choices=['daemon', 'docker'],
        default='daemon')


def add_cluster_stop_parser(subparsers, parent_parser):
    parser = subparsers.add_parser('stop', parents=[parent_parser])

    parser.add_argument(
        'node_names',
        metavar='NODE_NAME',
        help='stop specific node(s)',
        nargs='*')


def do_cluster(args):
    if args.cluster_command == 'start':
        do_cluster_start(args)
    elif args.cluster_command == 'status':
        do_cluster_status(args)
    elif args.cluster_command == 'stop':
        do_cluster_stop(args)
    else:
        raise CliException("invalid cluster command: {}".format(
            args.cluster_command))


def do_cluster_start(args):
    # pylint: disable=redefined-variable-type
    file_name = \
        os.path.join(os.path.expanduser("~"), '.sawtooth', 'cluster',
                     "state.yaml")

    # Check for existing state.yaml and get state. If not create state dict.
    try:
        with open(file_name, 'r') as state_file:
            state = yaml.load(state_file)
    except IOError:
        state = dict()
        state["State"] = "Stopped"

    # Check State for Running validators, if stopped clear out nodes.
    if state["State"] == "Stopped":
        state["Nodes"] = {}

    if "Manage" not in state:
        state['Manage'] = args.manage if args.manage is not None else 'docker'
    elif args.manage is not None and state['Manage'] != args.manage\
            and state["State"] == "Running":
        raise CliException('Cannot use two different Manage types.'
                           ' Already running {}'.format(state["Manage"]))

    state["State"] = "Running"

    if state["Manage"] == 'docker':
        node_controller = DockerNodeController()

    elif state["Manage"] == 'daemon':
        node_controller = DaemonNodeController()
    else:
        raise CliException('invalid management type:'
                           ' {}'.format(state["Manage"]))

    node_command_generator = SimpleNodeCommandGenerator()

    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    try:
        existing_nodes = vnm.get_node_names()
    except ManagementError as e:
        raise CliException(str(e))

    for i in xrange(0, args.count):
        node_name = "validator-{:0>3}".format(i)

        if node_name in existing_nodes and vnm.is_running(node_name):
            print "Already running: {}".format(node_name)
            continue

        # genesis is true for the first node
        genesis = (i == 0)

        print "Starting: {}".format(node_name)
        node_command_generator.start(
            node_name,
            http_port=8800,
            gossip_port=5500,
            genesis=genesis)

        state["Nodes"][node_name] = {"Status": "Running", "Index": i}

    # Write file to default directory with current state Nodes
    with open(file_name, 'w') as state_file:
        yaml.dump(state, state_file, default_flow_style=False)

    try:
        vnm.update()
    except ManagementError as e:
        raise CliException(str(e))


def do_cluster_stop(args):
    # pylint: disable=redefined-variable-type
    file_name = \
        os.path.join(os.path.expanduser("~"), '.sawtooth', 'cluster',
                     "state.yaml")
    # Get current state of Nodes
    try:
        with open(file_name, 'r') as state_file:
            state = yaml.load(state_file)
    except IOError as e:
        raise CliException(str(e))

    if state['Manage'] is None or state['Manage'] == 'docker':
        node_controller = DockerNodeController()
    elif state['Manage'] == 'daemon':
        node_controller = DaemonNodeController()
    else:
        raise CliException('invalid management'
                           ' type: {}'.format(state['Manage']))

    node_command_generator = SimpleNodeCommandGenerator()

    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    if len(args.node_names) > 0:
        node_names = args.node_names
    else:
        node_names = vnm.get_node_names()

    for node_name in node_names:
        print "Stopping: {}".format(node_name)
        node_command_generator.stop(node_name)

    vnm.update()


def do_cluster_status(args):
    # pylint: disable=redefined-variable-type
    if args.manage is None or args.manage == 'docker':
        node_controller = DockerNodeController()
    elif args.manage == 'daemon':
        node_controller = DaemonNodeController()
    else:
        raise CliException('invalid management type: {}'.format(args.manage))

    node_command_generator = SimpleNodeCommandGenerator()

    vnm = ValidatorNetworkManager(
        node_controller=node_controller,
        node_command_generator=node_command_generator)

    if len(args.node_names) > 0:
        node_names = args.node_names
    else:
        node_names = vnm.get_node_names()

    for node_name in node_names:
        print "{} {}".format(node_name, vnm.status(node_name))
