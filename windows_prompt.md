Create a new virtual machine using the tools. Use the following requirements:

1. VM Creation

- VM Name: windowsTest
- Operating System: Windows (64-bit)
- CPUs: 2
- Memory: 4096 MB

2. Networking

- Configure adapter 1 to NAT

3. Customization

- Change the display memory to 128 MB
- Change the graphics controller to VBoxSVGA
- Enable mouse integration
- Set clipboard mode to bidirectional

4. Storage & ISO

- Create new hard drive, 150 GB
- mount the iso: C:\ISOs\win11eval.iso

5. Unattended Installation

- Perform an unattended Windows installation with:
- Username: alice
- Password: boblikestoclickonspamemails
- Hostname: windowsTest.local
- iso: C:\ISOs\win11eval.iso
- Enable Install Guest Additions
- Enable Install in Background

6. Workflow Expectations

Execute the steps in correct order:
- Create VM
- Modify CPU & RAM
- Modify VM according to customizations
- Configure networking
- Create or verify virtual disk
- Run unattended installation
Provide status output and stop on any failure.
