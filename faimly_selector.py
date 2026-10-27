import clr
import os

from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    Transaction,
    Family,
    FilteredElementCollector,
    Structure
)
from Autodesk.Revit.Exceptions import OperationCanceledException

from System.Collections.Generic import List
from Autodesk.Revit.DB import ElementId

doc = revit.doc
uidoc = revit.uidoc

family_path = forms.pick_file(
    file_ext="rfa",
    title="Select Furniture Family"
)

if not family_path:
    forms.alert("No family file selected.")
else:
    try:
        # Load or retrieve the family
        family_ref = clr.Reference[Family]()
        family = None

        with Transaction(doc, "Load Furniture Family") as t:
            t.Start()

            loaded = doc.LoadFamily(family_path, family_ref)

            if loaded:
                family = family_ref.Value

            # If loading returned False, search loaded families
            if family is None:
                expected_name = os.path.splitext(
                    os.path.basename(family_path)
                )[0]

                for item in FilteredElementCollector(doc).OfClass(Family):
                    if item.Name == expected_name:
                        family = item
                        break

            t.Commit()

        if family is None:
            raise Exception(
                "Revit did not return the family. "
                "Check the file path and family load errors."
            )

        # Find available types
        symbol_ids = list(family.GetFamilySymbolIds())

        if not symbol_ids:
            raise Exception("This family contains no available types.")

        symbol = doc.GetElement(symbol_ids[0])

        # Select insertion point
        forms.alert(
            "Family loaded or already exists.\n"
            "Click OK, then click a point in the Revit view."
        )

        point = uidoc.Selection.PickPoint(
            "Select furniture placement point"
        )

        # Activate type and place instance
        with Transaction(doc, "Place Furniture") as t:
            t.Start()

            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()

            instance = doc.Create.NewFamilyInstance(
                point,
                symbol,
                Structure.StructuralType.NonStructural
            )

            t.Commit()

        selected_ids = List[ElementId]()
        selected_ids.Add(instance.Id)
        uidoc.Selection.SetElementIds(selected_ids)

        forms.alert(
            "Furniture placed successfully!\n"
            "Family: {}\nType: {}".format(
                family.Name,
                symbol.Name
            )
        )

    except OperationCanceledException:
        forms.alert("Placement cancelled.")

    except Exception as e:
        forms.alert(
            "Error:\n{}".format(str(e)),
            title="Furniture Placement"
        )
