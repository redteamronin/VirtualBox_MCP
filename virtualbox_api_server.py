#!/usr/bin/env python3
"""
VirtualBox MCP Server (vboxapi / Main API)

Return normalization contract (applied end-to-end):
- Tools that return strings MUST use one of:
    OK:   <one-line summary>
    WARN: <one-line summary>
    ERR:  <one-line summary>
  Followed by optional bullet metadata lines:
    • key=value

Notes:
- vbox_show_vm_info returns a dict (kept as dict by design). Its error case returns a dict
  with a consistent "status"/"message" shape rather than raising.

Tool List:
- vbox_list_vms: gets a list of the VMs, name only
- vbox_show_vm_info: fetches detailed info about an particular VM
- vbox_create_vm: creates a VM with name and OS
- vbox_start_vm: starts a VM
- vbox_stop_vm: stops a VM
- vbox_delete_vm: deletes a VM, delete disk is true
- vbox_modify_vm: modify a VM, such as CPU count and RAM
- vbox_create_disk: creates a hard drive (SATA) for a VM and mounts to VM
- vbox_attach_iso: mounts to the VM, port numerically 1 up from the hard drive
- vbox_get_ip: gets the VMs ip address, requires guest additions
- vbox_set_network_adapter: bridged, NAT
- vbox_add_shared_folder: add shared folder to VM mapping to local host directory
- vbox_remove_shared_folder: remove shared folder by name from the VM
- vbox_modify_display: modify the video memory of the VM display 
- vbox_set_mouse_integration: enables mouse integration allowing for seemless mouse transition to and from the host/VM
- vbox_set_graphics_controller: modify the graphics controller for the VM display
- vbox_set_clipboard_mode: modify the clipboard settings for the VM
- vbox_set_drag_and_drop: modify the drag and drop settings for the VM
- vbox_unattended_linux_install: create viso for unattended installation of the linux operating system, can use username/password/iso
- vbox_unattended_windows_install: create viso for unattended installation of the windows operating system, can use username/password/iso
"""

import os
import sys
import logging
from mcp.server.fastmcp import FastMCP
import vboxapi

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("virtualbox-api-server")

mcp = FastMCP("virtualbox")

# ---------------------------------------------------------------------------
# MCP return helpers (NORMALIZED CONTRACT)
# ---------------------------------------------------------------------------


def mcp_ok(msg: str, **fields) -> str:
    lines = [f"OK: {msg}"]
    for k, v in fields.items():
        lines.append(f"• {k}={v}")
    return "\n".join(lines)


def mcp_warn(msg: str, **fields) -> str:
    lines = [f"WARN: {msg}"]
    for k, v in fields.items():
        lines.append(f"• {k}={v}")
    return "\n".join(lines)


