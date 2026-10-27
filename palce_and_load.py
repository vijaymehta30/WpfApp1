```python
import clr
import os

from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    Transaction,
    Family,
    FamilySymbol,
    FilteredElementCollector,
    XYZ,
    ElementId
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

doc = revit.doc
uidoc = revit.uidoc


def load_and_place_family():
    # 1. Choose a family file
    family_path = forms.pick_file(
        file_ext="rfa",
        title="Select Family to Load and Place"
    )

    if not family_path:
        forms.alert("No family file selected.")
        return

    family = None

    try:
        # 2. Load the family or retrieve it if already loaded
        family_ref = clr.Reference[Family]()

        with Transaction(doc, "Load Family") as t:
            t.Start()

            loaded = doc.LoadFamily(family_path, family_ref)

            if loaded:
                family = family_ref.Value

            t.Commit()

        # If already loaded, retrieve it from the project
        if family is None:
            expected_name = os.path.splitext(
                os.path.basename(family_path)
            )[0]

            for item in FilteredElementCollector(doc).OfClass(Family):
                if item.Name == expected_name:
                    family = item
                    break

        if family is None:
            raise Exception(
                "Could not load or find the selected family."
            )

        # 3. Get the available family types
        symbol_ids = list(family.GetFamilySymbolIds())

        if not symbol_ids:
            raise Exception("No family types found.")

        symbols = [
            doc.GetElement(symbol_id)
            for symbol_id in symbol_ids
        ]

        # 4. Let the user choose a family type
        symbol_names = [
            "{}".format(symbol.Name)
            for symbol in symbols
        ]

        selected_name = forms.SelectFromList.show(
            symbol_names,
            title="Choose Family Type",
            button_name="Select Type"
        )

        if not selected_name:
            forms.alert("No family type selected.")
            return

        symbol = symbols[symbol_names.index(selected_name)]

        # 5. Ask the user to select the placement point
        forms.alert(
            "Family loaded successfully.\n\n"
            "Click OK, then select a point in the Revit view."
        )

        point = uidoc.Selection.PickPoint(
            "Select the family placement point"
        )

        # 6. Activate the type and place the family
        with Transaction(doc, "Place Family") as t:
            t.Start()

            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()

            instance = doc.Create.NewFamilyInstance(
                point,
                symbol,
                StructuralType.NonStructural
            )

            t.Commit()

        # 7. Select and zoom to the placed instance
        selected_ids = List[ElementId]()
        selected_ids.Add(instance.Id)

        uidoc.Selection.SetElementIds(selected_ids)
        uidoc.ShowElements(instance.Id)

        forms.alert(
            "Family placed successfully!\n\n"
            "Family: {}\n"
            "Type: {}".format(family.Name, symbol.Name),
            title="Success"
        )

    except OperationCanceledException:
        forms.alert("Placement cancelled.")

    except Exception as e:
        forms.alert(
            "Error:\n{}".format(str(e)),
            title="Family Loader"
        )


load_and_place_family()
```
