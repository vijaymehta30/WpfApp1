import clr
import os

dll_path = os.path.join(
    os.path.dirname(__file__),
    "ClassLibrary1.dll"
)

clr.AddReferenceToFileAndPath(dll_path)

from ClassLibrary1 import Class1

window = Class1()
window.ShowPreview()
