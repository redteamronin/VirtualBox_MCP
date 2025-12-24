# Prerequistes:

- VirtualBox
- Run setup.py for vboxapi

# vboxapi setup:

Windows:
```PowerShell
PS C:\Program Files\Oracle\VirtualBox\sdk\installer\python> python .\vboxapisetup.py install
```

MacOS:
```bash
export VBOX_INSTALL_PATH="/Applications/VirtualBox.app/Contents/MacOS"
python3.11 /Applications/VirtualBox.app/Contents/MacOS/sdk/installer/python/vboxapisetup.py install
```
NOTE: I had to install python3.11 as it was failing with python3.14

# Validate install:

If the following results in no errors, we should be good.

```PowerShell
PS C:\Users\redteamronin> python
Python 3.12.0 (tags/v3.12.0:0fb18b0, Oct  2 2023, 13:03:39) [MSC v.1935 64 bit (AMD64)] on win32
Type "help", "copyright", "credits" or "license" for more information.
>>> import vboxapi
>>> exit()
PS C:\Users\redteamronin>
```

# Adding to LM Studio

Modify the mcp.json and add 
```
"virtualbox_api": {
  "command": "python",
  "args": [
    "C:\\Users\\redteamronin\\VirtualBox_MCP\\virtualbox_api_server.py"
  ]
}
```

Then ensure the tool is enabled in LM Studio.
