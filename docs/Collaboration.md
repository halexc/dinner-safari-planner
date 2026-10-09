# Collaboration (local network or VPN)

[User guide](README.md)

Collaboration shares a project directly between running copies of Bike Party. One copy is the host; every other copy connects to that host over TCP. No cloud account or cloud server is used.

## Hosting

1. Open or create the project you want to share. Finish any current route draft or background operation.
2. Click **Collaborate**, enter your name, and click **Host**.
3. Share the displayed address with the other participants. The copy icon copies the primary address. Other available addresses are listed below it, including VPN addresses when present.
4. Keep the host application running. The dialog lists collaborators after they have received the project.

Hosting uses TCP port **45454**. Allow incoming connections to the application on your private network if your firewall asks. Choose an address reachable from the clients: a LAN address for the same network or a VPN address for VPN participants. `127.0.0.1` only connects to another instance on the same computer.

The top button becomes darker blue and reads **Collaborating...**. The dialog stays open, Connect is disabled, and **Stop Hosting** is red. Closing the dialog keeps hosting active. Reopen it to inspect participants or stop hosting.

**Stop Hosting** closes the session and disconnects its clients. Each client keeps its last confirmed project copy. Save Project writes a normal `.dsf` file; network connections and edit locks are not saved in that file.

## Connecting

1. Click **Collaborate** and enter your name.
2. Click **Connect**, enter the host's `IPv4-address:port` or hostname, then press ENTER or **OK**. If the port is omitted, 45454 is used.
3. Confirm replacement if your current project has unsaved changes. A successful connection replaces the project with the host's data and project settings, while retaining your system preferences.

The address dialog closes when synchronization succeeds. In the collaboration dialog, **Connected** is green, Host is disabled, and **Disconnect** ends the connection. The name is fixed while the session is active.

An unsuccessful attempt shows **Connection failed...** and leaves your previous project unchanged. You can correct the address and retry, or cancel. Check that the host is running, that the address is reachable through your local network or VPN, and that its TCP port is allowed through the firewall.

## Shared editing

Participant, stop, and saved route edits are sent to the host. The host checks changes, allocates new IDs, and sends the resulting state to every connected client. Conflicting edits are rejected rather than silently overwriting newer data.

Route gestures remain private drafts until **Save**. Entering route editing reserves its participant and current host nodes. Choosing additional hosts reserves those nodes too. Other collaborators see reserved nodes with dark diagonal stripes and cannot edit them. Course menus exclude nodes reserved by someone else.

Reservations cover related host assignments and stop records, not just marker appearance. Table edits and deletion checks also respect them. Locks are conservative: an address reserved for one course is unavailable to other editors for all courses until the reservation is released.

**Save** commits the route through the host. **Revert** discards the draft. Both release its reservations, as does disconnecting. Existing empty route records continue to behave as described in the [Map guide](<Map View.md>).

Unrelated updates continue arriving during a draft. The draft is rebased onto the current project so that saving does not replace unrelated changes. Selection, map display controls, map position, verification results, and system preferences stay local.

## Host-only controls

Connected clients can inspect project settings, but only the host changes them. Host changes appear in the client controls. Clients cannot use New Project, Load Project, Export results, Clear Routes, Delete all, or Generate Routes. CSV imports and Find Addresses are also host-only because they modify the project in bulk.

Clients can still use Save Project and individual table CSV exports to keep local copies. Disconnecting restores standalone functionality while retaining the shared project data.

Finish active route or table edits before project replacement or automatic generation. During host background operations, new client mutations are rejected until the operation finishes.

## Connection loss

The host tracks acknowledged project revisions and checks connections periodically. Unresponsive clients are removed and their locks released. Clients show **Host unreachable...**, keep the last confirmed shared project, and return to standalone mode. Unsaved local route drafts are retained for local completion; they are not automatically uploaded later.

There is no offline change queue or automatic reconnection. Connecting again receives the host's current project. If a connection fails during Save, the host may have accepted the change before its confirmation was lost; reconnect and inspect the route before repeating the edit.

This first version is intended for trusted local networks and VPNs. The TCP connection has no application-level encryption or password authentication. Use the VPN's protection when connecting across the internet; public internet hosting and automatic router traversal are outside this version's scope.

Data groups and their memberships are shared with collaborators. Checked entries and group filters remain local.
