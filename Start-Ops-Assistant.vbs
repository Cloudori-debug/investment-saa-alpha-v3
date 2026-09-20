' SAA Alpha Ops Assistant - double-click daily launcher
' Starts UI (minimized), waits until port 8501 is listening, then opens browser.
' Do not HTTP-probe localhost: Windows may SYN_SENT-hang on IPv6 ::1 and even 127.0.0.1:8501.
Option Explicit

Dim sh, fso, root, bat, url, i, ok
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
bat = root & "\run_ui_direct.bat"
url = "http://127.0.0.1:8501"

If Not fso.FileExists(bat) Then
  MsgBox "Missing run_ui_direct.bat in:" & vbCrLf & root, vbCritical, "Alpha Screener"
  WScript.Quit 1
End If

sh.CurrentDirectory = root
' start /min detaches so this VBS never waits on the UI console
sh.Run "cmd.exe /c start /min """" """ & bat & """", 0, False

ok = False
For i = 1 To 60
  WScript.Sleep 1500
  If PortListening(8501) Then
    ok = True
    Exit For
  End If
Next

If ok Then
  sh.Run url, 1, False
Else
  MsgBox "UI did not start within 90 seconds." & vbCrLf & vbCrLf & _
    "Check the minimized 'KOSPI Alpha Screener UI [v3]' window," & vbCrLf & _
    "or run run_ui_direct.bat directly to see the error." & vbCrLf & vbCrLf & _
    "Folder:" & vbCrLf & root, vbExclamation, "Alpha Screener"
End If

Function PortListening(port)
  On Error Resume Next
  Dim rc
  rc = sh.Run( _
    "cmd.exe /c netstat -ano | findstr /C:""LISTENING"" | findstr /C:"":" & port & " """, _
    0, True)
  PortListening = (rc = 0)
  On Error GoTo 0
End Function
