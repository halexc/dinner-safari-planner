# Dinner Safari Routing

Python foundation for a desktop dinner safari planner: participants cycle between
appetizer, main dish, and dessert hosts.

For a step-by-step Windows or Mac setup, see
[INSTALL (For Dummies).md](<INSTALL (For Dummies).md>). Run `install.bat` on Windows
or `install.command` on Mac to set up Python dependencies and create an icon launcher.
The application uses `res/icon.ico` on Windows and `res/icon.icns` on Mac.

For a tour of all five views, planning workflows, and file operations, see the
[Bike Party user guide](docs/README.md).

Use **Collaborate** to host a project on a local network or VPN, or connect to a
host at `address:45454`. The host synchronizes saved edits and project settings;
striped map nodes show edits reserved by other collaborators. See the
[collaboration guide](docs/Collaboration.md) for setup and supported behavior.

## Environment

Use Python 3.13 (64-bit). A project-local `.venv` is installed; no global Python
packages are required. From this directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\check_environment.py
.\.venv\Scripts\python.exe -m pip check
```

Activation is optional. Using the full interpreter path avoids PowerShell
execution-policy changes. Select `.venv\Scripts\python.exe` in your editor.

To recreate the environment with the recorded dependency versions:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
```

To resolve newer versions within the project's supported ranges:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`pyproject.toml` declares direct dependencies; `requirements-lock.txt` records
the installed third-party versions for this Windows/Python 3.13 environment.
The local editable package is installed separately. This version snapshot is
not a hash-verified, cross-platform lockfile.

## Selected packages

