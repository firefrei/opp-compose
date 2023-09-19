# OMNeT++ Compose

A python3-based tool for launching many OMNeT++ containers to run many simulations simultaneously.
`opp_compose` usage is very similar to the `docker compose` command-line interface.

### Example
```bash
#$ ./opp_compose.py -f simulation.yaml ps
Simulation Container Overview:
CONTAINER ID	NAME	STATUS (RC)	UPTIME
0c86c004b134	sim-r9	exited (133)	2 days, 3:57:00.976178
7b3f95bd97ce	sim-r8	exited (133)	2 days, 5:13:22.556070
0cf2932b4dd4	sim-r7	exited (133)	1 day, 5:28:31.100610
e192adef2c75	sim-r6	exited (133)	1 day, 5:08:30.590936
b7b4c6b29df2	sim-r5	exited (133)	1 day, 0:54:40.184521
ecf3438c8c21	sim-r4	exited (133)	2 days, 2:05:18.867849
3634eec5140e	sim-r3	exited (133)	2 days, 9:31:43.570320
3692c9065fc6	sim-r2	exited (133)	2 days, 10:26:53.468835
6cab8a529739	sim-r1	exited (133)	1 day, 6:23:48.697642
849268aa996f	sim-r0	exited (133)	1 day, 9:09:50.554303
```

### Command-Line Arguments
`opp_compose` can be configured using command-line arguments or by passing a `YAML` configuration file.  
Both variants can be combined. Configuration passed by command-line overrides the loaded configuration from file.
  
Available command-line arguments:
```bash
#$ ./opp_compose.py -h
usage: opp_compose.py [-h] [-f FILE] [-c CONFIGURATION] [--first FIRST]
                      [--last LAST] [--image IMAGE] [--name NAME]
                      [--user USER] [--ini INI] [--results-path RESULTS_PATH]
                      [--container-result-path CONTAINER_RESULT_PATH]
                      {ps,up,down,stop,rm,config-dump,help,testup}

OMNeT++ Compose :: Launch OMNeT++ Simulations as Containers

positional arguments:
  {ps,up,down,stop,rm,config-dump,help,testup}
                        Command to execute. Commands are similar to `docker
                        compose` commands.

optional arguments:
  -h, --help            show this help message and exit
  -f FILE, --file FILE  OMNeT++ Compose configuration file (.yaml)
  -c CONFIGURATION, --configuration CONFIGURATION
                        Configuration name in OMNeT++ ini-file
  --first FIRST         Run number of the first run to launch
  --last LAST           Run number of the last run to launch
  --image IMAGE         Name of the docker container image to use
  --name NAME           Base name of the simulation container to use
  --user USER           System user-id to use inside the docker container
  --ini INI             Name of OMNeT++ configuration ini-file
  --results-path RESULTS_PATH
                        Base path on host file system where to store
                        simulation result files. A folder for each run is
                        created
  --container-result-path CONTAINER_RESULT_PATH
                        Absolute path on container file system where to store
                        simulation result files (right side of container bind
                        mount)
```

### Configuration File
The `YAML` configuration file can contain the same configuration. However, `-` needs to be converted to `_`.  
Example configuration file:
```yaml
#$ cat simulation.yaml
configuration: fun-factor-variation
ini: omnetpp.ini
image: sim-docker-image:latest

results_path: /data/sim_results
first: 0
last: 9
```

## Installation
1. Clone this repository
2. Install python3 dependencies: `pip3 install -r requirements.txt`
3. Call `opp_compose`: `./opp_compose/opp_compose.py -h`
