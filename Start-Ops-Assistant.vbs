' SAA Alpha Ops Assistant - double-click daily launcher
' Starts UI (minimized), waits until http://localhost:8501 is up, then opens browser.
Option Explicit

Dim sh, fso, root, bat, url, i, ok
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

' Poll until Streamlit answers (up to ~90s) — fixed Sleep often opens browser too early
ok = False
For i = 1 To 60
  WScript.Sleep 1500
  If HttpOk(url) Then
    ok = True
    Exit For
  End If
Next

If ok Then
  sh.Run url, 1, False
Else
  ' Show the console so the user can see Python/streamlit errors
  MsgBox "UI did not start within 90 seconds." & vbCrLf & vbCrLf & _
    "Check the minimized 'SAA Alpha Ops Assistant UI [v3]' window," & vbCrLf & _
    "or run run_ui_direct.bat directly to see the error." & vbCrLf & vbCrLf & _
    "Folder:" & vbCrLf & root, vbExclamation, "SAA Ops Assistant"
End If

Function HttpOk(u)
  On Error Resume Next
  Dim xhr
  Set xhr = CreateObject("MSXML2.XMLHTTP")
  If Err.Number <> 0 Then
    Err.Clear
    Set xhr = CreateObject("Microsoft.XMLHTTP")
  End If
  If xhr Is Nothing Then
    HttpOk = False
    Exit Function
  End If
  xhr.Open "GET", u, False
  xhr.setRequestHeader "Cache-Control", "no-cache"
  xhr.Send
  If Err.Number <> 0 Then
    HttpOk = False
    Err.Clear
  Else
    HttpOk = (xhr.Status >= 200 And xhr.Status < 500)
  End If
  Set xhr = Nothing
  On Error GoTo 0
End Function
