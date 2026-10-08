# Install Cykelfest on Windows or Mac

You do not need to know programming. Follow the steps for your computer.
You will need an internet connection and a few minutes for the first installation.
This version requires **64-bit Python 3.13**. Choose a normal Python 3.13 release.
It has not been tested with Python 3.14, a preview release, an embeddable package, or a free-threaded build.

## 1. Install Python

### Windows

1. Open the official [Python downloads for Windows](https://www.python.org/downloads/windows/).
2. Find a **Python 3.13.x** release and click **Windows installer (64-bit)**.
   For example, the [Python 3.13.12 download page](https://www.python.org/downloads/release/python-31312/)
   offers this installer under **Files**. The usual 64-bit installer is for Intel/AMD PCs.
3. Open the downloaded `.exe` file.
4. If offered, tick **Add python.exe to PATH** and keep the Python launcher enabled.
   Then click **Install Now** and follow the prompts.
5. Close the installer once installation finishes.

If you already have Python 3.13 installed, you can skip these steps. Other Python
versions can remain installed; the Cykelfest installer looks for 3.13 specifically.

### Mac

1. Open the official [Python downloads for macOS](https://www.python.org/downloads/macos/).
2. Find a **Python 3.13.x** release and click **macOS 64-bit universal2 installer**.
   The [Python 3.13.12 download page](https://www.python.org/downloads/release/python-31312/)
   also links to this installer under **Files**. Universal2 supports Intel and Apple Silicon Macs.
3. Open the downloaded `.pkg` file and follow **Continue** / **Install**.
4. In Finder, open **Applications → Python 3.13** and double-click
   **Install Certificates.command** to finish setting up secure internet downloads.

## 2. Put the program in its own folder

1. Download or copy the **whole Cykelfest project**, including `src`, `scripts`,
   `res`, `pyproject.toml`, and the install/run scripts.
2. If it is a ZIP file, extract it first. On Windows, right-click the ZIP and choose
   **Extract All**. On Mac, double-click the ZIP.
3. Put the extracted folder somewhere you can keep it, such as **Documents**.
   Do not run it from inside the ZIP, and do not copy a `.venv` folder from another
   computer. Each computer needs its own environment.
4. Open the extracted folder. You should see `install.bat` and `install.command`.

## 3. Install the program

### Windows

1. Double-click **install.bat**.
2. Keep the window open while packages download. Lines such as
   **Requirement already satisfied** mean a package is already installed correctly.
3. Wait for **Installation complete!** and press a key to close the window.
4. A shortcut named **Cykelfest** (`Cykelfest.lnk`) now appears in the project folder
   with the icon from `res/icon.ico`.

### Mac

1. First make the installer runnable. Open **Terminal** using Spotlight
   (press **Command + Space**, type **Terminal**, and press Return).
2. Type `chmod +x ` with a space at the end, then drag **install.command** from
   Finder into the Terminal window. Press Return. Dragging inserts its full path,
   even if the folder name contains spaces.
3. Double-click **install.command** in Finder. If Finder does not open it, type
   `bash ` in Terminal, drag **install.command** into the window, and press Return.
4. Keep the window open until **Installation complete!** appears, then press Return.
5. **Cykelfest.app** now appears in the project folder with the icon from `res/icon.icns`.
   The installer also makes **run.command** runnable.

The installer creates a hidden `.venv` folder containing the private Python
environment. It checks the existing environment, installs the program and any
missing or incompatible dependencies, and checks package compatibility. You can
run it again to repair an installation; it keeps satisfying installed packages.
It does not change your dinner data or install the program's packages globally.

## 4. Start Cykelfest

- **Windows:** double-click the **Cykelfest** shortcut. You can also use **run.bat**.
  You may copy the shortcut to your Desktop.
- **Mac:** double-click **Cykelfest.app**. You can also use **run.command**.
  Keep the `.app` inside the project folder; use a Finder alias if you want a
  Desktop launcher (**File → Make Alias**, then move the alias to the Desktop).

Keep the project folder and `.venv` together. If you move the folder on Windows,
rerun the installer to refresh the shortcut. If you move it on either platform
and it stops working, rename `.venv` to `.venv-old` and rerun the installer;
virtual environments are not intended to be moved between locations or computers.

Use **Save Project** in the program to save your dinner data as a `.dsf` file.
Installation does not start the program automatically. Internet access is needed
for map tiles and address lookup.

## If something goes wrong

- **“Python 3.13 was not found”:** install Python 3.13 using the links above.
  On Windows, rerun the Python installer with the launcher/PATH options enabled.
  Close and reopen Terminal or the installer afterwards.
- **Wrong or incomplete `.venv`:** close Cykelfest, rename the hidden `.venv`
  folder to `.venv-old`, and run the installer again. Show hidden files using
  **View → Show → Hidden items** in Windows Explorer or **Command + Shift + .** in Finder.
  Rename only `.venv`; keep your `.dsf` files.
- **Download or certificate errors:** check internet access. On Mac, run
  **Install Certificates.command** from **Applications → Python 3.13**.
  Rerun the installer after fixing the connection.
- **The launcher opens nothing:** use **run.bat** (Windows) or **run.command**
  (Mac) to see the error. On Mac, the `.app` also writes `cykelfest-launch.log`
  in the project folder. Keep the error text when asking for help.
- **macOS blocks opening a downloaded script/app:** check **System Settings →
  Privacy & Security** for an **Open Anyway** option, after verifying it is the
  project you intended to download. You can also run `bash install.command`
  from Terminal in the project folder. Do not disable system security globally.
- **Packages cannot be installed on your computer:** some dependencies require
  a recent OS and supported processor. Keep the installer error text; the Mac
  launcher has not been tested on a physical Mac in this project's Windows environment.

For program features, CSV formats, settings, and technical setup details, see
[README.md](README.md).
