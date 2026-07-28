' SAA Alpha Ops Assistant - double-click daily launcher
' Starts UI with CMD minimized, then opens the browser.
Option Explicit

Dim sh, fso, root, bat, url
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
bat = root & "\run_ui_direct.bat"
url = "http://localhost:8501"

If Not fso.FileExists(bat) Then
  MsgBox "Missing run_ui_direct.bat in:" & vbCrLf & root, vbCritical, "SAA Ops Assistant"
  WScript.Quit 1
End If

' 7 = minimized window, False = do not wait
sh.CurrentDirectory = root
sh.Run """" & bat & """", 7, False

' Give Streamlit a moment, then open browser (Streamlit may also open one)
WScript.Sleep 3500
sh.Run url, 1, False
