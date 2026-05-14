$dir = "C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt"
$files = Get-ChildItem $dir -Filter "*.html"

foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8
    
    # Fix canonical i og: URLs
    $content = $content -replace 'https://shortsyt\.pl', 'https://shortsyt.salon-prettywoman.pl'
    
    # Fix Agency FAQ - usun wzmiankę o umowie 3 mies.
    $content = $content -replace 'Pakiet Agency wymaga umowy na 3 miesiące\.', 'Wszystkie pakiety działają bez długoterminowych umów — możesz zakończyć współpracę z miesięcznym wyprzedzeniem.'
    
    Set-Content $f.FullName -Value $content -Encoding UTF8 -NoNewline
    Write-Host "Fixed: $($f.Name)"
}

Write-Host ""
Write-Host "Weryfikacja canonical w index.html:"
$check = Get-Content "$dir\index.html" -Raw
if ($check -match 'canonical.*shortsyt\.salon-prettywoman\.pl') {
    Write-Host "  [OK] Canonical URL poprawny" -ForegroundColor Green
} else {
    Write-Host "  [ERR] Canonical URL nadal bledny" -ForegroundColor Red
}

Write-Host "Weryfikacja emaila:"
if ($check -match 'mz10062001@gmail\.com') {
    Write-Host "  [OK] Email poprawny" -ForegroundColor Green
} else {
    Write-Host "  [ERR] Email nie znaleziony" -ForegroundColor Red
}
