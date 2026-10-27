import clr

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI import TaskDialog

# Get the active Revit document
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

# Path to the Revit family
family_path = r"C:\Families\Chair.rfa"

# Load and place the family
try:
    family_ref = clr.Reference[Family]()

    with Transaction(doc, "Load and Place Family") as t:
        t.Start()

        # 1. Load the family into the project
        loaded = doc.LoadFamily(family_path, family_ref)

        if loaded:
            family = family_ref.Value
        else:
            # Family may already exist in the project
            family = None
            for f in FilteredElementCollector(doc).OfClass(Family):
                if f.Name == family_path.split("\\")[-1].replace(".rfa", ""):
                    family = f
                    break

        if family is None:
            raise Exception("Could not load or find the family.")

        # 2. Get the first available family type
        symbol = None
        for symbol_id in family.GetFamilySymbolIds():
            symbol = doc.GetElement(symbol_id)
            break

        if symbol is None:
            raise Exception("No family types found.")

        # 3. Activate the family type
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()

        # 4. Find a level in the project
        level = FilteredElementCollector(doc) \
            .OfClass(Level) \
            .FirstElement()

        if level is None:
            raise Exception("No level found in the project.")

        # 5. Place the family in the model
        point = XYZ(0, 0, 0)

        instance = doc.Create.NewFamilyInstance(
            point,
            symbol,
            level,
            StructuralType.NonStructural
        )

        t.Commit()

    # 6. Select the placed family
    uidoc.Selection.SetElementIds(
        List[ElementId]([instance.Id])
    )

    uidoc.ShowElements(instance.Id)

    TaskDialog.Show(
        "Success",
        "Family loaded and placed successfully!"
    )

except Exception as e:
    TaskDialog.Show("Error", str(e))
