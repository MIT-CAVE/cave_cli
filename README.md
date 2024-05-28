# CAVE CLI
A unix based Command Line Interface (CLI) to streamline the creation and development process for `cave_app`s

## Prerequisits for the CLI installation

Click your OS below for instructions on how to install the prerequisits for the CLI installation.
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
<summary>MacOs</summary>

- Install `Command Line Tools`
    - Install `XCode` from the `App Store`
    - Once `XCode` is installed, install the XCode `Command Line Tools`
        - `menu` -> `preferences` -> `downloads` -> `command line tools`
- Install Docker
    - https://docs.docker.com/docker-for-mac/install/

</details>
<details>
<summary>Windows</summary>

- Install docker desktop **for wsl**
    - https://docs.docker.com/desktop/wsl/
- Install wsl2 with ubuntu 22.04
    - https://learn.microsoft.com/en-us/windows/wsl/install#upgrade-version-from-wsl-1-to-wsl-2
- Open your wsl ubuntu terminal and in that terminal:
    - Check docker:
        - `docker run hello-world`
        - `docker --version`
    - Install the cave cli:
        - `bash -c "$(curl https://raw.githubusercontent.com/MIT-CAVE/cave_cli/main/install.sh)"`
    - Optional: Configure git and ssh for wsl2 (since this is different from windows git)
        - Configure ssh credentials:
            - `ssh-keygen -f ~/.ssh/id_rsa -t rsa -b 4096 -C [youremail@gmail.com](mailto:youremail@gmail.com)`
            - `echo '# Add Git Profile' >> ~/.bashrc`
            - `echo 'eval $(ssh-agent -s) &>/dev/null' >> ~/.bashrc`
            - `echo 'ssh-add ~/.ssh/id_rsa &>/dev/null' >> ~/.bashrc`
            - `source ~/.bashrc`
        - Show your credentials:
            - `cat ~/.ssh/id_rsa.pub`
        - Copy your credential up to github in your profile under ssh keys
    - Notes
        - If the cave cli installation isn't working, try using Ubuntu 22.04
        - To open projects in your code editor, cd into the project and:
            - `code .`

</details>

## CLI Installation

```sh
# Install the CLI
bash -c "$(curl https://raw.githubusercontent.com/MIT-CAVE/cave_cli/main/install.sh)"
```
```sh
# Validate the installation succeeded
cave --version
```

## CLI Functions

- All current CLI functions can be listed with:
    ```
    cave --help
    ```

- To create and run a new app:
    1) `cave create my_app`
    2) `cd my_app`
    3) `cave run`
    4) Open a browser to `http://localhost:8000/`

## License Notice

Copyright 2023 Massachusetts Institute of Technology (MIT), Center for Transportation & Logistics (CTL)

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
