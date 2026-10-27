from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from Autodesk.Revit.Exceptions import OperationCanceledException

family_path = r"C:\Families\Chair.rfa"

# Get the current document
doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# Load the family
with Transaction(doc, "Load Family") as t:
    t.Start()
    family = clr.Reference[Family]()
    loaded = doc.LoadFamily(family_path, family)
    t.Commit()

# Select a family type
symbol = None

if family.Value:
    for symbol_id in family.Value.GetFamilySymbolIds():
        symbol = doc.GetElement(symbol_id)
        break

# Place the family
if symbol:
    with Transaction(doc, "Place Family") as t:
        t.Start()

        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()

        point = XYZ(0, 0, 0)
        level = FilteredElementCollector(doc).OfClass(Level).FirstElement()

        if level:
            doc.Create.NewFamilyInstance(
                point,
                symbol,
                level,
                StructuralType.NonStructural
            )

        t.Commit()
