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

Install with [uv](https://docs.astral.sh/uv/) (required to run cave update and cave uninstall):

```sh
uv tool install cave_cli
```

If you don't have uv, install it first:

<details>
<summary>macOS</summary>

```sh
# With Homebrew (recommended)
brew install uv

# Or with the official installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

</details>
<details>
<summary>Linux</summary>

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```
</details>
<details>
<summary>Windows</summary>

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
</details>

For more options see the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

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
| `cave doctor` | Check the health of your Docker, Git, and uv environment |

### Peripheral Commands

| Command | Description |
|---|---|
| `cave reset` | Remove containers/volumes and rebuild from scratch |
| `cave upgrade` | Upgrade app files from the upstream template |
| `cave sync --url <url>` | Merge files from another repository into the app |
| `cave test` | Run tests in `cave_api/tests/` |
| `cave prettify` | Format code with autoflake and black |
| `cave task` | Inspect, kill, and manage running tasks and task runner |
| `cave purge <path>` | Remove an app and all its Docker resources |

### Utility Commands

| Command | Description |
|---|---|
| `cave list` | List running CAVE apps |
| `cave kill` | Stop Docker containers for an app |
| `cave list-versions` | List available CAVE app versions |
| `cave theme <name>` | Set the CLI color theme (dark, light, solarized, monokai) |
| `cave completion` | Generate or install shell completion script for bash/zsh |
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

### `cave test` & `cave prettify` Options

Both commands execute against a background persistent task runner queue, allowing tests and code formatting to run without stopping or interrupting a live application server.

| Option | Description |
|---|---|
| `-d`, `--detached` | Run task in detached background mode |
| `--docker-args ARGS` | Additional arguments to pass to Docker |

### `cave task` Options

Schedule, inspect, attach to, and cancel serialized background tasks and manage the task runner stack.

| Command / Option | Description |
|---|---|
| `cave task list` (or `-l`, `--list`) | List current active tasks (queued and running) |
| `cave task list-all` (or `-la`, `--list-all`) | List all tasks including completed, failed, and cancelled |
| `cave task start <file> [args...]` | Run arbitrary file or script (e.g. `utils/prettify.py`) sequentially in task container |
| `cave task <cmd...>` | Run arbitrary container command (e.g. `python manage.py makemigrations`) |
| `cave task attach [id]` (or `-a`, `--attach`) | Attach to a task to follow live logs (`Esc` to detach, `Ctrl+C` to cancel) |
| `cave task kill <id>` (or `-k <id>`, `--kill <id>`) | Cancel or terminate a specific task by its incremental ID |
| `cave task kill-all` (or `--kill-all`) | Cancel all queued and running tasks |
| `cave task reset` (or `--reset`) | Rebuild the task runner image and reinitialize its database |
| `cave task stop` (or `--stop`) | Stop task runner containers and purge finished tasks |

While attached or waiting in the task queue, pressing **Esc** detaches back to the terminal (leaving the task running in the background), and **Ctrl+C** cancels the task. When the task server stops or times out from inactivity, completed tasks are automatically cleaned up.

## Updating

```sh
cave update
```

Or directly via uv:

```sh
uv tool upgrade cave_cli
```

## License Notice

Copyright 2023 Massachusetts Institute of Technology (MIT), Center for Transportation & Logistics (CTL)

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
