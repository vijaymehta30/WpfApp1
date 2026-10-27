```python
import clr
import os

from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    Transaction,
    Family,
    FilteredElementCollector,
    Level,
    ElementId
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

doc = revit.doc
uidoc = revit.uidoc


def load_and_place_family():
    family_path = forms.pick_file(
        file_ext="rfa",
        title="Select Furniture Family"
    )

    if not family_path:
        forms.alert("No family file selected.")
        return

    try:
        # Load the family
        family_ref = clr.Reference[Family]()
        family = None

        with Transaction(doc, "Load Family") as t:
            t.Start()

            loaded = doc.LoadFamily(family_path, family_ref)

            if loaded:
                family = family_ref.Value

            t.Commit()

        # Find the family if it was already loaded
        if family is None:
            expected_name = os.path.splitext(
                os.path.basename(family_path)
            )[0]

            for item in FilteredElementCollector(doc).OfClass(Family):
                if item.Name == expected_name:
                    family = item
                    break

        if family is None:
            raise Exception("Could not load or find the family.")

        # Get available types
        symbols = [
            doc.GetElement(sid)
            for sid in family.GetFamilySymbolIds()
        ]

        if not symbols:
            raise Exception("No family types found.")

        symbol_names = [s.Name for s in symbols]

        selected_name = forms.SelectFromList.show(
            symbol_names,
            title="Choose Family Type",
            button_name="Select Type"
        )

        if not selected_name:
            return

        symbol = symbols[symbol_names.index(selected_name)]

        # Find a level
        levels = list(
            FilteredElementCollector(doc).OfClass(Level)
        )

        if not levels:
            raise Exception("No levels found in the project.")

        level_names = [level.Name for level in levels]

        selected_level_name = forms.SelectFromList.show(
            level_names,
            title="Choose Placement Level",
            button_name="Select Level"
        )

        if not selected_level_name:
            return

        level = levels[level_names.index(selected_level_name)]

        # Pick a point in Revit
        forms.alert(
            "Family is ready.\n"
            "Click OK, then select a placement point."
        )

        point = uidoc.Selection.PickPoint(
            "Select furniture placement point"
        )

        # Activate and place
        with Transaction(doc, "Place Family") as t:
            t.Start()

            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()

            instance = doc.Create.NewFamilyInstance(
                point,
                symbol,
                level,
                StructuralType.NonStructural
            )

            t.Commit()

        # Select and zoom to the instance
        selected_ids = List[ElementId]()
        selected_ids.Add(instance.Id)

        uidoc.Selection.SetElementIds(selected_ids)
        uidoc.ShowElements(instance.Id)

        forms.alert(
            "Family placed successfully!\n\n"
            "Family: {}\nType: {}\nLevel: {}".format(
                family.Name,
                symbol.Name,
                level.Name
            ),
            title="Success"
        )

    except OperationCanceledException:
        forms.alert("Placement cancelled.")

    except Exception as e:
        forms.alert(
            "Placement failed:\n{}".format(str(e)),
            title="Family Loader"
        )


load_and_place_family()
```
