Create a new virtual machine using the tools with the following requirements:

1. VM Creation

- VM Name: ubuntuTest
- Operating System: Ubuntu (64-bit)
- CPUs: 2
- Memory: 4096 MB

2. Networking

- Configure adapter 1 to bridge

3. Storage & ISO

- Create new hard drive, 50 GB

4. Unattended Installation

- Perform an unattended Linux installation with:
- Username: alice
- Password: boblikestoclickonspamemails
- Hostname: ubuntutest.local
- iso: C:\ISOs\ubuntu-25.10-desktop-amd64.iso
- Enable Install Guest Additions
- Enable Install in Background

5. Workflow Expectations

Execute the steps in correct order:
- Create VM
- Modify CPU & RAM
- Configure networking
- Create or verify virtual disk
- Run unattended installation
Provide status output and stop on any failure.
