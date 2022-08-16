# cave_cli
A unix based cli to simplify and streamline the creation and development process for `cave_app`s

## License Notice

Copyright 2022 Massachusetts Institute of Techology, Center for Transportation & Logistics

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.


## Setup
1. Install [Python](https://www.python.org/downloads/):
  - Note: Make sure to install Python 3.9.0 or later
  - `cave_cli` is not compatible with Anaconda. Make sure you are not using Anaconda when installing or using `cave_cli`

2. Install [Git](https://git-scm.com)
  - It is likely `git` is already installed. You can check with:
    ```
    git --version
    ```

3. Install [postgres](https://www.postgresql.org/download/)

4. Install the `cave_cli`
  - Run the following commands to install the `cave_cli`,
    ```
    bash -c "$(curl https://raw.githubusercontent.com/MIT-CAVE/cave_cli/main/install.sh)"
    ```
    - Follow the prompts to finish the installation process
