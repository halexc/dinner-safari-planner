# Data · Participants

[User guide](README.md) · [Shared table controls and CSV](<Project Files and CSV.md>)

Manage the people or pairings travelling together in **Data · Participants**. Every row is one travelling unit, regardless of how many names it contains. Guest counts and solver group sizes count these records rather than individual people.

## Columns

| Column | Contents |
| --- | --- |
| ID | Unique participant identifier; new records use `P-XXXXX` |
| Name / pairing | Name or names of the pairing |
| Address | Hosting address |
| Route | Route reference, or empty if no route is assigned |
| Allergies | Free text with optional comma-separated items or phrases |

Coordinates are available in the edit dialog and CSV files, rather than as table columns. Each participant can have at most one route. Course stop references belong to [Data · Routes](<Routes View.md>).

## Adding and editing

Click **Add** to create a participant. The ID is generated automatically and is read-only. Enter a name or pairing, address, and any allergies. Allergies default to empty; for example, `peanuts, dairy products`.

Select a row and click **Edit selected**, or double-click a non-reference cell, to open the edit dialog. **Save** accepts and **Cancel** discards dialog changes. Use the Map view to create a route for the participant.

Double-click the **Route** reference to open its row in Data · Routes. A single click selects a row without following a reference.

Allergy text is stored in project files and table exports. It does not constrain the solver. **Export results** gathers allergy lists for attendees at the courses each participant hosts, including the host's own list.

## Finding coordinates

Click **Find Addresses** to look up participants with an address but no coordinates. The lookup uses Photon with OpenStreetMap data and requires internet access. Existing coordinates are preserved.

Include street, city, and country for better matches. The progress dialog allows cancellation; completed lookups are retained. The final summary reports outcomes. Check locations on the map and correct coordinates manually when necessary.

To enter coordinates yourself, use **Edit selected** and provide both latitude and longitude in decimal degrees, or leave both empty. The solver needs coordinates for every participant. Participants without them cannot appear as host markers.

## CSV fields

Exports contain `id`, `name`, `address`, `allergies`, `route_id`, `latitude`, and `longitude`.

Only `name` is required on import. Missing or blank IDs are generated; other fields can use empty defaults. The mapping dialog lets you select source columns when headers are ambiguous.

When comma is the delimiter, quote fields containing commas:

```csv
name,address,allergies
Alex and Sam,"12 Example Street, Example City","peanuts, dairy products"
```

Use `.dsf` for a complete event backup. Generated participant IDs do not automatically repair references in separately imported stop files.

## Removing participants

**Remove selected** offers a confirmation when other records refer to the participant. Inspect the affected references and either cancel or delete while clearing them.

Deleting a participant also deletes their route, clears their host and guest references, and removes stops left without participant references. Stops unique to a deleted route can also be removed. Other routes can become incomplete and need verification afterwards.

**Delete all** affects every participant, including rows hidden by a search. Save a project copy first if you need to retain the data.
