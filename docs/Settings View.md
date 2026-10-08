# Settings

[User guide](README.md) · [Automatic generation](<Map View.md#automatic-route-generation>)

The **Settings** tab groups system and project controls on the left, with **Project Warnings** on the right. Scroll if necessary. Hover over a setting's clarifier or warning control for its description.

Changes take effect without an Apply button. System preferences are remembered on this computer. Project settings and warning preferences are included with **Save Project** and restored by **Load Project**.

## System

These preferences are excluded from `.dsf` files. Loading another project keeps your system preferences.

| Setting | Function | Initial default |
| --- | --- | --- |
| Dark Mode | Switches light and dark GUI themes | Off |
| OSM-data | Selects the map background, independently of Dark Mode | Standard map |
| Verify on Change | Checks affected routes after changes, including map drafts | Off |
| CSV-Delimiter | Comma, semicolon, tab, or pipe for imports and exports | Comma |
| Maximum solver time | Automatic assignment budget, from 1 to 3,600 seconds | 30 seconds |
| Localization | English, German, French, Spanish, or Swedish GUI and solver messages | English |

The map backgrounds are **OpenStreetMap Standard**, **CARTO Positron (Light)**, and **CARTO Dark Matter (Dark)**. Map tiles need internet access. Localization does not translate entered names, addresses, allergies, or CSV field names. The CSV mapping dialog can override the delimiter for a single import.

More solver time can improve results but does not guarantee feasibility or optimality. The progress dialog shows elapsed time; preparation and final validation can affect exact completion time.

## Project Settings

| Setting | Function | Default |
| --- | --- | --- |
| Safe Edit | Limits route choices to hosts at home or unassigned for the edited course | On |
| Preferred minimum segment length (km) | Warns below this length; a soft preference in full generation | 0.5 km |
| Preferred maximum segment length (km) | Warns above this length; a soft preference in full generation | 3 km |
| Respect existing routes | Preserves filled slots during generation and completes missing courses | Off |

Minimum cannot exceed maximum. Segments exceeding **three times the preferred maximum** produce an error and are forbidden by generation. A preferred maximum of 3 km gives a hard maximum of 9 km. Pre-Gen requires its seed segments to meet the preferred minimum and maximum.

Distances are straight-line estimates between courses, excluding travel to the first stop or from the last.

Safe Edit keeps ineligible markers at 25% opacity but prevents choosing them. Disabling it permits conflicting choices; verification still reports errors. It controls editing, not enforcement of solver hard constraints.

Respect existing routes locks individual filled course slots, including incomplete routes. Empty routes can be completed and other participants may join preserved stops. Repair conflicting fixed assignments or disable the setting before generation. **Pre-Gen** enables it automatically.

## Project Warnings

Each warning type has three controls:

| Control | Effect | Default |
| --- | --- | --- |
| Ignore | Hides the warning and removes its solver penalty | Off |
| Autogen: Minimize #Warnings | Includes it in the first warning-minimization objective | On |
| Penalty multiplier | Changes its optimization weight from 0 to 5 | 1 |

Double-click a slider to reset it to **1**. Larger values give a warning more priority; zero removes its optimization weight while leaving it visible unless Ignore is enabled. Turning off **Autogen: Minimize #Warnings** only excludes that type from the first objective; later penalty scoring remains controlled by Ignore and the slider.

For example, to penalize short segments without considering them in the first step, leave **Ignore** off, turn **Autogen: Minimize #Warnings** off, and retain a nonzero multiplier.

Available warning rows:

- Route contains stops with few guests.
- Route contains stops with many guests.
- Short Route segment.
- Long Route segment.
- Participant is not hosting.
- Participant is repeat host.
- Participant is not assigned all 3 stops.
- Repeat meetups.

See [Map verification](<Map View.md#verifying-routes>) for triggers. Guest thresholds count participant records, excluding the host.

Errors cannot be ignored or weighted down. Full generation requires all three courses even when the incomplete-route warning is ignored. Group balancing also has an independent objective; disabling a warning penalty does not disable every related preference.