| Package | Intended role | Documentation |
| --- | --- | --- |
| PySide6 | Desktop tabs, editable tables, selection, route controls; Qt WebEngine embeds the map | [Qt for Python](https://doc.qt.io/qtforpython-6/) |
| Folium | Generate Leaflet map HTML, OSM tiles, markers and route overlays | [Folium](https://python-visualization.github.io/folium/latest/) |
| OSMnx + NetworkX | Download OSM cycling networks, snap stops to nodes, compute path geometry and distance matrices | [OSMnx](https://osmnx.readthedocs.io/en/stable/getting-started.html) |
| OR-Tools | CP-SAT course/host assignments with hard constraints and weighted preferences | [CP-SAT](https://developers.google.com/optimization/cp/cp_solver) |
| pandas | CSV import/export and tabular transformations, retaining IDs as strings | [pandas](https://pandas.pydata.org/docs/) |
| Pydantic | Validate participants, stops, route settings and imported rows | [Pydantic](https://docs.pydantic.dev/latest/) |
| geopy | Address geocoding and straight-line distance helpers | [geopy](https://geopy.readthedocs.io/en/stable/) |
| Shapely | Geographic areas and geometry operations | [Shapely](https://shapely.readthedocs.io/en/stable/) |
| SciPy + scikit-learn | OSMnx nearest-node searches on projected and latitude/longitude networks | [OSMnx nearest nodes](https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.distance.nearest_nodes) |
| pytest + Ruff | Behavioral tests, linting and formatting during implementation | [pytest](https://docs.pytest.org/en/stable/), [Ruff](https://docs.astral.sh/ruff/) |

Python's built-in `sqlite3` can handle local persistence without an additional
database dependency. OSMnx supplies its geospatial dependencies transitively.

## Run the GUI

```powershell
.\.venv\Scripts\python.exe -m cykelfest_routing
# Or explore fictional example pairings:
.\.venv\Scripts\python.exe -m cykelfest_routing --demo
```

The desktop GUI has Map, Data · Participants, Data · Stops, Data · Routes and Settings tabs. Add or edit
records using the table-side buttons, then add a pairing's route on the Map tab.
Participants contain identity, address and a Route ID link. Each participant can have
one route record or no assigned route. Empty assigned routes stay visible. Routes have
an `R-XXXXX` ID and Appetizer, Main Dish and Dessert stop links. Double-click the Route ID
in Participants to open Routes, and course stop IDs in Routes to open Stops.
Use **Show participant** in Routes to return to its owner. Use **+ Add** on the map to create an empty route for a participant without one.
**Remove** deletes the selected route record and clears its participant link.
**Clear Routes** does this for all routes. Participants are kept; stops included
only in deleted routes are deleted, and guest memberships for removed routes
are cleared. Removing individual course assignments
keeps the empty route record.
All three tables include column sorting, search and CSV exchange. **Edit selected**
in Routes updates course assignments, host reservations and guest membership using
the same Safe Edit rules as the map.
Route edits synchronize guest membership. Direct stop edits and CSV imports can
introduce inconsistent references; Verify all routes highlights these conflicts.

Each data tab has **Remove selected** and **Delete all**. The confirmation dialog
lists the affected entries and references under **Show Details**, with Cancel as
the default. Deleting a participant deletes their route and clears their host and
guest references; affected stops with no remaining participants can be deleted.
Deleting a stop clears its course references while keeping the route records.
Deleting a route clears its participant link and removes its stops only when no
other route uses them. Delete all applies the same rules to the entire current
table, including rows hidden by search.

### Settings

The **Settings** tab applies changes immediately. System preferences persist locally;
Project Settings are stored in `.dsf` files. Hover
over each setting's name, control, or **?** icon for an explanation.

- **Dark Mode:** switches the GUI, dialogs and tables between a light
  theme and a dark theme. Light mode is the default.
- **Localization:** choose English, German, French, Spanish or Swedish. The
  interface, dialogs, map editing labels and solver messages update immediately.
  English uses the name **Bike Party**. The preference stays on this computer;
  CSV field names, course codes, participant data and `.dsf` contents remain
  unchanged. Language changes wait until any background operation finishes.
- **OSM-data:** selects OpenStreetMap Standard, CARTO Positron (Light) or
  CARTO Dark Matter (Dark), independently of the GUI theme.
- **Maximum solver time:** limits preparation/search for automatic assignments
  to 1–3600 seconds (30 by default). Stored locally, outside project files.
- **Verify on change:** checks routes automatically after edits, CSV imports,
  saves, and map draft changes. Draft checks do not commit edits. When disabled
  (the default), verification runs only when you click **Verify all routes**.
- **CSV-delimiter:** selects comma (default), semicolon, tab or pipe for all
  participant, stop and route imports/exports. The import mapping dialog can
  override it for one file; CSV quoting preserves separators inside values.

**Project Settings** contains Safe Edit and the preferred minimum and maximum
segment lengths. **Project Warnings** has one Ignore toggle for every warning
category and a smooth **0–5 penalty multiplier** slider, with 0.001 precision.
The **Autogen: Minimize #Warnings** column is enabled for every warning by default.
Disable a checkbox to exclude that warning type from the solver's first warning
minimization objective. Its penalty scoring in the following optimization stage
still uses its slider and Ignore setting. Verification continues to report it.
These checkboxes are saved with the project; older projects default to all enabled.
Double-click a slider to reset it to **1**. Zero removes its solver penalty while
leaving verification warnings visible; Ignore hides the warning and overrides its
penalty to zero. Multipliers and Ignore toggles are saved in the project and never
suppress errors. Penalties apply to both warning count and violation severity.
Loading a project restores these options while retaining all
System preferences.

### Manually plan a route

1. In Map, click **+ Add**. The scrollable picker lists only pairings with
   no route entry. Click **Select** or double-click a pairing; **Cancel**
   leaves the workspace unchanged. The pairing opens in Selected route and
   immediately enters **Edit on Map** mode. For an existing route, select it and
   click **Edit on Map**.
2. Click an eligible address to fill the first empty course,
   preserving any courses already assigned. Or hold the left mouse button on an
   address and drag to another address. Dragging from the current main dish host
   sets dessert; dragging from any other address replaces the route with appetizer
   at the start and main dish at the end, clearing dessert.
3. Right-click a numbered stop to remove that course from the draft. Other course
   assignments remain in place. If one address serves multiple courses, choose
   the course to remove from the menu.
4. Click **Save** to commit the draft and synchronize guest memberships, or **Revert**
   to discard it. Other routes and data tables are locked during map editing.

Markers use blue for the pairing's own address, green for zero guests, lime green
for one guest, and yellow for two or more guests. Counts reflect the current draft.
Selecting an unassigned host also assigns that host to the same stop in its own
route, for the same course. These automatic assignments stay in the draft until
Save and are discarded when their stop is removed or the draft is reverted.
Existing host assignments are preserved.

Each course in Selected route has a centering icon and an edit dropdown. Centering
moves the map to that stop; the dropdown replaces only that course or removes it.
Choosing a stop starts a draft; Save commits it and Revert discards it. Hosts without
coordinates are selectable in the dropdown, but their centering button is disabled.

Double-click a route segment to select its route and fit the map to its stops.
Single clicks do not draw a focus rectangle. The centering icon beside the Map
display dropdown fits all host locations without reloading the map.
Marker outlines indicate assigned hosting courses: orange for appetizer, green
for main dish, blue for dessert, black for no course, and red for multiple courses.
The Map key lists these colors, and outlines update while editing a route.

Safe Edit is enabled by default in Settings. Hosts are eligible when their course
assignment is empty or points to their own stop for that course. Safe editing keeps
ineligible map stops visible at 25% opacity and excludes them from course dropdowns.
Disabling Safe Edit shows every host at full opacity and allows every host.
Eligibility is evaluated for the next empty course, or the endpoint course during
a drag. The outlined main dish marker remains available as a continuation anchor,
even when it cannot be assigned to the next course. Selected-route markers are larger and
numbered 1 (appetizer), 2 (main dish), and 3 (dessert), both during editing and in
normal map display. Addresses used more than once show their course numbers together.
Marker opacity transitions between 100% and 25% over 0.5 seconds when eligibility
changes. Ineligible stops remain unassignable, but support hover information,
right-click removal and starting a continuation drag from the main dish stop.
With all courses assigned, the map shows eligible appetizer hosts for restarting.

Hover over overlapping map nodes to double their screen-space distances from
their average center. Small individual random offsets (8–10 pixels before
expansion) separate nodes at identical coordinates into different directions.
Connected route edges follow the displayed node positions, and the nodes return
to their original positions when the pointer leaves the group. This works in
normal map display and during editing; stored coordinates remain unchanged.

Map nodes represent host addresses. Existing course-specific stops are reused;
when needed, new course-specific stops are created only on Save. Abandoned drafts
and abandoned sections do not create committed stop records. Hosts without
coordinates cannot appear on the map; add latitude/longitude in Participants first.

Route list warning/error icons include counts and tooltips for the current
verification results. See the [Map guide](<docs/Map View.md#verifying-routes>)
for every warning and error type.

Enter host latitude/longitude in the participant editor to place it on the map,
or use **Find Addresses** in Participants to look up everyone missing coordinates.
The button sends nonempty addresses to Photon using OpenStreetMap data; include
street, city and country for better matches. Existing coordinates are preserved.
Lookup runs in the background with progress and Cancel, retaining completed
results. Unmatched addresses and service failures appear in the completion report.
Addresses edited or records replaced during lookup are not overwritten. Results
are cached in the application cache folder and requests run sequentially at least
1.1 seconds apart. Export Participants to save the coordinates with your event.

Photon's public endpoint is for modest project use and has no availability
guarantee. For large or recurring batches, use a private Photon instance:
set `CYKELFEST_PHOTON_DOMAIN` (host and optional port) and
`CYKELFEST_PHOTON_SCHEME` (`https` by default, or `http` for a local instance).
See [Photon usage guidance](https://github.com/komoot/photon).

Map lines and distances are straight-line
previews. Select one route, display all routes, or show hosts only. Map tiles and
Leaflet assets require internet access. Normal startup uses an empty workspace;
sample data is opt-in and fictional.

Use **Save Project** and **Load Project** at the top of the window to save or restore
the complete event in a `.dsf` file. This includes all participants, stops, routes,
and Project Settings: Safe Edit, preferred segment lengths and ignored warnings. Finish any route draft or address lookup before saving/loading.
Loading checks the whole file before replacing data and asks before discarding
unsaved changes. Project Settings changes also count as unsaved changes.

The System section contains Dark Mode, OSM-data, Verify on Change and
CSV-Delimiter. These preferences persist on this computer using Qt system
settings and never travel with a project. OSM-data selects OpenStreetMap Standard,
[CARTO Positron or Dark Matter](https://github.com/cartodb/basemap-styles),
independently of the GUI theme. Changing the background preserves map edits.

The `.dsf` format is UTF-8 JSON with `format: "cykelfest-dinner-safari"`, `version: 2`,
arrays named `participants`, `stops`, and `routes`, and a `settings` object.
Every route must link to exactly one participant; participants may have no route. Files retain incomplete/conflicting assignments
so they can be opened and corrected; verification results are recalculated.
Writes replace the destination atomically after the complete file has been written.
Version 1 files remain loadable; their old system settings are ignored.
Unsupported versions or malformed files leave the current project unchanged.

CSV import/export remains available for exchanging individual tables. Export
all three tables to transfer event data through CSV; settings require a `.dsf` file.
New participants receive IDs such as `P-00001`, and new stops
receive IDs such as `S-00001`, including stops created by map editing. IDs are
generated automatically without rewriting existing or imported IDs. Click a
column heading to sort any table ascending/descending. In Stops, double-click any
guest ID to open that participant's data; hover an ID to see the participant name.

Imports replace their respective table after confirmation and
reject malformed records before making changes. IDs are strings and keep leading
zeros. Missing ID columns and blank ID cells receive unique `P-XXXXX`, `S-XXXXX`,
or `R-XXXXX` IDs; supplied IDs are preserved. Participant CSV columns are
`id,name,address,allergies,route_id,latitude,longitude`; only `name` is mandatory. Route CSV
columns are `id,appetizer_stop_id,main_stop_id,dessert_stop_id`; stop fields may be
omitted or empty. Import Participants before Routes: the Routes CSV must contain exactly
the Route IDs linked by Participants. Legacy participant CSVs with course columns
automatically migrate their assignments into route records. Stop CSV columns
are `id,host,guests,course`. Unmapped stop fields default to an empty host, no
guests, and `Appetizer`. `guests` is a JSON array of string IDs inside the CSV
cell; `course` is `Appetizer`, `Main dish`, or `Dessert`.

When column names or the delimiter are uncertain, an import dialog lets you map
each data column to a CSV column, with sample values and a five-row preview.
You can leave optional fields unmapped and select the file's delimiter without
changing the system preference. Cancel leaves the data unchanged. Generated IDs
do not rewrite references in other tables; linked route, host and stop IDs must
still match.

The app opens maximized. Settings include preferred minimum and maximum segment
lengths (0.5 km and 3 km by default), with hover descriptions. Segments outside
these bounds produce warnings; the preferences are soft constraints for
automatic assignment. Distances currently use straight-line estimates between
consecutive courses, not cycling paths. Missing coordinates skip that segment.

An assigned route with no course references produces **Empty route**.
**Repeat meetups** warns when at least two known participants meet together at
two distinct stops on a route. Each warning category can be ignored in Project
Warnings; errors are always reported.

Verify all routes checks guest counts below/above two, short/long segments,
participants hosting zero or multiple courses, missing course assignments, and
stops with missing hosts. Each warning/error category is counted once per route.
Verification also reports a host assigned to a different stop during that course.
Separate icons show counts and severity-specific hover descriptions. Verify on
change also checks map drafts and all routes affected by shared stop changes;
Revert restores diagnostics for the committed data. A segment longer than three
times the preferred maximum produces **Route segment exceeds hard maximum distance**,
even when long-distance warnings are ignored. Equality at the hard limit is allowed.

### Automatic assignment

Click **Generate Routes** in Map to assign all three courses for every participant.
The progress popup shows elapsed time and the configured time limit, and supports
cancellation.

**Pre-Gen**, to its left, greedily seeds up to 25% of participants, rounded down.
It randomly selects owners with empty or absent routes and three distinct hosts
per seed route; no host node is shared between seed routes. The owner hosts
appetizer, and both segments must meet the preferred minimum and maximum lengths.
Existing stop assignments are kept. Main and dessert hosts receive their own
hosting slot when it is empty; triples that would introduce errors are rejected.
Successful seeds are applied immediately and enable **Respect existing routes**
for subsequent full generation. If the target cannot be reached, Pre-Gen reports
how many seeds it found. Cancellation leaves the project unchanged. At least four
participants are required.

All participants need coordinates; use Find Addresses first if necessary. The
CP-SAT solver runs in the background with Cancel and a shared time budget across
preparation and optimization stages. Editing is disabled while it runs.

Hard constraints require exactly one stop per course, a present host at every
active stop, and both route segments at or below three times the preferred maximum.
Distances use the same straight-line estimates as the map and verification; the
cap currently does not guarantee a cycling-network distance.

The objective first minimizes enabled per-route warning categories plus an active
group-size imbalance flag (largest group minus smallest greater than one). It then
reduces violation severity, balances travel, and reduces total event travel, in
that order. Travel balance combines the longest route, average travel, and mean
absolute deviations of route totals and each course-to-course leg. The distance
component discourages making routes longer merely to equalize them.
Ignored warning categories disable their penalties, but never hard
constraints. Group-size balance remains an independent objective. Size counts
pairings including the host, with three as the ideal group size for the current
two-guest warnings. Meeting variation covers the three courses of this event.
Hosting exactly once is preferred but remains soft. Non-hosting has a penalty
even when its first-stage warning-minimization checkbox is disabled. Guest-count
severity remains weighted by affected attendees; group balance is independent
of the warning controls.

Enable **Respect existing routes** in Project Settings to lock all existing route
IDs and their assigned course stop references. The solver fills empty slots in
incomplete or empty routes, assigns participants who have no route entry, and can
add guests to existing stops. Invalid or conflicting assigned stops prevent
generation; correct/remove them or disable this option. If the fixed stops cannot
be completed while satisfying all hard constraints, no changes are applied.
Hard distance limits still apply. This setting is saved
and loaded with the project. It is disabled by default in older projects, whose
warning multipliers default to 1.

Warning minimization receives at most **60% of the total time budget**.
Penalty optimization receives at most **75% of the time remaining when it starts**.
Travel balancing receives 75% of what then remains, leaving the rest for total
distance reduction. Finishing a stage early makes its unused time available to
later stages. Preparation also counts against the total budget. Later stages run
even without an optimality proof, with upper bounds preserving previously
achieved scores. Only a run proving all four priorities globally is labelled
optimal. Intermediate solutions never replace a better retained objective tuple.

Distances are computed once per unique coordinate pair. A valid current solution
is used as a starting candidate even when it is not locked. Multiple randomized
blocks of nine, repairs around locked slots, and guest swaps supply better seeds.
Reserved stages also use validated local moves when there is too little time to
load another CP-SAT model. Every move preserves host presence, locked assignments,
the hard distance cap, and bounds on earlier objectives. Unused warning variables
and distance-table columns are omitted.

For more than 36 participants, the solver starts with smaller, course-specific
host pools around home, current course locations and locked stops. It removes
hosts who cannot be home and choices without a feasible adjoining leg. Search
pools expand when time permits; local moves can also explore beyond these pools.
Restricted searches are labelled **FEASIBLE** and cannot prove global
infeasibility. Full-domain pruning can still prove an impossible locked route.
Hard constraints and independent validation apply to every
returned route. Model-loading and result-validation overhead can extend total
wall time slightly beyond the configured search budget.

A time-limited feasible assignment remains reviewable; the app distinguishes it
from a proven optimal result. No solution or cancellation leaves the project intact.
The review dialog lists host names for each course, estimated route distances,
warning counts/tooltips, and active group-size range. **Apply routes** commits the
independently validated candidate; **Discard** retains the current project.
Applying replaces unlocked route assignments and updates guest lists, retains existing route IDs
where possible, reuses matching host/course stops, and keeps unused stop records.
Save Project to retain the accepted result.

Forced/blacklisted meetings, individual route locks, past-event meeting history,
cycling-network distances and endpoint preferences remain for later development.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
# Optional integration check (loads online map assets and sends native mouse gestures):
.\.venv\Scripts\python.exe scripts\check_map_editor.py
.\.venv\Scripts\python.exe scripts\check_map_overlap.py
# Local, aggregate-only solver benchmark (does not change project data):
.\.venv\Scripts\python.exe scripts\benchmark_solver.py --project test_big.dsf --seconds 5
# Compare worker counts on the same data and budget (automatic default: up to 4):
.\.venv\Scripts\python.exe scripts\benchmark_solver.py --sizes 9 36 60 --seconds 10 --workers 2
```

## Further implementation direction

- **Map tab:** use a horizontal splitter with a roughly 2:1 map/sidebar ratio.
  Give the map about 80% of its column height, with visualization controls below.
  The sidebar holds selected-route details, a scrollable route list, add/remove
  actions and a verify-all action with conflict highlighting.
- **Participants and Routes tabs:** keep identity, address and the Route ID in
  Participants, with course-specific stop references in the linked Routes table.
  Activate a route reference to open Routes and a stop reference to open Stops.
- **Stops tab:** use a separate table model with stop ID, host participant ID and
  guest participant IDs. Store course, coordinates and capacity in the domain
  model as well. Both data tabs get CSV import/export actions.
- **Assignment model:** treat each participant row as one traveling pairing or
  group. Assign groups to hosts per course, including their own hosting course.
  Host capacities, one stop per course, valid references, and forced/blacklisted
  meetings become hard constraints. Hosting rules and the meaning of a forced
  pairing must be specified before implementing these constraints.
- **Objectives:** balance total cycling distances and individual legs, penalize
  repeat encounters and geographic backtracking, and prefer dessert stops near
  one or more configured endpoints. Make weights adjustable. Preferred minimum
  and maximum segment lengths are soft bounds on travel legs.
  Hosting at one's own address is not a travel leg.
- **Separate routing from assignment:** compute cycling-network distances and
  paths first, then pass integer-meter costs into CP-SAT. Straight-line distances
  are only estimates. OSMnx's bike filter is a starting point; local access and
  cycling rules need consideration. Run network work and solving outside the
  GUI thread, with caching, progress reporting and cancellation.
- **Validation:** independently check every proposed or edited assignment,
  including references, course order, capacity, hosting, constraints and repeated
  meetings. Distinguish hard conflicts from soft preference warnings.

Map tiles, network downloads and geocoding require internet access. Keep OSM
attribution visible, cache network/geocoding results, and respect the chosen
providers' usage policies. Folium is a useful starting map renderer; interactive
editing uses a Leaflet/Qt WebChannel bridge.
The environment check runs entirely offline and does not query participant addresses.

Participants can store comma-separated allergies, including multiword entries.
Allergies are included in participant CSV exports and project files; older files
without the field load with an empty allergy entry. When using a comma CSV
delimiter, fields containing commas are automatically quoted.

**Export results** produces one CSV row per participant with their name, three
course addresses (prefixed with `(H)` for hosted courses), and the combined
allergies of the host and guests at their hosting station. If a participant hosts
multiple courses, attendees across those courses are included once each.

The scrollable solution panel below the map shows straight-line leg and total
distance statistics. Total statistics include only complete routes with known
coordinates. Warning/error counts summarize affected routes by issue type after
verification; use **Verify all routes** to refresh them when automatic verification
is disabled.
