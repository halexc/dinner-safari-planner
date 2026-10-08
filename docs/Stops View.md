# Data · Stops

[User guide](README.md) · [Shared table controls and CSV](<Project Files and CSV.md>)

Use **Data · Stops** to inspect dinner gatherings. A stop represents one course at one host. An address hosting multiple courses uses separate stop records.

## Columns

| Column | Contents |
| --- | --- |
| ID | Unique stop identifier; new records use `S-XXXXX` |
| Host | Hosting participant reference |
| Guests | Visiting participant references; excludes the host |
| Course | Appetizer, Main dish, or Dessert |

The host's address and coordinates come from [Data · Participants](<Participants View.md>). Routes refer to stop IDs, not directly to addresses.

## Adding and editing

Click **Add**, or select a row and click **Edit selected**. The ID is generated automatically and is read-only. Choose a host and course, and enter guest IDs separated by commas, such as `P-00002, P-00003`.

Guests must exist, be unique within the stop, and exclude the host. A host can be left unassigned, but a route using that stop produces a verification error. A new stop defaults to appetizer.

**Save** accepts and **Cancel** discards dialog changes. Direct stop edits can create inconsistencies with route assignments; run **Verify all routes** afterwards. For ordinary planning, editing routes on the map also maintains guest memberships and reserves unassigned hosts at home for that course.

## Following references

Double-click a **Host** or individual **Guest** ID to open the corresponding participant row. Hover over the ID to see their name. A single click does not navigate. Double-clicking the stop ID opens its edit dialog.

## CSV fields

Exports contain `id`, `host`, `guests`, and `course`. Missing or blank IDs are generated. Host and guest IDs must match participants. Courses use the English codes `Appetizer`, `Main dish`, and `Dessert`, regardless of interface language.

Exported guest lists are JSON arrays inside quoted CSV fields. With comma as delimiter:

```csv
id,host,guests,course
S-00001,P-00001,"[""P-00002"", ""P-00003""]",Appetizer
```

Export an existing table to obtain a template. Import replaces the Stops table rather than adding rows; references in other tables still need checking.

## Removing stops

**Remove selected** lets you review affected references and confirm deletion. Deleting a stop clears all route assignments referring to it. The route records remain, even when empty.

**Delete all** removes every stop, including rows hidden by search, and clears references from Routes. Participants remain. Verify afterwards to find incomplete or empty routes.
