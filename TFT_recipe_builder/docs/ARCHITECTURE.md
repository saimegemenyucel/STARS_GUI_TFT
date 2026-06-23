# Recipe Builder — Architecture

## Layering

```
run.py
  └─ bootstrap/qt_app.py
       └─ ui/main_window.py
            ├─ ui/recipe_list.py            # saved-recipe panel (signals)
            ├─ ui/dialogs/process_step_dialog.py
            ├─ ui/dialogs/save_recipe_dialog.py
            ├─ ui/dialogs/load_recipe_dialog.py
            └─ bootstrap/container.py        # DI: main + working services
                 └─ logic/recipe_service.py  # CRUD over one connection
                      ├─ logic/models.py     # Recipe, ProcessStep
                      ├─ logic/enums.py       # ProcessType, SubstrateType
                      └─ logic/validation.py
sql/db_ops.py        # main connection + in-memory working connection
shared/              # schema, DB, style
```

## Working vs main database

The editor manipulates an in-memory `Recipe` object. After every change the
draft is auto-saved into an **in-memory SQLite 'working database'**
(`db_ops.create_working_connection`) via the same `RecipeService` class. Nothing
touches the persistent store until the user clicks **Save Recipe**, which calls
`Container.commit_to_main` → `RecipeService.save_recipe` against the main
connection.

Because `RecipeService` is bound to a single connection, the identical CRUD code
serves both stores — only the connection differs (dependency injection via
`Container`).

## Design notes

- **Models are plain dataclasses** with `from_row` / `gas_mixture_json` helpers;
  gas mixtures are dicts in memory and JSON strings in the database.
- **Validation is separate** from persistence (`logic/validation.py`) so the
  dialogs can validate a single step and the save path can validate the whole
  recipe.
- **Save replaces steps transactionally**: updating a recipe deletes its old
  steps and reinserts the current list inside one transaction, rolling back on a
  uniqueness conflict (`RecipeExistsError`).
