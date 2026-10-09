# Checkbox selection and data groups

[User guide](README.md)

Every data row starts with a checkbox. Check multiple entries to work with them together. **Shift-click** a checkbox to set the visible rows between it and the last selected row to the same checked or unchecked state. The range follows the current sort order; filtered-out rows are skipped. Checks remain when sorting, searching, or switching tabs.

The checkbox in the table header checks or unchecks all entries, including filtered-out rows. Individual checkboxes are centered in their column.

**Edit selected** opens only the last active row, regardless of how many boxes are checked. **Remove selected** removes all checked entries in that table after the usual reference confirmation. **Find Addresses** looks up checked participants that lack coordinates; with no entries checked, it looks up all participants without coordinates. **Delete all** still affects the entire table, including hidden rows.

The controls are arranged in two columns to the right of each table. Below them, the **Data groups** panel shows the same groups in all three views.

## Creating and editing groups

- Press **+** to immediately create an empty blue group named **Group 001**, **Group 002**, and so on.
- Select a group and press **−** to remove it. Its data entries remain.
- Double-click the group name to edit it directly in the list. Press Enter to commit or Escape to cancel.
- Double-click its filled color circle to choose one of nine preset colors in a 3×3 grid.

A group can contain participants, stops, and routes together. Entries can belong to more than one group.

## Membership and selection

Select a group, then use these buttons:

| Button | Effect |
| --- | --- |
| Assign | Adds checked entries from all three data views to the group. |
| Unbind | Removes checked entries from all three views from the group. |
| Select | Checks the group's existing entries in all three views. Other checked entries remain checked. |
| Deselect | Unchecks the group's entries in all three views. |

Hidden checked entries are included in these actions. Remove obsolete checks before assigning another group. Deleting data clears the corresponding group memberships.

## Filters

The dropdown to the left of each table's search field filters that table to a group. Each group has a filled circle in its color; **None** has a black outlined circle and shows all entries. Search applies within the group filter. Each view keeps its own filter. Following a reference clears the destination filter and search so that the referenced row is visible.

The Map display panel has a second dropdown for groups. It includes routes whose participant, route record, or any assigned stop belongs to the group, plus their complete paths and host markers. Participant and stop members also display their host locations. During route editing the current route stays visible, and the display filters are disabled until Save or Revert.

The two map dropdowns have equal widths. **Color by Groups**, next to **Show host locations**, is off initially. When enabled, group members receive a wider outer outline in their group color at 50% opacity, preserving the course outline. Participant membership colors the participant's address; stop and route membership colors the corresponding host locations. The first listed group supplies the color when a node belongs to multiple groups.

Groups, names, colors, and memberships are saved in `.dsf` projects and shared during collaboration. Checkbox selections and display filters stay local and are not saved in the project. New Project and Load Project reset them.
