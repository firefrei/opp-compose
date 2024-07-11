#!/usr/bin/env python3
import os
import sys
import logging
import argparse
import yaml
import docker
import pprint

from typing import Tuple, List
from argparse import Namespace
from collections.abc import Generator
from datetime import datetime, timezone
from tabulate import tabulate


class SimulationConfigModel:
    def __init__(self) -> None:
        # Environment
        self.name:str = None
        self.ini:str = None
        self.configuration:str = None
        
        ## Container Image
        self.image:str = None
        self.user:str = None
        self.container_result_path:str = None
        # self.registry_username:str = None
        # self.registry_password:str = None

        # Results
        self.results_path:str = None

        # Runs
        self.first:str = None
        self.last:str = None

    def __str__(self) -> str:
        return self.name if self.name else super().__str__()

    def from_dict(self, src:dict):
        for key, value in src.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self

    def valid(self) -> bool:
        for value in self.__dict__.values():
            if value is None:
                return False
        return True


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
    def __init__(self, config:SimulationConfigModel, logger:logging.Logger) -> None:
        self.config = config
        self.log = logger.getChild(__name__)
        self.docker_client = docker.from_env()

    def list(self, all:bool = False) -> list:
        labels = [
            'app=opp_compose'
        ]

        if not all:
            labels.append('sim-name=%s' % (self.config.name))

        return self.docker_client.containers.list(
            all=True,
            filters={
                'label': labels
            })

    def run(self) -> list:
        created = []
        running_names = set([ c.name for c in self.list() ])

        if not os.path.exists(self.config.results_path):
            self.log.error("Path for results files does not exist!")
            exit(2)

        cont_name_gen = ContainerNameGenerator(
            first_idx=self.config.first,
            last_idx=self.config.last,
            base_name=self.config.name)

        for cont_number, cont_name in cont_name_gen:
            if cont_name in running_names:
                continue

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
                    'sim-name': self.config.name,
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
    def status(self, containers, *, add_header: bool = True, extensive:bool=False) -> str:
        header = [ 
            "CONTAINER ID", "NAME", "STATUS (RC)", "UPTIME"
            ] if add_header else None
        if extensive:
            header.append("CONFIGURATION")
        header.append("")

        table = []
        for container in containers:
            # Container Runtime Info
            exit_code = container.__dict__['attrs']['State']['ExitCode']
            error = container.__dict__['attrs']['State']['Error']
            started_at_str = container.__dict__[
                'attrs']['State']['StartedAt']
            finished_at_str = container.__dict__[
                'attrs']['State']['FinishedAt']
            if sys.version_info < (3, 11):
                started_at_str = started_at_str[:26]
                finished_at_str = finished_at_str[:26]

            now = datetime.now(timezone.utc)
            started_at = datetime.fromisoformat(
                started_at_str) if container.status != "created" else now
            finished_at = datetime.fromisoformat(
                finished_at_str) if container.status == "exited" else now
            
            ## Ensure timezone is UTC
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=timezone.utc)

            uptime = finished_at - started_at

            line = [
                container.short_id, container.name,
                "%s (%s)" % (container.status, exit_code),
                uptime
            ]

            # Container Config Info
            if extensive:
                labels = container.__dict__['attrs']['Config']['Labels']
                line.append(labels['sim-config'])

            line.append(error)

            table.append(line)
        return tabulate(table, headers=header, showindex=False)


