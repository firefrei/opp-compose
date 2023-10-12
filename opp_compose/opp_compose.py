#!/usr/bin/env python3
import os
import sys
import logging
import argparse
import yaml
import docker
import pprint

from argparse import Namespace
from collections.abc import Generator
from datetime import datetime


class ContainerNameGenerator(Generator):
    def __init__(self, last_idx: int, first_idx: int = 0, base_name: str = "") -> None:
        self.idx_first = first_idx
        self.idx_last = last_idx
        self.base_name = base_name
        self.reset()

    def send(self, value) -> tuple:
        if self.idx <= self.idx_last:
            number = self.idx
            name = "%s%d" % (self.base_name, number)
            self.idx = self.idx + 1
            return number, name
        raise StopIteration

    def reset(self) -> None:
        self.idx = self.idx_first

    def __next__(self):
        return self.send(None)

    def throw(self, typ, val=None, tb=None):
        super().throw(typ, val, tb)


class ContainerManager:
    def __init__(self, config) -> None:
        self.config = config
        self.log = logging.getLogger(__name__)
        self.docker_client = docker.from_env()

    def list(self) -> list:
        return self.docker_client.containers.list(
            all=True,
            filters={
                'label': [
                    'sim-config=%s' % (self.config.configuration)
                ]
            })

    def run(self) -> list:
        created = []

        if not os.path.exists(self.config.results_path):
            LOG.error("Path for results files does not exist!")
            exit(2)

        cont_name_gen = ContainerNameGenerator(
            first_idx=self.config.first,
            last_idx=self.config.last,
            base_name=self.config.name)

        for cont_number, cont_name in cont_name_gen:
            result_path = os.path.join(self.config.results_path, cont_name)
            cont_volumes = ['%s:%s' %
                            (result_path, self.config.container_result_path)]
            cont_env = {
                'OPP_RUN_INIFILE': self.config.ini,
                'OPP_RUN_CONFIG': self.config.configuration,
                'OPP_RUN_NUMBER': cont_number,
                'OPP_RUN_RESULT_DIR': self.config.container_result_path
            }

            cont = self.docker_client.containers.run(
                image=self.config.image,
                name=cont_name,
                detach=True,
                environment=cont_env,
                volumes=cont_volumes,
                user=self.config.user,
                labels={
                    'sim-config': self.config.configuration,
                    'app': 'opp_compose'
                })
            created.append(cont)
        return created

    def stop(self, timeout: int = 10) -> int:
        containers = self.list()
        cnt = len(containers)
        for container in containers:
            container.stop(timeout=timeout)
        return cnt

    def remove(self, v: bool = False, force: bool = False) -> int:
        containers = self.list()
        cnt = len(containers)
        for container in containers:
            container.remove(v=v, force=force)
        return cnt

    def image_pull(self) -> docker.models.images.Image:
        return self.docker_client.images.pull(
            self.config.image
           )


class ContainerFormatter:
    def status(self, containers, *, add_header: bool = True) -> str:
        result = ""
        if not containers:
            result = "[]"
        else:
            if add_header:
                output = "CONTAINER ID\tNAME\tSTATUS (RC)\tUPTIME\t\n"
                result += output

            for container in containers:
                exit_code = container.__dict__['attrs']['State']['ExitCode']
                error = container.__dict__['attrs']['State']['Error']
                started_at_str = container.__dict__[
                    'attrs']['State']['StartedAt']
                finished_at_str = container.__dict__[
                    'attrs']['State']['FinishedAt']
                if sys.version_info < (3, 11):
                    started_at_str = started_at_str[:26]
                    finished_at_str = finished_at_str[:26]

                now = datetime.utcnow()
                started_at = datetime.fromisoformat(
                    started_at_str) if container.status != "created" else now
                finished_at = datetime.fromisoformat(
                    finished_at_str) if container.status == "exited" else now
                uptime = finished_at - started_at

                output = "{0.short_id}\t{0.name}\t{0.status} ({1})\t{2}\t{3}\n".format(
                    container, exit_code, uptime, error)
                result += output
        return result


