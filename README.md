# cave_cli
A unix based cli to simplify and streamline the creation and development process for `cave_app`s

## Development Prerequisites

- Make sure you are using a Unix based kernel (Mac or Linux).
    - If you are using Windows, you can use Ubuntu20.04 (via WSL2).
        - While using WSL2, make sure to follow all instructions in your WSL2 terminal
- Install [Git](https://git-scm.com)
    - It is likely `git` is already installed. You can check with:
        ```
        git --version
        ```
- Install `python3.9+`, `python3 pip`, `python development tools`, and `virtualenv`
    - **Note**: Only `python` is supported (and not python derivatives like anaconda)
    - On Ubuntu:
        ```sh
        # Update your package list and current packages
        sudo apt-get update && sudo apt-get upgrade -y
        # Install software to add external PPAs
        sudo apt install software-properties-common -y
        # Add the deadsnakes python PPA
        sudo add-apt-repository ppa:deadsnakes/ppa
        # Install python3.10 from the deadsnakes PPA
        sudo apt-get install python3.10 -y
        # Install pip
        curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
        # Install virtualenv
        pip install virtualenv
        ```
    - On Mac (via Brew):
        - Install `python development tools`
            - Install `XCode` from the `App Store`
            - Once `XCode` is installed, install the XCode `Command Line Tools`
                - `menu` -> `preferences` -> `downloads` -> `command line tools`
      - Install `python3.9+`
          ```sh
          brew install python@3.10
          ```
      - Install `pip` and `virtualenv`:
          ```sh
          # Install pip
          curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
          # Install virtualenv
          pip install virtualenv
          ```
- Install `Postgres 12`:
    - On Ubuntu:
        ```sh
        sudo apt-get install postgresql postgresql-contrib
        ```
    - On Mac (via Brew):
        ```sh
        brew install postgresql
        brew services start posgresql
        ```

## CLI Installation

```
bash -c "$(curl https://raw.githubusercontent.com/MIT-CAVE/cave_cli/main/install.sh)"
```
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

Copyright 2022 Massachusetts Institute of Technology (MIT), Center for Transportation & Logistics (CTL)

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