def main(command:str, config:SimulationConfigModel):
    logger = LOG.getChild(config.name)

    if (config.last - config.first) > os.cpu_count():
        logger.warning("Not enough CPU cores available to run all simulations!")

    pp = pprint.PrettyPrinter(indent=4)
    containers = ContainerManager(config, logger)
    formatter = ContainerFormatter()
    docker_client = docker.from_env()

    if command in ['ps']:
        items = containers.list()
        print("Simulation Container Overview for Simulation '%s':\n%s" % (config, formatter.status(items)))
    
    elif command in ['ps-all']:
        items = containers.list(all=True)
        print("Simulation Container Overview - All Simulations Launched by OPP-Compose:\n%s" % (formatter.status(items, extensive=True)))
        exit(0)

    elif command in ['stop']:
        cnt = containers.stop()
        logger.info("Stopped %d container(s)." % (cnt))

    elif command in ['rm', 'remove']:
        cnt = containers.remove()
        logger.info("Removed %d container(s)." % (cnt))

    elif command in ['down']:
        cnt_stopped = containers.stop()
        logger.info("Stopped %d container(s)." % (cnt_stopped))
        cnt_removed = containers.remove()
        logger.info("Removed %d container(s)." % (cnt_removed))

    elif command in ['up']:
        created = containers.run()
        if created:
            print("Created %d simulation container(s):\n%s" %
                    (len(created), formatter.status(created)))
        else:
            items = containers.list()
            logger.warning("Simulation container(s) are already running. Nothing was changed.\nExisting container(s):\n%s" % (
                formatter.status(items)))
    
    elif command in ['pull', 'image-pull']:
        image = containers.image_pull()
        logger.info("Pulled image %s." % (image))

    elif command in ['config-dump']:
        print(yaml.dump(vars(config)))

    elif command in ['testup']:
        cont_name_gen = ContainerNameGenerator(
            first_idx=config.first, last_idx=config.last, base_name=config.name)
        for cont_number, cont_name in cont_name_gen:
            result = docker_client.containers.run('alpine', 'echo hello world',
                                                  name=cont_name,
                                                  detach=True,
                                                  labels={
                                                      'sim-name': config.name,
                                                      'app': 'opp_compose'
                                                  })
            pp.pprint(result)

    else:
        logger.error("Unknown command: %s" % (command))
        exit(1)


def parse_configuration() -> Tuple[argparse.Namespace, List[SimulationConfigModel]]:
    parser = argparse.ArgumentParser(
        description='OMNeT++ Compose :: Launch OMNeT++ Simulations as Containers')
    parser.add_argument('command',
                        choices=['ps', 'ps-all', 'up',
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
                        default='simulation',
                        help='Name of the docker container image to use')
    parser.add_argument('--name',
                        default=r'sim%d-r',
                        help='Base name of the simulation container to use. Run number is appended to the string. Optionally, add integer template parameter to to include simulation index.')
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
    
    extra_options = [ "simulations" ]

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
                if key not in config_prim and key not in extra_options:
                    parser.error(
                        "`%s` is not a valid configuration option!" % (key))

                # Use YAML config when:
                # - Config value on cli evaluates to False
                # - Config value on cli equals the default value (-> not overwritten by user on cli)
                if config_prim.get(key) is None or config_prim.get(key) == parser.get_default(key):
                    config_prim[key] = value

            args = Namespace(**config_prim)

    # Create simulation model objects
    sim_objects = []
    sim_main = SimulationConfigModel().from_dict(vars(args))
    if sim_main.valid():
        sim_objects.append(sim_main)
    if "simulations" in args:
        for simulation in args.simulations:
            sim = SimulationConfigModel().from_dict(vars(args)).from_dict(simulation)
            if sim.valid():
                sim_objects.append(sim)
            else:
                parser.error("Simulation configuration %s is not valid, maybe some parameters are not defined." % (sim))

    # Validate configuration dependencies and values
    if not sim_objects and not args.configuration:
        parser.error(
            "OMNeT++ configuration name not defined. [Argument: configuration]")

    if not sim_objects and args.last is None:
        parser.error(
            "Run number of last run to launch is not defined. [Argument: last]")

    return args, sim_objects


if __name__ == "__main__":
    # Init logging
    logging.basicConfig(level=os.getenv('LOGLEVEL', 'INFO'))
    LOG = logging.getLogger("opp_compose")

    # Init configuration
    config, simulations = parse_configuration()

    # Run actions
    index = 0
    for simulation in simulations:
        if r"%d" in simulation.name:
            simulation.name %= index
        main(config.command, simulation)
        index += 1
