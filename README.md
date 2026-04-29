# CAVE CLI

A cross-platform CLI for creating and managing Docker-based CAVE web applications.

Developed by [MIT-CAVE](https://cave.mit.edu/) (Center for Transportation & Logistics). Licensed under Apache 2.0.

## Prerequisites

- [Python](https://www.python.org/downloads/) 3.11+
- [Docker](https://docs.docker.com/get-docker/) 23.0.6+
- [Git](https://git-scm.com/)

<details>
<summary>Ubuntu</summary>

```sh
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh ./get-docker.sh
# Add the current user to the docker group
dockerd-rootless-setuptool.sh install
# Make sure it works outside of sudo
docker run hello-world
```

</details>
<details>
<summary>macOS</summary>

- Install Docker Desktop: https://docs.docker.com/docker-for-mac/install/

</details>
<details>
<summary>Windows</summary>

- Install Docker Desktop: https://docs.docker.com/docker-for-windows/install/

</details>

## Installation

Install with [pipx](https://pipx.pypa.io/) (recommended — keeps the CLI isolated from your system Python):

```sh
pipx install cave_cli
```

If you don't have pipx, install it first:

<details>
<summary>macOS</summary>

```sh
# With Homebrew (recommended)
brew install pipx
pipx ensurepath

# Or with pip
pip3 install --user pipx
pipx ensurepath
```

</details>
<details>
<summary>Other Linux / Windows</summary>

```sh
python3 -m pip install --user pipx
pipx ensurepath
```
</details>

For more options see the [pipx installation guide](https://pipx.pypa.io/stable/installation/).

Verify the installation and check your environment health:

```sh
cave doctor
```

## Quick Start

```sh
cave create my_app
cd my_app
cave run
# Open http://localhost:8000/ in your browser
```

## CLI Commands

```sh
cave --help
```

### Core Commands

| Command | Description |
|---|---|
| `cave create <name>` | Create a new CAVE app from the template repository |
| `cave run` | Build Docker image and run the app with a live TUI dashboard |
| `cave doctor` | Check the health of your Docker, Git, and Pipx environment |

### Peripheral Commands

| Command | Description |
|---|---|
| `cave reset` | Remove containers/volumes and rebuild from scratch |
| `cave upgrade` | Upgrade app files from the upstream template |
| `cave sync --url <url>` | Merge files from another repository into the app |
| `cave test` | Run tests in `cave_api/tests/` |
| `cave prettify` | Format code with autoflake and black |
| `cave purge <path>` | Remove an app and all its Docker resources |

### Utility Commands

| Command | Description |
|---|---|
| `cave list` | List running CAVE apps |
| `cave kill` | Stop Docker containers for an app |
| `cave list-versions` | List available CAVE app versions |
| `cave theme <name>` | Set the CLI color theme (dark, light, solarized, monokai) |
| `cave update` | Update the CAVE CLI itself |
| `cave uninstall` | Remove the CAVE CLI |
| `cave version` | Print version information |

### Global Flags

| Flag | Description |
|---|---|
| `-v`, `--verbose` | Enable verbose (DEBUG) logging output |
| `--loglevel LEVEL` | Set log level: DEBUG, INFO, WARN, ERROR, SILENT |
| `-y`, `--yes` | Automatically answer confirmation prompts with yes |

### `cave run` Options

| Flag | Description |
|---|---|
| `--all` | Show raw container output instead of the TUI dashboard |
| `-it`, `--interactive` | Run in interactive mode (drops into a bash shell) |
| `ip:port` | Optional argument for LAN hosting (e.g. `192.168.1.1:8000`) |

## Updating

```sh
cave update
```

Or directly via pipx:

```sh
pipx upgrade cave_cli
```

## License Notice

Copyright 2023 Massachusetts Institute of Technology (MIT), Center for Transportation & Logistics (CTL)

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
