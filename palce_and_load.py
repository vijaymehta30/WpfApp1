# -*- coding: utf-8 -*-
"""Load a .rfa into the project and place it repeatedly (Esc to stop)."""
import os
import traceback

import clr
from pyrevit import revit, DB, forms, script
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectSnapTypes
from System.Collections.Generic import List

doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()

PLAN_VIEW_TYPES = (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan,
                   DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan)


class WarningSwallower(DB.IFailuresPreprocessor):
    """Dismiss warnings, print errors and let Revit roll back."""
    def PreprocessFailures(self, accessor):
        for f in accessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(f)
            else:
                print("Revit error: {}".format(f.GetDescriptionText()))
        return DB.FailureProcessingResult.Continue


class OverwriteLoadOptions(DB.IFamilyLoadOptions):
    """Replace an existing family (and its parameter values) on load."""
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = True
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source,
                            overwriteParameterValues):
        source.Value = DB.FamilySource.Family
        overwriteParameterValues.Value = True
        return True


def run_transaction(name, action):
    """Run action() in one transaction; return True only if it committed."""
    t = DB.Transaction(doc, name)
    t.Start()
    try:
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(WarningSwallower())
        t.SetFailureHandlingOptions(opts)
        action()
        status = t.Commit()
    except Exception:
        if t.HasStarted():
            t.RollBack()
        raise
    if status != DB.TransactionStatus.Committed:
        if t.HasStarted():
            t.RollBack()
        return False
    return True


def type_name(symbol):
    p = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    return p.AsString() if p else str(symbol.Id)


def load_family(path):
    """Load (overwriting) and return the Family, or raise."""
    box = clr.StrongBox[DB.Family]()
    result = []

    def action():
        result.append(doc.LoadFamily(path, OverwriteLoadOptions(), box))

    if not run_transaction("Load Family", action):
        raise Exception("Loading the family was rolled back by Revit.")

    family = box.Value
    if family is None:
        # Fall back to a lookup by file name
        expected = os.path.splitext(os.path.basename(path))[0]
        for item in DB.FilteredElementCollector(doc).OfClass(DB.Family):
            if item.Name == expected:
                family = item
                break
    if family is None:
        raise Exception("Could not load or find the family.")
    return family


def pick_symbol(family):
    symbols = [doc.GetElement(sid) for sid in family.GetFamilySymbolIds()]
    symbols = [s for s in symbols if s is not None]
    if not symbols:
        raise Exception("The family has no types.")
    by_name = dict((type_name(s), s) for s in symbols)
    if len(by_name) == 1:
        return symbols[0]
    chosen = forms.SelectFromList.show(
        sorted(by_name.keys()), title="Choose Family Type",
        button_name="Select Type")
    return by_name[chosen] if chosen else None


def pick_level():
    view = doc.ActiveView
    if view.GenLevel is not None:
        return view.GenLevel
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level),
                    key=lambda l: l.Elevation)
    if not levels:
        raise Exception("No levels found in the project.")
    by_name = dict(("{} ({:.2f} ft)".format(l.Name, l.Elevation), l)
                   for l in levels)
    keys = [k for k, _ in sorted(by_name.items(),
                                 key=lambda kv: kv[1].Elevation)]
    chosen = forms.SelectFromList.show(
        keys, title="Choose Placement Level", button_name="Select Level")
    return by_name[chosen] if chosen else None


def place_family():
    # Preconditions
    if doc.IsFamilyDocument:
        forms.alert("Open a project, not a family document.")
        return
    if doc.ActiveView.ViewType not in PLAN_VIEW_TYPES:
        forms.alert("Switch to a plan view first, then run again.")
        return

    path = forms.pick_file(file_ext="rfa", title="Select Family")
    if not path:
        return

    family = load_family(path)
    if family.FamilyPlacementType != DB.FamilyPlacementType.OneLevelBased:
        forms.alert(
            "'{}' is {} and cannot be placed by this tool.\n"
            "Only level-based families are supported.".format(
                family.Name, family.FamilyPlacementType))
        return

    symbol = pick_symbol(family)
    if symbol is None:
        return
    level = pick_level()
    if level is None:
        return

    if not symbol.IsActive:
        def activate():
            symbol.Activate()
            doc.Regenerate()

        if not run_transaction("Activate Type", activate):
            raise Exception("Activating the type was rolled back by Revit.")

    placed = []
    while True:
        try:
            point = uidoc.Selection.PickPoint(
                ObjectSnapTypes.Endpoints | ObjectSnapTypes.Midpoints
                | ObjectSnapTypes.Intersections,
                "Pick placement point for '{}' (Esc to finish)".format(
                    type_name(symbol)))
        except OperationCanceledException:
            break

        created = []

        def action():
            created.append(doc.Create.NewFamilyInstance(
                point, symbol, level, DB.Structure.StructuralType.NonStructural))

        if not run_transaction("Place " + family.Name, action):
            forms.alert("Placement was rolled back by Revit.")
            break
        placed.append(created[0].Id)

    if placed:
        ids = List[DB.ElementId]()
        for i in placed:
            ids.Add(i)
        uidoc.Selection.SetElementIds(ids)
        print("Placed {} x '{}' ({}) on {}".format(
            len(placed), family.Name, type_name(symbol), level.Name))


try:
    place_family()
except Exception as e:
    logger.error(traceback.format_exc())
    forms.alert("Placement failed:\n{}".format(e), title="Load and Place Family")
