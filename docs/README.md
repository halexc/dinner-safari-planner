# Bike Party user guide

Bike Party plans a dinner safari where participants cycle between appetizer, main-dish, and dessert hosts. A participant record can represent one person or a pairing travelling together.

## Views

| Tab | Guide |
| --- | --- |
| Map | [Plan, edit, generate, and verify routes](<Map View.md>) |
| Data · Participants | [Names, addresses, allergies, and coordinates](<Participants View.md>) |
| Data · Stops | [Hosts, guests, and courses](<Stops View.md>) |
| Data · Routes | [Course assignments and participant links](<Routes View.md>) |
| Settings | [System preferences and project optimization settings](<Settings View.md>) |

The guides use English button names. **Localization** in Settings offers English, German, French, Spanish, and Swedish.

## A first planning session

1. Add or import participants in **Data · Participants**, with one record per travelling pairing.
2. Provide full addresses and use **Find Addresses**, or enter coordinates manually.
3. In **Settings**, choose preferred segment distances and warning priorities.
4. In **Map**, use **+ Add** to plan manually or **Generate Routes** to calculate an assignment. Optionally use **Pre-Gen** to seed routes first.
5. Run **Verify all routes**, inspect the results, and resolve errors.
6. Use **Save Project** to keep the event as a `.dsf` file and **Export results** for a participant-facing CSV.

The map and distance checks currently use straight-line segments, not cycling-road distances. Check actual journeys before distributing the plan.

## Files and shared controls

[Collaboration](Collaboration.md) explains local/VPN hosting, connecting, shared editing, and edit locks.

[Project files and CSV](<Project Files and CSV.md>) explains the top-bar buttons, imports, exports, column mapping, sorting, reference navigation, and deletion.

For installation, see [INSTALL (For Dummies).md](<../INSTALL (For Dummies).md>). For dependencies and developer commands, see the [main README](../README.md).