def mcp_err(msg: str, **fields) -> str:
    lines = [f"ERR: {msg}"]
    for k, v in fields.items():
        lines.append(f"• {k}={v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _mgr():
    """Get VirtualBox manager instance."""
    return vboxapi.VirtualBoxManager(None, None)


def _vbox(mgr):
    """Get VirtualBox object from manager."""
    return mgr.getVirtualBox()


def _find_machine(vbox, name_or_id: str):
    """Find a machine by name or UUID."""
    return vbox.findMachine(name_or_id)


def _get_session(mgr, vbox):
    """Get a new session object."""
    return mgr.getSessionObject(vbox)


def _wait_progress(progress, timeout_ms: int = -1):
    """Wait for a progress operation to complete and check for errors."""
    progress.waitForCompletion(timeout_ms)
    if hasattr(progress, "resultCode") and progress.resultCode != 0:
        raise RuntimeError(f"VirtualBox progress failed: resultCode={progress.resultCode}")


def safe_bool(value: str, default: bool = False) -> bool:
    """Convert string to boolean with sensible defaults."""
    if value is None:
        return default
    v = str(value).strip().lower()
    if not v:
        return default
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def vbox_list_vms(filter_text: str = "") -> str:
    """List all registered VirtualBox VMs with optional name filter."""
    filt = filter_text.strip().lower()
    mgr = _mgr()
    vbox = _vbox(mgr)

    names = []
    for m in vbox.machines:
        if not filt or filt in m.name.lower():
            names.append(m.name)

    if not names:
        if filt:
            return mcp_warn("No VMs matched filter", filter=filter_text)
        return mcp_warn("No VirtualBox VMs found")

    return mcp_ok(
        "VMs listed",
        count=len(names),
        filter=(filter_text if filt else None),
        vms=", ".join(sorted(names)),
    )


@mcp.tool()
async def vbox_show_vm_info(vm_name: str = "") -> dict:
    """
    Show detailed info for a specific VM (returns dict).
    """
    if not vm_name:
        return {"status": "ERR", "message": "vm_name is required"}

    mgr = _mgr()
    vbox = _vbox(mgr)
    c = mgr.constants
    m = _find_machine(vbox, vm_name)

    # ------------------------------------------------------------------
    # Safe enum mapping (kept for non-vm_state fields)
    # ------------------------------------------------------------------

    def enum_map(prefix: str):
        mapping = {}
        for attr in dir(c):
            if attr.startswith(prefix):
                try:
                    mapping[getattr(c, attr)] = attr.replace(prefix, "").lower()
                except Exception:
                    pass
        return mapping

    SESSION_STATE_MAP = enum_map("SessionState_")
    GRAPHICS_CONTROLLER_MAP = enum_map("GraphicsControllerType_")
    NETWORK_ATTACHMENT_MAP = enum_map("NetworkAttachmentType_")
    DEVICE_TYPE_MAP = enum_map("DeviceType_")
    STORAGE_BUS_MAP = enum_map("StorageBus_")

    # ------------------------------------------------------------------
    # FIXED: explicit vm_state mapping (authoritative numeric values)
    # ------------------------------------------------------------------

    VM_STATE_MAP = {
        1: "powered_off",
        2: "saved",
        4: "aborted",
        5: "paused",
        6: "running",
    }

    raw_vm_state = int(m.state)

    # ------------------------------------------------------------------
    # Core VM info
    # ------------------------------------------------------------------

    info = {
        "status": "OK",
        "identity": {
            "name": m.name,
            "id": str(m.id),
            "os_type_id": m.OSTypeId,
            "description": m.description,
        },
        "state": {
            "vm_state": {
                "raw": raw_vm_state,
                "name": VM_STATE_MAP.get(raw_vm_state, "other"),
                "is_running": raw_vm_state == 5,
            },
            "session_state": {
                "raw": int(m.sessionState),
                "name": SESSION_STATE_MAP.get(m.sessionState, "unknown"),
            },
            "last_state_change": m.lastStateChange,
            "accessible": bool(m.accessible),
        },
        "hardware": {
            "cpu_count": m.CPUCount,
            "memory_mb": m.memorySize,
            "memory_balloon_mb": m.memoryBalloonSize,
            "cpu_execution_cap": m.CPUExecutionCap,
            "page_fusion_enabled": bool(m.pageFusionEnabled),
        },
    }

    # ------------------------------------------------------------------
    # Display (fully defensive)
    # ------------------------------------------------------------------

    ga = m.graphicsAdapter

    def safe_attr(obj, name, default=None):
        return getattr(obj, name, default)

    info["display"] = {
        "graphics_controller": {
            "raw": int(ga.graphicsControllerType),
            "name": GRAPHICS_CONTROLLER_MAP.get(
                ga.graphicsControllerType, "unknown"
            ),
        },
        "vram_mb": ga.VRAMSize,
        "monitor_count": ga.monitorCount,
        "accelerate_3d": bool(
            safe_attr(ga, "accelerate3DEnabled",
                      safe_attr(ga, "Accelerate3DEnabled", None))
        ),
        "accelerate_2d": bool(
            safe_attr(ga, "accelerate2DVideoEnabled",
                      safe_attr(ga, "Accelerate2DVideoEnabled", None))
        ),
    }

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    network = []
    for slot in range(8):
        na = m.getNetworkAdapter(slot)
        if not na.enabled:
            continue

        network.append(
            {
                "slot": slot,
                "adapter_type_raw": int(na.adapterType),
                "attachment": {
                    "raw": int(na.attachmentType),
                    "name": NETWORK_ATTACHMENT_MAP.get(
                        na.attachmentType, "unknown"
                    ),
                },
                "mac_address": na.MACAddress,
                "cable_connected": bool(na.cableConnected),
            }
        )

    info["network"] = network

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    storage = []
    for ctl in m.storageControllers:
        devices = []
        for att in m.getMediumAttachmentsOfController(ctl.name):
            med = att.medium
            devices.append(
                {
                    "port": att.port,
                    "device": att.device,
                    "device_type": {
                        "raw": int(att.type),
                        "name": DEVICE_TYPE_MAP.get(att.type, "unknown"),
                    },
                    "medium": {
                        "name": med.name if med else None,
                        "location": med.location if med else None,
                        "logical_size": med.logicalSize if med else None,
                        "format": med.format if med else None,
                        "state": str(med.state) if med else None,
                    },
                }
            )

        storage.append(
            {
                "controller_name": ctl.name,
                "bus": {
                    "raw": int(ctl.bus),
                    "name": STORAGE_BUS_MAP.get(ctl.bus, "unknown"),
                },
                "controller_type_raw": int(ctl.controllerType),
                "devices": devices,
            }
        )

    info["storage"] = storage

    # ------------------------------------------------------------------
    # Audio (defensive)
    # ------------------------------------------------------------------

    aa = m.audioSettings.adapter
    info["audio"] = {
        "enabled": bool(aa.enabled),
        "audio_controller_raw": int(aa.audioController),
        "audio_driver_raw": int(aa.audioDriver),
    }

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    info["snapshots"] = {
        "count": m.snapshotCount,
        "current_snapshot_id": (
            str(m.currentSnapshot.id) if m.currentSnapshot else None
        ),
    }

    return info


@mcp.tool()
async def vbox_create_vm(
    vm_name: str = "",
    ostype: str = "",
    base_folder: str = "",
    iso_path: str = "",
) -> str:
    """Create a new VM (VirtualBox 7.x compliant)."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    os_type = ostype.strip() or "Other"

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        # Platform is required in VBox 7.x
        platform = mgr.constants.PlatformArchitecture_x86

        # Determine settings file path
        if base_folder.strip():
            vm_folder = os.path.join(base_folder.strip(), name)
            os.makedirs(vm_folder, exist_ok=True)
            settings_file = os.path.join(vm_folder, f"{name}.vbox")
        else:
            # Empty string lets VBox choose default folder
            settings_file = ""

        # Create the machine
        machine = vbox.createMachine(
            settings_file,  # aSettingsFile
            name,  # aName
            platform,  # aPlatform (REQUIRED)
            [],  # aGroups
            os_type,  # aOSTypeId
            "",  # aFlags
            "",  # aCipher
            "",  # aPasswordId
            "",  # aPassword
        )

        vbox.registerMachine(machine)

        return mcp_ok(
            "VM created",
            vm=name,
            os_type=os_type,
            platform="x86",
            iso_provided=bool(iso_path.strip()),
        )

    except Exception as e:
        return mcp_err("Failed to create VM", vm=name, error=str(e))


@mcp.tool()
async def vbox_start_vm(vm_name: str = "", headless: str = "true") -> str:
    """Start a VM in headless or GUI mode."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        launch_type = "headless" if safe_bool(headless, True) else "gui"
        progress = machine.launchVMProcess(session, launch_type, [])
        _wait_progress(progress)
        session.unlockMachine()
        return mcp_ok("VM started", vm=name, mode=launch_type)
    except Exception as e:
        return mcp_err("Failed to start VM", vm=name, error=str(e))


@mcp.tool()
async def vbox_stop_vm(vm_name: str = "", force: str = "false") -> str:
    """Stop a running VM gracefully or forcefully."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)

        # Shared lock is required for console operations
        machine.lockMachine(session, mgr.constants.LockType_Shared)
        console = session.console

        if safe_bool(force, False):
            progress = console.powerDown()
            _wait_progress(progress)
            method = "forced power down"
        else:
            console.powerButton()
            method = "ACPI shutdown signal sent"

        session.unlockMachine()
        return mcp_ok("VM stop requested", vm=name, method=method)

    except Exception as e:
        # IMPORTANT: lock contention is expected in VBox; report it plainly
        return mcp_err("Failed to stop VM", vm=name, error=str(e))


@mcp.tool()
async def vbox_delete_vm(vm_name: str = "", delete_disks: str = "false") -> str:
    """Unregister a VM and optionally delete all associated disks."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)

        if safe_bool(delete_disks, False):
            media = machine.unregister(3)
            progress = machine.deleteConfig(media)
            _wait_progress(progress)
            return mcp_ok("VM deleted", vm=name, disks="removed")
        else:
            machine.unregister(1)
            machine.deleteConfig([])
            return mcp_ok("VM unregistered", vm=name, disks="preserved")
    except Exception as e:
        return mcp_err("Failed to delete VM", vm=name, error=str(e))


@mcp.tool()
async def vbox_modify_vm(
    vm_name: str = "",
    cpus: str = "",
    memory_mb: str = "",
    vrde: str = "",
) -> str:
    """Modify basic VM settings such as CPUs, memory, and VRDE state."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine

        changed = []
        if cpus.strip():
            mm.CPUCount = int(cpus.strip())
            changed.append(f"cpus={cpus.strip()}")
        if memory_mb.strip():
            mm.memorySize = int(memory_mb.strip())
            changed.append(f"memory_mb={memory_mb.strip()}")
        if vrde.strip():
            mm.VRDEServer.enabled = safe_bool(vrde, False)
            changed.append(f"vrde={'on' if safe_bool(vrde, False) else 'off'}")

        if not changed:
            session.unlockMachine()
            return mcp_warn("No changes requested", vm=name, hint="Provide cpus, memory_mb, or vrde")

        mm.saveSettings()
        session.unlockMachine()
        return mcp_ok("VM updated", vm=name, changes=", ".join(changed))
    except Exception as e:
        return mcp_err("Failed to modify VM", vm=name, error=str(e))


@mcp.tool()
async def vbox_create_disk(
    vm_name: str = "",
    disk_size_gb: str = "50",
    disk_format: str = "VDI",
    disk_variant: str = "Standard",
    storage_controller: str = "SATA",
    port: str = "0",
    device: str = "0",
    disk_dir: str = "",
) -> str:
    """Create and attach a virtual disk."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)
    c = mgr.constants

    try:
        machine = vbox.findMachine(name)

        # Check VM state
        if machine.state != c.MachineState_PoweredOff:
            return mcp_err(
                "VM must be powered off",
                vm=name,
                state=str(machine.state),
            )

        # Lock machine to add/check controller
        session = mgr.getSessionObject(vbox)
        machine.lockMachine(session, c.LockType_Write)
        mm = session.machine

        # Check if controller exists, create if needed
        controller_exists = any(ctl.name == storage_controller for ctl in mm.storageControllers)
        if not controller_exists:
            if storage_controller.upper() == "SATA":
                ctl = mm.addStorageController(storage_controller, c.StorageBus_SATA)
                ctl.controllerType = c.StorageControllerType_IntelAhci
                ctl.portCount = 4
            elif storage_controller.upper() == "IDE":
                ctl = mm.addStorageController(storage_controller, c.StorageBus_IDE)
                ctl.controllerType = c.StorageControllerType_PIIX4
            else:
                session.unlockMachine()
                return mcp_err("Unsupported controller type", controller=storage_controller)

        mm.saveSettings()
        session.unlockMachine()

        # Determine disk path
        if disk_dir.strip():
            disk_path = os.path.join(disk_dir.strip(), f"{name}.vdi")
        else:
            vm_dir = os.path.dirname(machine.settingsFilePath)
            disk_path = os.path.join(vm_dir, f"{name}.vdi")

        # Create disk if it doesn't exist
        created = False
        if not os.path.exists(disk_path):
            size_bytes = int(disk_size_gb) * 1024 * 1024 * 1024
            medium = vbox.createMedium(
                disk_format,
                disk_path,
                c.AccessMode_ReadWrite,
                c.DeviceType_HardDisk,
            )

            variants = (
                [c.MediumVariant_Fixed] if disk_variant.lower() == "fixed" else [c.MediumVariant_Standard]
            )

            progress = medium.createBaseStorage(size_bytes, variants)
            progress.waitForCompletion(-1)
            created = True
        else:
            # Open existing disk
            medium = vbox.openMedium(
                disk_path,
                c.DeviceType_HardDisk,
                c.AccessMode_ReadWrite,
                False,
            )

        # Check if something is already attached at this location
        session = mgr.getSessionObject(vbox)
        machine.lockMachine(session, c.LockType_Write)
        mm = session.machine

        req_port = int(port)
        req_dev = int(device)

        for att in mm.getMediumAttachmentsOfController(storage_controller):
            if att.port == req_port and att.device == req_dev and att.medium is not None:
                session.unlockMachine()
                return mcp_err(
                    "Medium already attached at target",
                    vm=name,
                    controller=storage_controller,
                    port=req_port,
                    device=req_dev,
                )

        # Attach disk
        mm.attachDevice(
            storage_controller,
            req_port,
            req_dev,
            c.DeviceType_HardDisk,
            medium,
        )

        mm.saveSettings()
        session.unlockMachine()

        return mcp_ok(
            "Disk attached",
            vm=name,
            size_gb=disk_size_gb,
            disk_path=disk_path,
            created=created,
            controller=storage_controller,
            port=req_port,
            device=req_dev,
        )

    except Exception as e:
        return mcp_err("Failed to create/attach disk", vm=name, error=str(e))


@mcp.tool()
async def vbox_attach_iso(
    vm_name: str = "",
    iso_path: str = "",
    storage_controller: str = "SATA",
    port: str = "1",
    device: str = "0",
) -> str:
    """Attach an ISO image to the VM. Note: Port 0 is typically reserved for hard disks."""
    name = vm_name.strip()
    iso = iso_path.strip()
    if not name or not iso:
        return mcp_err("vm_name and iso_path are required", vm=name or None, iso=iso or None)

    mgr = _mgr()
    vbox = _vbox(mgr)
    c = mgr.constants

    try:
        machine = vbox.findMachine(name)

        # Check VM state
        if machine.state != c.MachineState_PoweredOff:
            return mcp_err("VM must be powered off", vm=name, state=str(machine.state))

        requested_port = int(port)
        requested_device = int(device)

        # Pre-check attachments (avoid locking if obviously occupied)
        for ctl in machine.storageControllers:
            if ctl.name == storage_controller:
                for att in machine.getMediumAttachmentsOfController(ctl.name):
                    if att.port == requested_port and att.device == requested_device and att.medium is not None:
                        medium_type = "disk" if att.type == c.DeviceType_HardDisk else "dvd"
                        return mcp_err(
                            "Medium already attached at target",
                            vm=name,
                            controller=storage_controller,
                            port=requested_port,
                            device=requested_device,
                            attached_type=medium_type,
                            hint="Hard disks are typically on port 0; use port>=1 for ISO",
                        )

        # Lock machine to add/check controller
        session = mgr.getSessionObject(vbox)
        machine.lockMachine(session, c.LockType_Write)
        mm = session.machine

        # Check if controller exists, create if needed
        controller_exists = any(ctl.name == storage_controller for ctl in mm.storageControllers)
        if not controller_exists:
            if storage_controller.upper() == "SATA":
                ctl = mm.addStorageController(storage_controller, c.StorageBus_SATA)
                ctl.controllerType = c.StorageControllerType_IntelAhci
                ctl.portCount = 4
            elif storage_controller.upper() == "IDE":
                ctl = mm.addStorageController(storage_controller, c.StorageBus_IDE)
                ctl.controllerType = c.StorageControllerType_PIIX4
            else:
                session.unlockMachine()
                return mcp_err("Unsupported controller type", controller=storage_controller)

        mm.saveSettings()
        session.unlockMachine()

        # Open ISO medium
        medium = vbox.openMedium(
            iso,
            c.DeviceType_DVD,
            c.AccessMode_ReadOnly,
            False,
        )

        # Attach ISO
        session = mgr.getSessionObject(vbox)
        machine.lockMachine(session, c.LockType_Write)
        mm = session.machine

        mm.attachDevice(
            storage_controller,
            requested_port,
            requested_device,
            c.DeviceType_DVD,
            medium,
        )

        mm.saveSettings()
        session.unlockMachine()

        return mcp_ok(
            "ISO attached",
            vm=name,
            iso=iso,
            controller=storage_controller,
            port=requested_port,
            device=requested_device,
        )

    except Exception as e:
        return mcp_err("Failed to attach ISO", vm=name, iso=iso, error=str(e))


@mcp.tool()
async def vbox_get_ip(vm_name: str) -> str:
    """Get the IP address of a running VM."""
    if not vm_name:
        return mcp_err("vm_name is required")

    # You previously returned a generic warning; keep behavior but normalize.
    return mcp_warn(
        "IP detection not implemented",
        vm=vm_name,
        hint="Requires Guest Additions; check VM/guest network properties",
    )


@mcp.tool()
async def vbox_set_network_adapter(
    vm_name: str = "",
    adapter: str = "1",
    mode: str = "nat",
    network_name: str = "",
) -> str:
    """Configure a VM network adapter with NAT, bridged, hostonly, or natnetwork."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine

        slot = int(adapter) - 1
        na = mm.getNetworkAdapter(slot)
        na.enabled = True

        mode_lower = mode.lower()
        if mode_lower == "nat":
            na.attachmentType = 1
        elif mode_lower == "bridged":
            na.attachmentType = 2
            if network_name.strip():
                na.bridgedInterface = network_name.strip()
        elif mode_lower == "hostonly":
            na.attachmentType = 4
            if network_name.strip():
                na.hostOnlyInterface = network_name.strip()
        elif mode_lower == "natnetwork":
            na.attachmentType = 5
            if network_name.strip():
                na.NATNetwork = network_name.strip()
        else:
            session.unlockMachine()
            return mcp_err("Unknown network mode", vm=name, adapter=adapter, mode=mode)

        mm.saveSettings()
        session.unlockMachine()
        return mcp_ok(
            "Network adapter updated",
            vm=name,
            adapter=adapter,
            mode=mode_lower,
            network_name=(network_name.strip() or None),
        )
    except Exception as e:
        return mcp_err("Failed to set network adapter", vm=name, adapter=adapter, error=str(e))


@mcp.tool()
async def vbox_add_shared_folder(
    vm_name: str = "",
    share_name: str = "",
    host_path: str = "",
    readonly: str = "false",
) -> str:
    """Add a shared folder to a VM."""
    name = vm_name.strip()
    share = share_name.strip()
    host = host_path.strip()
    if not name or not share or not host:
        return mcp_err("vm_name, share_name, and host_path are required", vm=name or None, share=share or None, host_path=host or None)

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine

        writable = not safe_bool(readonly, False)

        mm.createSharedFolder(
            share,    # name
            host,     # hostPath
            writable, # writable
            True,     # automount
            "",       # autoMountPoint
        )

        mm.saveSettings()
        session.unlockMachine()
        return mcp_ok(
            "Shared folder added",
            vm=name,
            share=share,
            host_path=host,
            readonly=(not writable),
            automount=True,
        )
    except Exception as e:
        return mcp_err("Failed to add shared folder", vm=name, share=share, error=str(e))


@mcp.tool()
async def vbox_remove_shared_folder(vm_name: str = "", share_name: str = "") -> str:
    """Remove a shared folder from a VM."""
    name = vm_name.strip()
    share = share_name.strip()
    if not name or not share:
        return mcp_err("vm_name and share_name are required", vm=name or None, share=share or None)

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine
        mm.removeSharedFolder(share)
        mm.saveSettings()
        session.unlockMachine()
        return mcp_ok("Shared folder removed", vm=name, share=share)
    except Exception as e:
        return mcp_err("Failed to remove shared folder", vm=name, share=share, error=str(e))


@mcp.tool()
async def vbox_modify_display(
    vm_name: str = "",
    vram_mb: str = "",
    monitor_count: str = "",
    scale_factor: str = "",
    acceleration_3d: str = "",
    acceleration_2d: str = "",
) -> str:
    """Modify VM display settings including VRAM, monitors, scaling, and acceleration."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    # NOTE: scale_factor exists in signature but was not implemented in your original code.
    # We keep behavior (no-op) but normalize by warning if user provided it.
    scale_requested = bool(scale_factor.strip())

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine
        ga = mm.graphicsAdapter

        changed = []
        if vram_mb.strip():
            ga.VRAMSize = int(vram_mb.strip())
            changed.append(f"vram_mb={vram_mb.strip()}")
        if monitor_count.strip():
            ga.monitorCount = int(monitor_count.strip())
            changed.append(f"monitor_count={monitor_count.strip()}")
        if acceleration_3d.strip():
            ga.accelerate3DEnabled = safe_bool(acceleration_3d, False)
            changed.append(f"acceleration_3d={'on' if safe_bool(acceleration_3d, False) else 'off'}")
        if acceleration_2d.strip():
            ga.accelerate2DVideoEnabled = safe_bool(acceleration_2d, False)
            changed.append(f"acceleration_2d={'on' if safe_bool(acceleration_2d, False) else 'off'}")

        mm.saveSettings()
        session.unlockMachine()

        if not changed and not scale_requested:
            return mcp_warn("No display changes requested", vm=name)

        if scale_requested:
            # Signature included it; original implementation didn’t.
            # Report it explicitly so callers aren’t misled.
            return mcp_warn(
                "Display updated (partial); scale_factor not implemented",
                vm=name,
                changes=(", ".join(changed) if changed else None),
                scale_factor=scale_factor.strip(),
            )

        return mcp_ok("Display updated", vm=name, changes=", ".join(changed))

    except Exception as e:
        return mcp_err("Failed to modify display", vm=name, error=str(e))


@mcp.tool()
async def vbox_set_mouse_integration(vm_name: str = "", enabled: bool = True) -> str:
    """Enable or disable mouse pointer integration safely."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)
    c = mgr.constants

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)

        # Write lock required for hardware changes
        machine.lockMachine(session, c.LockType_Write)
        mm = session.machine

        # ------------------------------------------------------------
        # Ensure a USB controller exists if enabling USB tablet
        # ------------------------------------------------------------

        if enabled:
            usb_controllers = mm.USBControllers

            if not usb_controllers:
                # Add a default USB 3.0 controller
                usb = mm.addUSBController("USB", c.USBControllerType_XHCI)
            # else: controller already exists

            # USB tablet = absolute pointing device
            mm.pointingHIDType = c.PointingHIDType_USBTablet

        else:
            # Revert to PS/2 mouse (no USB required)
            mm.pointingHIDType = c.PointingHIDType_PS2Mouse

        mm.saveSettings()
        session.unlockMachine()

        return mcp_ok(
            "Mouse integration updated",
            vm=name,
            enabled=enabled,
        )

    except Exception as e:
        try:
            session.unlockMachine()
        except Exception:
            pass

        return mcp_err(
            "Failed to set mouse integration",
            vm=name,
            error=str(e),
        )


@mcp.tool()
async def vbox_set_graphics_controller(vm_name: str = "", controller: str = "vmsvga") -> str:
    """Set the graphics controller type for the VM."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine
        ga = mm.graphicsAdapter

        controller_map = {"vboxvga": 1, "vmsvga": 2, "vboxsvga": 3, "none": 0}
        ctl_key = controller.lower().strip()
        if ctl_key not in controller_map:
            session.unlockMachine()
            return mcp_err("Unknown controller type", vm=name, controller=controller)

        ga.graphicsControllerType = controller_map[ctl_key]
        mm.saveSettings()
        session.unlockMachine()
        return mcp_ok("Graphics controller updated", vm=name, controller=ctl_key)
    except Exception as e:
        return mcp_err("Failed to set graphics controller", vm=name, error=str(e))


@mcp.tool()
async def vbox_set_clipboard_mode(vm_name: str = "", mode: str = "bidirectional") -> str:
    """Set clipboard sharing mode between host and guest."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine

        mode_map = {"disabled": 0, "hosttoguest": 1, "guesttohost": 2, "bidirectional": 3}
        key = mode.lower().strip()
        if key not in mode_map:
            session.unlockMachine()
            return mcp_err("Unknown clipboard mode", vm=name, mode=mode)

        mm.clipboardMode = mode_map[key]
        mm.saveSettings()
        session.unlockMachine()
        return mcp_ok("Clipboard mode updated", vm=name, mode=key)
    except Exception as e:
        return mcp_err("Failed to set clipboard mode", vm=name, error=str(e))


@mcp.tool()
async def vbox_set_drag_and_drop(vm_name: str = "", mode: str = "bidirectional") -> str:
    """Set drag and drop mode between host and guest."""
    name = vm_name.strip()
    if not name:
        return mcp_err("vm_name is required")

    mgr = _mgr()
    vbox = _vbox(mgr)

    try:
        machine = _find_machine(vbox, name)
        session = _get_session(mgr, vbox)
        machine.lockMachine(session, 2)
        mm = session.machine

        mode_map = {"disabled": 0, "hosttoguest": 1, "guesttohost": 2, "bidirectional": 3}
        key = mode.lower().strip()
        if key not in mode_map:
            session.unlockMachine()
            return mcp_err("Unknown drag and drop mode", vm=name, mode=mode)

        mm.DNDMode = mode_map[key]
        mm.saveSettings()
        session.unlockMachine()
        return mcp_ok("Drag and drop mode updated", vm=name, mode=key)
    except Exception as e:
        return mcp_err("Failed to set drag and drop", vm=name, error=str(e))


@mcp.tool()
async def vbox_unattended_linux_install(
    vm_name: str = "",
    linux_iso: str = "",
    user: str = "",
    password: str = "",
    locale: str = "en_US",
    timezone: str = "UTC",
    install_additions: str = "true",
    headless: str = "true",
) -> str:
    """Linux unattended install with best-effort detectIsoOS()."""
    name = vm_name.strip()
    iso = linux_iso.strip()

    if not name or not iso:
        return mcp_err("vm_name and linux_iso are required", vm=name or None, iso=iso or None)
    if not user or not password:
        return mcp_err("user and password are required", vm=name, user=(user or None))

    mgr = _mgr()
    vbox = _vbox(mgr)
    c = mgr.constants

    try:
        # Find VM
        machine = vbox.findMachine(name)

        if machine.state != c.MachineState_PoweredOff:
            return mcp_err("VM must be powered off", vm=name, state=str(machine.state))

        # Create unattended installer
        unattended = vbox.createUnattendedInstaller()
        unattended.isoPath = iso
        unattended.machine = machine

        # Best-effort detectIsoOS (non-fatal)
        detected_info = []
        detect_status = "skipped"
        try:
            unattended.detectIsoOS()
            detect_status = "ok"
            if hasattr(unattended, "detectedOSTypeId"):
                detected_info.append(f"OSType={unattended.detectedOSTypeId}")
            if hasattr(unattended, "detectedOSVersion"):
                detected_info.append(f"Version={unattended.detectedOSVersion}")
        except Exception:
            detect_status = "skipped"

        # Configure attributes
        unattended.user = user
        unattended.userPassword = password
        unattended.fullUserName = user
        unattended.hostname = f"{name}.local"
        unattended.locale = locale.replace("-", "_")
        unattended.timeZone = timezone
        unattended.installGuestAdditions = safe_bool(install_additions, True)

        # Prepare, construct media, and reconfigure VM
        unattended.prepare()
        unattended.constructMedia()
        unattended.reconfigureVM()

        # Launch VM (normalized; previously your Linux message said "ready to be started" but it DOES start)
        session = mgr.getSessionObject(vbox)
        launch_type = "headless" if safe_bool(headless, True) else "gui"
        progress = machine.launchVMProcess(session, launch_type, [])
        progress.waitForCompletion(-1)
        session.unlockMachine()

        return mcp_ok(
            "Linux unattended install started",
            vm=name,
            iso=iso,
            launch=launch_type,
            guest_additions=safe_bool(install_additions, True),
            detectIsoOS=detect_status,
            detection=(", ".join(detected_info) if detected_info else None),
        )

    except Exception as e:
        return mcp_err("Failed to start Linux unattended install", vm=name, iso=iso, error=str(e))


@mcp.tool()
async def vbox_unattended_windows_install(
    vm_name: str = "",
    windows_iso: str = "",
    user: str = "",
    password: str = "",
    full_name: str = "",
    hostname: str = "",
    locale: str = "en_US",
    timezone: str = "UTC",
    install_additions: str = "true",
    headless: str = "true",
) -> str:
    """Windows unattended install following official IUnattended workflow."""
    name = vm_name.strip()
    iso = windows_iso.strip()

    if not name or not iso:
        return mcp_err("vm_name and windows_iso are required", vm=name or None, iso=iso or None)
    if not user or not password:
        return mcp_err("user and password are required", vm=name, user=(user or None))

    mgr = _mgr()
    vbox = _vbox(mgr)
    c = mgr.constants

    try:
        machine = vbox.findMachine(name)

        if machine.state != c.MachineState_PoweredOff:
            return mcp_err("VM must be powered off", vm=name, state=str(machine.state))

        # Create unattended installer
        unattended = vbox.createUnattendedInstaller()

        # Set ISO and detect OS
        unattended.isoPath = iso
        unattended.detectIsoOS()

        # Associate with existing machine
        unattended.machine = machine

        # Configure installation parameters
        unattended.user = user
        if hasattr(unattended, "password"):
            unattended.password = password
        if hasattr(unattended, "userPassword"):
            unattended.userPassword = password

        if full_name:
            unattended.fullUserName = full_name
        if hostname:
            unattended.hostname = hostname

        unattended.locale = locale.replace("-", "_")
        unattended.timeZone = timezone
        unattended.installGuestAdditions = safe_bool(install_additions, True)

        # Execute unattended workflow
        unattended.prepare()
        unattended.constructMedia()
        unattended.reconfigureVM()

        # Launch VM (this is the exact section you quoted; now normalized)
        session = mgr.getSessionObject(vbox)
        launch_type = "headless" if safe_bool(headless, True) else "gui"
        progress = machine.launchVMProcess(session, launch_type, [])
        progress.waitForCompletion(-1)
        session.unlockMachine()

        return mcp_ok(
            "Windows unattended install started",
            vm=name,
            iso=iso,
            launch=launch_type,
            guest_additions=safe_bool(install_additions, True),
            user=user,
            hostname=(hostname.strip() or f"{name}.local"),
        )

    except Exception as e:
        return mcp_err("Failed to start Windows unattended install", vm=name, iso=iso, error=str(e))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting VirtualBox (vboxapi) MCP server...")
    mcp.run(transport="stdio")
