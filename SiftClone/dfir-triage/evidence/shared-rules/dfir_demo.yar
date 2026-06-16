rule Suspicious_PowerShell_Encoded_Command
{
    meta:
        description = "Demo rule for encoded PowerShell command indicators"
    strings:
        $ps1 = "powershell" nocase
        $enc1 = "-enc" nocase
        $enc2 = "-encodedcommand" nocase
        $hidden = "-w hidden" nocase
    condition:
        $ps1 and any of ($enc*) or ($ps1 and $hidden)
}

rule Suspicious_Temp_Executable_Strings
{
    meta:
        description = "Demo rule for temp-path execution strings"
    strings:
        $temp1 = "\\Windows\\Temp\\" nocase
        $temp2 = "/Windows/Temp/" nocase
        $exe = ".exe" nocase
    condition:
        any of ($temp*) and $exe
}