def main():
    if (CONFIG.last - CONFIG.first) > os.cpu_count():
        LOG.warning("Not enough CPU cores available to run all simulations!")

    pp = pprint.PrettyPrinter(indent=4)
    containers = ContainerManager(CONFIG)
    formatter = ContainerFormatter()
    docker_client = docker.from_env()

    if CONFIG.command in ['ps']:
        items = containers.list()
        print("Simulation Container Overview:\n%s" % (formatter.status(items)))

    elif CONFIG.command in ['stop']:
        cnt = containers.stop()
        LOG.info("Stopped %d container(s)." % (cnt))

    elif CONFIG.command in ['rm', 'remove']:
        cnt = containers.remove()
        LOG.info("Removed %d container(s)." % (cnt))

    elif CONFIG.command in ['down']:
        cnt_stopped = containers.stop()
        LOG.info("Stopped %d container(s)." % (cnt_stopped))
        cnt_removed = containers.remove()
        LOG.info("Removed %d container(s)." % (cnt_removed))

    elif CONFIG.command in ['up']:
        if not containers.list():
            created = containers.run()
            print("Created %d simulation container(s):\n%s" %
                  (len(created), formatter.status(created)))
        else:
            items = containers.list()
            LOG.warning("Simulation container(s) are already running. Nothing was changed.\nExisting container(s):\n%s" % (
                formatter.status(items)))
    
    elif CONFIG.command in ['pull', 'image-pull']:
        image = containers.image_pull()
        LOG.info("Pulled image %s." % (image))

    elif CONFIG.command in ['config-dump']:
        print(yaml.dump(vars(CONFIG)))

    elif CONFIG.command in ['testup']:
        cont_name_gen = ContainerNameGenerator(
            first_idx=CONFIG.first, last_idx=CONFIG.last, base_name=CONFIG.name)
        for cont_number, cont_name in cont_name_gen:
            result = docker_client.containers.run('alpine', 'echo hello world',
                                                  name=cont_name,
                                                  detach=True,
                                                  labels={
                                                      'sim-config': CONFIG.configuration,
                                                      'app': 'opp_compose'
                                                  })
            pp.pprint(result)

    else:
        LOG.error("Unknown command: %s" % (CONFIG.command))
        exit(1)


def parse_configuration() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='OMNeT++ Compose :: Launch OMNeT++ Simulations as Containers')
    parser.add_argument('command',
                        choices=['ps', 'up',
                                 'down', 'stop', 'rm',
                                 'pull', 'image-pull',
                                 'config-dump', 'help',
                                 'testup'],
                        help='Command to execute. Commands are similar to `docker compose` commands.')
    parser.add_argument('-f', '--file', type=str,
                        help="OMNeT++ Compose configuration file (.yaml)",
                        default='simulation.yaml')
    parser.add_argument('-c', '--configuration',
                        help='Configuration name in OMNeT++ ini-file')
    parser.add_argument('--first', type=int, default=0,
                        help='Run number of the first run to launch')
    parser.add_argument('--last', type=int, default=None,
                        help='Run number of the last run to launch')
    parser.add_argument('--image',
                        default='mobmecmeshsim',
                        help='Name of the docker container image to use')
    parser.add_argument('--name',
                        default='sim-r',
                        help='Base name of the simulation container to use')
    parser.add_argument('--user',
                        default="",
                        help='System user-id to use inside the docker container')
    parser.add_argument('--ini',
                        default="omnetpp.ini",
                        help='Name of OMNeT++ configuration ini-file')
    parser.add_argument('--results-path',
                        default="/tmp/simulation",
                        help='Base path on host file system where to store simulation result files. A folder for each run is created')
    parser.add_argument('--container-result-path',
                        default="/usr/results",
                        help='Absolute path on container file system where to store simulation result files (right side of container bind mount)')
    # parser.add_argument('--registry-username',
    #                     help='Login username at container registry')
    # parser.add_argument('--registry-password',
    #                     help='Login password or access token at container registry')
    # parser.add_argument('--registry-username',
    #                     help='Login username at container registry')
    args = parser.parse_args()

    if args.command in ['help']:
        parser.print_help()
        parser.exit(0)

    # Additionally import configuration file
    yaml_file = os.path.abspath(args.file)
    if yaml_file and os.path.exists(yaml_file):
        with open(yaml_file, 'r') as file:
            LOG.debug("Using OMNeT++ Compose configuration file: %s" %
                      (yaml_file))
            config_sec = yaml.safe_load(file)
            config_prim = vars(args)

            # Update primary config with values from secondary config
            for key, value in config_sec.items():
                if key not in config_prim:
                    parser.error(
                        "`%s` is not a valid configuration option!" % (key))

                # Use YAML config when:
                # - Config value on cli evaluates to False
                # - Config value on cli equals the default value (-> not overwritten by user on cli)
                if config_prim.get(key) is None or config_prim.get(key) == parser.get_default(key):
                    config_prim[key] = value

            args = Namespace(**config_prim)

    # Validate configuration dependencies and values
    if not args.configuration:
        parser.error(
            "OMNeT++ configuration name not defined. [Argument: configuration]")

    if args.last is None:
        parser.error(
            "Run number of last run to launch is not defined. [Argument: last]")

    return args


if __name__ == "__main__":
    # Init logging
    logging.basicConfig(level=os.getenv('LOGLEVEL', 'INFO'))
    LOG = logging.getLogger("opp_compose")

    # Init configuration
    CONFIG = parse_configuration()

    # Run actions
    main()
