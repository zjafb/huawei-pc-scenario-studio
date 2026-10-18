$ErrorActionPreference = 'Stop'

Write-Host 'Open https://ima.qq.com/agent-interface in the account that joined the shared knowledge base.'
Write-Host 'Enter the current Client ID and API Key below. Both inputs are hidden.'
$imaConfigDirectory = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.config\ima'
[IO.Directory]::CreateDirectory($imaConfigDirectory) | Out-Null
$imaNewValues = @{}
try {
    foreach ($imaField in @('client_id', 'api_key')) {
        $imaHidden = Read-Host $imaField -AsSecureString
        $imaPointer = [IntPtr]::Zero
        try {
            $imaPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($imaHidden)
            $imaEntered = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($imaPointer).Trim()
            if ([string]::IsNullOrWhiteSpace($imaEntered) -or $imaEntered -match '\s') {
                throw 'An input is empty or contains whitespace. No configuration was updated.'
            }
            $imaNewValues[$imaField] = $imaEntered
        } finally {
            $imaEntered = $null
            if ($imaPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($imaPointer) }
            if ($null -ne $imaHidden) { $imaHidden.Dispose() }
        }
    }
    $imaModelscopePath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.config\modelscope\api_key'
    if ([IO.File]::Exists($imaModelscopePath)) {
        $imaOtherServiceToken = [IO.File]::ReadAllText($imaModelscopePath).Trim()
        if ($imaNewValues['api_key'] -eq $imaOtherServiceToken) {
            throw 'This is the ModelScope token. Use the IMA API Key from https://ima.qq.com/agent-interface instead. Nothing was updated.'
        }
        $imaOtherServiceToken = $null
    }
    foreach ($imaField in @('client_id', 'api_key')) {
        [IO.File]::WriteAllText((Join-Path $imaConfigDirectory $imaField), $imaNewValues[$imaField], [Text.UTF8Encoding]::new($false))
    }
    Write-Host 'Saved outside the project. Values are hidden. Authentication still needs a read-only check.'
} finally {
    $imaOtherServiceToken = $null
    $imaNewValues.Clear()
}
