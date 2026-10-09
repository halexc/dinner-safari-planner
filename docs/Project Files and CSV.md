# Project files and CSV

[User guide](README.md)

## Top-bar actions

### New Project

**New Project** starts an empty event with default project settings. System preferences, including language, theme, delimiter, and solver time, remain unchanged. If the current project has unsaved changes, a confirmation lets you cancel or discard them. Save the current event first if you want to keep it. Finish route editing or background work before starting a new project.

### Save Project

**Save Project** writes a `.dsf` file with all three tables, their references, and project settings, including warning preferences. Use it to resume planning or share a complete event.

System preferences such as theme, language, delimiter, and solver time remain on the computer. Finish a route draft before saving. The route panel's **Save** commits only to the current workspace; **Save Project** writes the event to disk.

The Save Project button is neutral when the project has no tracked changes. It becomes highlighted after a data or project-setting change and returns to neutral after a successful save, load, or new project. Changing system preferences does not mark the project as changed.

The format is a versioned JSON document; manual editing is normally unnecessary. Verification results are recalculated rather than saved permanently.

### Load Project

**Load Project** restores tables and project settings from a `.dsf` file, replacing the current event. Save changes you want to keep first and read the replacement prompts. Files are checked before replacement; invalid project files do not partially load.

System preferences remain unchanged. Route conflicts can be loaded for repair; run **Verify all routes** afterwards. Finish active editing or background work before loading.

### Export results

**Export results** writes a participant-facing CSV with one row per participant:

| Column | Contents |
| --- | --- |
| Participant name | Name or pairing |
| Appetizer | Appetizer host address |
| Main Dish | Main-dish host address |
| Dessert | Dessert host address |
| Allergies | Combined attendee allergy lists for courses this participant hosts |

Hosted addresses start with **(H)**. Allergy lists include hosts and guests. For multiple hosted courses, attendees are included once each, although identical allergy phrases from different people can repeat. Non-hosts have an empty hosting-allergy column. Missing stops or hosts produce empty address fields.

Verify assignments and review allergy information before distributing results. This is a handout, not a project backup or table-import format. It uses the current CSV delimiter.

## Shared data-table controls

These controls apply to [Participants](<Participants View.md>), [Stops](<Stops View.md>), and [Routes](<Routes View.md>):

- **Search this table** filters displayed rows; clear it to see all rows.
- Click a column heading to sort, then click again to reverse direction. Sorting does not change assignments or IDs.
- Select a row before using **Edit selected** or **Remove selected**.
- Double-click a reference to reveal and select its destination row.
- **Delete all** affects the whole table, including filtered-out rows.

Use edit dialogs rather than typing directly into cells. Participants and Stops have an **Add** button; create routes in the Map view.

Deleting referenced records offers a confirmation with affected references. You can cancel or delete while clearing references. Participant deletion removes its route and clears stop references; stop deletion clears route assignments; route deletion removes included stops when no other route uses them. See each view for details.

## Import CSV

1. Choose **CSV-Delimiter** in Settings.
2. Open the destination data tab and click **Import CSV**.
3. Select a file with a header row.
4. When interpretation is uncertain, review the mapping dialog. Choose a source column for each destination field, or leave optional fields unmapped for defaults. Check the first five preview rows and adjust the import delimiter if needed.
5. Confirm replacement of an existing table, then verify references and routes.

Import replaces the destination table rather than appending. Other tables are retained, although related updates may be needed to maintain route relationships. Invalid data is rejected before replacement.

IDs are optional. Missing or blank IDs are generated as `P-XXXXX`, `S-XXXXX`, or `R-XXXXX`; valid existing IDs are preserved. Generated IDs do not rewrite references in separate files. Participant names are required, and coordinates must be present as a pair or both empty.

For linked CSVs, import participants before referenced stops and routes. Route IDs must match participant route references. Prefer `.dsf` for transferring complete projects without reconstructing links.

CSV field names and course codes stay English in every localization. Quote fields containing the delimiter, such as comma-separated allergies or addresses. Table exports provide templates with correct field names and quoting.

## Export CSV

**Export CSV** writes the whole current table, including searched-out rows and fields not visible as columns, such as participant coordinates. It uses the system delimiter and preserves identifiers and references.

It does not include other tables or project settings. For a complete event use **Save Project**; for course addresses and hosting allergies use **Export results**.
