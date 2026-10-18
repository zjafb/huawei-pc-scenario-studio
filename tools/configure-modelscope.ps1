$ErrorActionPreference = 'Stop'

Write-Host 'Open https://modelscope.cn/my/myaccesstoken and copy your ModelScope Access Token.'
Write-Host 'Paste it at the prompt below. Input is hidden; nothing will be printed.'
$modelscopeSecureToken = Read-Host 'ModelScope Access Token' -AsSecureString
$modelscopePointer = [IntPtr]::Zero
try {
    $modelscopePointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($modelscopeSecureToken)
    $modelscopeTokenValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($modelscopePointer).Trim()
    if ([string]::IsNullOrWhiteSpace($modelscopeTokenValue) -or $modelscopeTokenValue -match '\s') {
        throw 'The token is empty or contains whitespace. Copy the complete token and try again.'
    }
    $modelscopeConfigDir = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.config\modelscope'
    [IO.Directory]::CreateDirectory($modelscopeConfigDir) | Out-Null
    [IO.File]::WriteAllText((Join-Path $modelscopeConfigDir 'api_key'), $modelscopeTokenValue, [Text.UTF8Encoding]::new($false))
    $env:MODELSCOPE_API_KEY = $modelscopeTokenValue
    Write-Host 'Saved to your local user configuration, outside the project. Token value is hidden.'
    Write-Host 'Configuration saved only; API availability and model quota still need verification.'
} finally {
    $modelscopeTokenValue = $null
    if ($modelscopePointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($modelscopePointer)
    }
    if ($null -ne $modelscopeSecureToken) { $modelscopeSecureToken.Dispose() }
}
