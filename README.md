# cave_cli
A unix based Command Line Interface (CLI) to streamline the creation and development process for `cave_app`s

## Development Prerequisites

- Make sure you are using a Unix based kernel (Mac or Linux).
    - If you are using Windows, you can use Ubuntu20.04 (via WSL2).
        - While using WSL2, make sure to follow all instructions in your WSL2 terminal
- **Note**: Only `python` is supported (and not python derivatives like anaconda)

## Ubuntu Setup:

```sh
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh ./get-docker.sh
# Add the current user to the docker group
dockerd-rootless-setuptool.sh install
# Make sure it works outside of sudo
docker run hello-world
```

## Mac Setup:

- Install `Command Line Tools`
    - Install `XCode` from the `App Store`
    - Once `XCode` is installed, install the XCode `Command Line Tools`
        - `menu` -> `preferences` -> `downloads` -> `command line tools`
- Install Docker
    - https://docs.docker.com/docker-for-mac/install/

## CLI Installation

```
bash -c "$(curl https://raw.githubusercontent.com/MIT-CAVE/cave_cli/main/install.sh)"
```
- **Note**: During installation you will be asked to choose your default python installation path.
    - You can use the default or this can be found with: `which python3.11` in a new terminal.
- Validate Installation:
    ```
    cave --version
    ```

## CLI Functions

- All current CLI functions can be listed with:
    ```
    cave --help
    ```

## License Notice

Copyright 2023 Massachusetts Institute of Technology (MIT), Center for Transportation & Logistics (CTL)

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
