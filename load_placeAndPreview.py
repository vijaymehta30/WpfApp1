# -*- coding: utf-8 -*-
"""Preview an .rfa, load it into the project and place it (Esc to stop)."""
import os
import re
import struct
import traceback

import clr
import System
from pyrevit import revit, DB, forms, script
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectSnapTypes
from System.Collections.Generic import List
from System.IO import MemoryStream
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption

doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()

PLAN_VIEW_TYPES = (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan,
                   DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan)


# ---------------------------------------------------------------- preview ---

def _read_ole_stream(data, wanted_prefix):
    """Return the bytes of the first stream whose name starts with
    wanted_prefix in an OLE compound file (the .rfa container), or None."""
    if data[:8] != '\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return None
    ss = 1 << struct.unpack_from('<H', data, 30)[0]
    mss = 1 << struct.unpack_from('<H', data, 32)[0]
    n_fat, dir_start, _, cutoff, mfat_start, _, difat_start, n_difat = \
        struct.unpack_from('<8I', data, 44)
    per_sector = ss // 4
    end_marks = 0xFFFFFFFA

    # FAT sector list: 109 entries in the header, the rest via the DIFAT chain
    difat = list(struct.unpack_from('<109I', data, 76))
    sid = difat_start
    for _ in range(n_difat):
        if sid >= end_marks:
            break
        vals = struct.unpack_from('<%dI' % per_sector, data, (sid + 1) * ss)
        difat.extend(vals[:-1])
        sid = vals[-1]
    fat = []
    for s in [s for s in difat if s < end_marks][:n_fat]:
        fat.extend(struct.unpack_from('<%dI' % per_sector, data, (s + 1) * ss))

    def chain(start, table):
        out, sid = [], start
        while sid < end_marks and len(out) <= len(table):
            out.append(sid)
            sid = table[sid]
        return out

    def read_big(start):
        return ''.join(data[(s + 1) * ss:(s + 2) * ss] for s in chain(start, fat))

    directory = read_big(dir_start)
    root = None
    target = None
    for i in range(len(directory) // 128):
        e = directory[i * 128:(i + 1) * 128]
        name_len = struct.unpack_from('<H', e, 64)[0]
        name = e[:max(name_len - 2, 0)].decode('utf-16-le')
        kind = ord(e[66])
        start = struct.unpack_from('<I', e, 116)[0]
        size = struct.unpack_from('<I', e, 120)[0]
        if kind == 5:
            root = (start, size)
        elif kind == 2 and name.startswith(wanted_prefix) and target is None:
            target = (start, size)
    if target is None:
        return None

    start, size = target
    if size >= cutoff:
        return read_big(start)[:size]
    if root is None:
        return None
    mini_stream = read_big(root[0])
    mini_fat = []
    for s in chain(mfat_start, fat):
        mini_fat.extend(struct.unpack_from('<%dI' % per_sector, data, (s + 1) * ss))
    return ''.join(mini_stream[s * mss:(s + 1) * mss]
                   for s in chain(start, mini_fat))[:size]


def extract_preview_png(path):
    """Return the embedded thumbnail of an .rfa as PNG bytes, or None."""
    with open(path, 'rb') as f:
        data = f.read()
    blob = _read_ole_stream(data, 'RevitPreview')
    if not blob:
        return None
    i = blob.find('\x89PNG\r\n\x1a\n')
    if i == -1:
        return None
    j = blob.find('IEND', i)
    end = j + 8 if j != -1 else len(blob)
    return blob[i:end]


def png_to_bitmap(png):
    stream = MemoryStream(System.Array[System.Byte](bytearray(png)))
    image = BitmapImage()
    image.BeginInit()
    image.StreamSource = stream
    image.CacheOption = BitmapCacheOption.OnLoad
    image.EndInit()
    image.Freeze()
    return image


PREVIEW_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Select Family" Width="880" Height="560" MinWidth="640"
        MinHeight="400" WindowStartupLocation="CenterScreen">
  <Grid Margin="14">
    <Grid.RowDefinitions>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>
    <Grid.ColumnDefinitions>
      <ColumnDefinition Width="320"/>
      <ColumnDefinition Width="14"/>
      <ColumnDefinition Width="*"/>
    </Grid.ColumnDefinitions>

    <Grid Grid.Row="0" Grid.Column="0">
      <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="*"/>
      </Grid.RowDefinitions>
      <DockPanel>
        <Button DockPanel.Dock="Right" Content="Folder..." Width="76"
                Height="26" Margin="8,0,0,0" Click="folder_click"/>
        <TextBlock x:Name="folder_text" VerticalAlignment="Center"
                   TextTrimming="CharacterEllipsis"/>
      </DockPanel>
      <TextBox Grid.Row="1" x:Name="search_box" Height="26" Margin="0,8,0,0"
               VerticalContentAlignment="Center" TextChanged="filter_changed"/>
      <CheckBox Grid.Row="2" x:Name="subfolders" Content="Include subfolders"
                Margin="0,8,0,8" Click="refresh_click"/>
      <ListBox Grid.Row="3" x:Name="file_list"
               SelectionChanged="file_selected"
               MouseDoubleClick="file_doubleclick"/>
    </Grid>

    <Grid Grid.Row="0" Grid.Column="2">
      <Grid.RowDefinitions>
        <RowDefinition Height="Auto"/>
        <RowDefinition Height="*"/>
        <RowDefinition Height="Auto"/>
      </Grid.RowDefinitions>
      <TextBlock x:Name="file_name" FontSize="14" FontWeight="SemiBold"
                 TextWrapping="Wrap"/>
      <Border Grid.Row="1" Margin="0,8" BorderBrush="#CCCCCC"
              BorderThickness="1" Background="#F5F5F5">
        <Grid>
          <Image x:Name="preview_image" Stretch="Uniform"
                 RenderOptions.BitmapScalingMode="HighQuality"/>
          <TextBlock x:Name="no_preview" Foreground="#888888"
                     HorizontalAlignment="Center" VerticalAlignment="Center"
                     TextAlignment="Center" TextWrapping="Wrap" Margin="20"/>
        </Grid>
      </Border>
      <TextBlock Grid.Row="2" x:Name="file_info" Foreground="#666666"
                 TextWrapping="Wrap"/>
    </Grid>

    <StackPanel Grid.Row="1" Grid.Column="0" Grid.ColumnSpan="3"
                Orientation="Horizontal" HorizontalAlignment="Right"
                Margin="0,12,0,0">
      <Button Content="Load and Place" Width="110" Height="28"
              Margin="0,0,8,0" IsDefault="True" Click="place_click"/>
      <Button Content="Cancel" Width="80" Height="28" IsCancel="True"
              Click="cancel_click"/>
    </StackPanel>
  </Grid>
</Window>
"""

MAX_FILES = 3000
BACKUP_RE = re.compile(r'\.\d{4}\.rfa$', re.IGNORECASE)


class PreviewWindow(forms.WPFWindow):
    """Folder browser for .rfa files with a thumbnail preview.
    result is the chosen file path, or None."""

    def __init__(self, folder):
        forms.WPFWindow.__init__(self, PREVIEW_XAML, literal_string=True)
        self.result = None
        self.path = None
        self.folder = None
        self.all_files = []
        self.visible = []
        self._ready = True
        self.set_folder(folder)

    # -- file list ----------------------------------------------------------
    def set_folder(self, folder):
        self.folder = folder
        self.folder_text.Text = folder
        self.folder_text.ToolTip = folder
        self.rescan()

    def rescan(self):
        files = []
        recursive = bool(self.subfolders.IsChecked)
        try:
            if recursive:
                for root, _, names in os.walk(self.folder):
                    for n in names:
                        files.append(os.path.join(root, n))
                    if len(files) > MAX_FILES * 5:
                        break
            else:
                for n in os.listdir(self.folder):
                    files.append(os.path.join(self.folder, n))
        except Exception:
            logger.error(traceback.format_exc())
        self.all_files = sorted(
            [p for p in files
             if p.lower().endswith('.rfa') and not BACKUP_RE.search(p)],
            key=lambda p: os.path.relpath(p, self.folder).lower())[:MAX_FILES]
        self.reload_list()

    def reload_list(self):
        needle = self.search_box.Text.lower()
        self.visible = [p for p in self.all_files if needle in
                        os.path.relpath(p, self.folder).lower()]
        self.file_list.Items.Clear()
        for p in self.visible:
            self.file_list.Items.Add(os.path.relpath(p, self.folder))
        if self.visible:
            self.file_list.SelectedIndex = 0
        else:
            self.clear_preview("No .rfa files here.")

    # -- preview ------------------------------------------------------------
    def clear_preview(self, message):
        self.path = None
        self.file_name.Text = ""
        self.file_info.Text = ""
        self.preview_image.Source = None
        self.no_preview.Text = message

    def show_file(self, path):
        self.path = path
        self.file_name.Text = os.path.basename(path)
        try:
            size_mb = os.path.getsize(path) / (1024.0 * 1024.0)
            self.file_info.Text = "{}\n{:.1f} MB".format(
                os.path.dirname(path), size_mb)
        except Exception:
            self.file_info.Text = path
        self.preview_image.Source = None
        self.no_preview.Text = ""
        try:
            png = extract_preview_png(path)
            if png:
                self.preview_image.Source = png_to_bitmap(png)
            else:
                self.no_preview.Text = "No preview is stored in this file."
        except Exception as e:
            logger.error(traceback.format_exc())
            self.no_preview.Text = "Could not read the preview:\n{}".format(e)

    # -- events -------------------------------------------------------------
    def folder_click(self, sender, args):
        picked = forms.pick_folder(title="Select folder with families")
        if picked:
            self.set_folder(picked)

    def refresh_click(self, sender, args):
        if getattr(self, '_ready', False):
            self.rescan()

    def filter_changed(self, sender, args):
        if getattr(self, '_ready', False):
            self.reload_list()

    def file_selected(self, sender, args):
        if not getattr(self, '_ready', False):
            return
        i = self.file_list.SelectedIndex
        if 0 <= i < len(self.visible):
            self.show_file(self.visible[i])

    def file_doubleclick(self, sender, args):
        self.place_click(sender, args)

    def place_click(self, sender, args):
        if self.path:
            self.result = self.path
            self.Close()

    def cancel_click(self, sender, args):
        self.Close()


def start_folder():
    try:
        last = script.get_config().get_option('last_dir', '')
    except Exception:
        last = ''
    for candidate in (last, os.path.join(os.path.expanduser('~'), 'Documents')):
        if candidate and os.path.isdir(candidate):
            return candidate
    return os.path.expanduser('~')


def choose_family_file():
    """Browse folders, preview each .rfa, return the confirmed path or None."""
    window = PreviewWindow(start_folder())
    window.show_dialog()
    if window.result:
        try:
            cfg = script.get_config()
            cfg.last_dir = window.folder
            script.save_config()
        except Exception:
            logger.debug(traceback.format_exc())
    return window.result


# ------------------------------------------------------------ transactions ---

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


# ---------------------------------------------------------------- placing ---

def type_name(symbol):
    p = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    return p.AsString() if p else str(symbol.Id)


def load_family(path):
    """Load (overwriting) and return the Family, or raise."""
    box = clr.StrongBox[DB.Family]()

    def action():
        doc.LoadFamily(path, OverwriteLoadOptions(), box)

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
    keys = sorted(by_name.keys(), key=lambda k: by_name[k].Elevation)
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

    path = choose_family_file()
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
