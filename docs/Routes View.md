# Data · Routes

[User guide](README.md) · [Shared table controls and CSV](<Project Files and CSV.md>)

Use **Data · Routes** to inspect course assignments as a table. Each route belongs to exactly one participant record. Participants can have no route; a route cannot be shared between participants.

## Columns

| Column | Contents |
| --- | --- |
| ID | Unique route identifier, `R-XXXXX` |
| Appetizer | Appetizer stop reference, or empty |
| Main dish | Main-dish stop reference, or empty |
| Dessert | Dessert stop reference, or empty |

The owner is linked through the participant's **Route** field in [Data · Participants](<Participants View.md>). Select a route and click **Show participant** to open its owner.

## Creating and editing routes

Create routes with **+ Add** in the [Map view](<Map View.md>) or by applying automatic generation. There is no Add button in this table. New IDs are generated automatically.

Select a route and click **Edit selected** to choose stops from course-specific dropdowns. Courses can be left unassigned. **Safe Edit** restricts new choices to eligible hosts; existing assignments remain visible for inspection or replacement. **Save** accepts and **Cancel** discards the changes.

Route edits update related memberships and assign an unassigned host to their hosting stop for that course. Run **Verify all routes** afterwards, or enable **Verify on Change**.

Double-click a course stop reference to open its [Stops](<Stops View.md>) row. Double-clicking the route ID opens the edit dialog. A single click selects without navigating.

## Empty and incomplete routes

Clearing an assignment does not delete the route. Empty and incomplete records remain here and in the Map view's Routes list.

Verification reports an incomplete-route warning for missing courses and an empty-route error when all three are unassigned. With **Respect existing routes** enabled, generation fills empty slots while preserving assigned stops.

## CSV fields

Exports contain `id`, `appetizer_stop_id`, `main_stop_id`, and `dessert_stop_id`.

Missing or blank IDs can be generated, but each imported route must still have a matching participant **route_id**. A Routes CSV has no owner column. Preserve IDs and links when exchanging all three tables, or use a `.dsf` project instead.

Import replaces the Routes table and must preserve its relationship to Participants; mismatched route links are rejected. Stop references should point to the matching records in Stops.

## Removing routes

**Remove selected** deletes the route and clears its participant's route reference after confirmation. Stops no longer used by other routes are deleted too. Shared stops remain, and the deleted route's owner is removed from guest lists.

**Delete all** removes every route, including filtered-out rows. Participants then have no route entries and are available through **+ Add** on the map.

To keep a route available for completion later, clear its course assignments rather than deleting it.
