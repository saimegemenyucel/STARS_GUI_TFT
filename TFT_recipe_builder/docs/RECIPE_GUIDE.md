# Recipe Builder — Usage Guide

## Creating a recipe

1. Click **New Recipe** (Ctrl+N) and fill in the name, substrate, process node
   and description.
2. Click **Add Step** and set the process type, name and parameters. Leave a
   numeric field at *(unset)* to store no value.
   - Gas mixture is entered as `name:fraction` pairs, e.g. `SiH4:50, N2O:200`.
3. Use **Move Up / Move Down** to reorder steps (the step numbers update
   automatically). **Edit Step** (or double-click a row) and **Remove Step**
   modify the selection.
4. Click **Save Recipe** (Ctrl+S) to commit it to the database. It then appears
   in the **Saved recipes** list.

The draft is continuously auto-saved to an in-memory working database, so the
editor always reflects a consistent recipe even before you save.

## Loading and editing

- Double-click a recipe in **Saved recipes**, or select it and click **Load
  Selected**. Edits apply to a private copy; **Save Recipe** writes them back.
- Renaming to an existing recipe name is rejected to keep names unique.

## Deleting

- Select a recipe and click **Delete Selected** (confirmation required). Its
  steps are removed via the database cascade.

## Validation rules

- Recipe name, substrate and process node are required; a recipe needs ≥ 1 step.
- Duration must be > 0; pressure and power cannot be negative.
- Temperature is checked against a typical range for the chosen process type and
  warns if outside it.

## Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+N | New recipe |
| Ctrl+S | Save recipe |
| Ctrl+Q | Quit |

## Device Structure tab

Switch to the **Device Structure** tab to view and edit a 2D cross-section of
the transistor (top-gate staggered, defaults from the IGZO TFT paper).

1. Adjust any layer's **material** (editable dropdown) and **thickness (nm)**.
   The cross-section and the layer legend redraw immediately.
2. Set **Channel length L** and **width W**, plus the S/D pad length and the
   channel/gate overlaps, in the **Geometry** group.
3. **Load IGZO Defaults** resets to the paper values
   (Si/SiO₂ · Ti/Pt 5/20 nm · IGZO 30 nm · AlOx 25 nm · Ti/Pt 5/45 nm,
   L = 3 µm, W = 10 µm).
4. **Export PNG…** saves the current schematic.

The vertical scale is true to relative layer thickness; the lateral channel
length is compressed for readability and annotated with its real value.
