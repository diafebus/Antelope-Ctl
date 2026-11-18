"""Offline cache invalidation checks for the pure PowerShell preflight helpers.

PowerShell hosts execute the actual helper definitions, without UI assemblies,
VM access or device commands. Linux-only source checks cover integration until
these same tests run on the Windows capture host.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/windows/Run-AfxCapture.ps1'
POWERSHELL = shutil.which('pwsh') or shutil.which('powershell.exe')
FILES = ('Run-AfxCapture.ps1', 'Inspect-AfxPanel.ps1', 'Run-AfxScan.ps1',
         'afx-scan-plans.json', 'afx-capture-workflows.json', 'afx-dropdown-options.json')


class PreflightCacheIntegrationTests(unittest.TestCase):
    def test_cache_cannot_bypass_explicit_validation_or_new_gesture_guards(self):
        source = SOURCE.read_text()
        validation, capture = source.split("$results = Join-Path $PSScriptRoot 'results'", 1)
        self.assertIn('if ($ValidateOnly)', validation)
        self.assertNotIn('Test-AfxPreflightCache $cache', validation)
        self.assertIn('Test-AfxPreflightCache $cache $currentHashes $context', capture)
        self.assertIn('Test-AfxPreflightCache $cache (Get-AfxKitHashes)', capture)
        for path in ('Run-AfxScan.ps1', 'Inspect-AfxPanel.ps1'):
            self.assertIn(path, capture)
        self.assertIn('Test-AfxKitHashes $initialObject $hashes', validation)

    def test_prepared_mode_requires_explicit_reviewed_plan_and_forwards_guards(self):
        source = SOURCE.read_text()
        self.assertIn('[switch]$Prepared', source)
        self.assertIn('if ($Prepared -and ($ValidateOnly -or', source)
        self.assertIn('[string]::IsNullOrWhiteSpace($PluginName)', source)
        self.assertIn('[string]::IsNullOrWhiteSpace($CapturePlan)', source)
        self.assertIn("if ($Prepared) { throw 'Prepared capture cannot resume", source)
        self.assertIn('$selectedPlans[0].effect_id -cne $matches[0].effect_id', source)
        self.assertIn('-PlanId $matches[0].range_plan -Prepared:$Prepared', source)
        self.assertIn("$matches[0].next_step -eq 'review'", source)
        self.assertIn('No automatic rescan.', source)

    def test_cache_publication_never_truncates_existing_destination(self):
        helper = SOURCE.read_text().split('function Write-AfxPreflightReport', 1)[1].split('if ($ValidateOnly)', 1)[0]
        self.assertIn('[System.IO.File]::Replace($temporary, $full, [NullString]::Value)', helper)
        self.assertIn('[System.IO.File]::Move($temporary, $full)', helper)
        self.assertNotIn('Set-Content', helper)
        self.assertNotIn('Remove-Item', helper)


@unittest.skipUnless(POWERSHELL, 'PowerShell is not installed; run on the Windows capture host')
class PreflightCacheRuntimeTests(unittest.TestCase):
    def execute(self, assertions):
        helpers = SOURCE.read_text().split('if ($ValidateOnly)', 1)[0]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in FILES:
                (root / name).write_text('original ' + name)
            fixture = r'''
$hashes = Get-AfxKitHashes $PSScriptRoot
$context = Get-AfxPreflightContext
$cache = Join-Path $PSScriptRoot 'cache.json'
$report = @{
 cache_schema=1; status='ok'; validation_complete=$true; settings_written=$false;
 validation_context=$context; hashes=$hashes;
 drag_axis_checks='metadata, direction and native geometry passed';
 control_bounds_checks='fixed anchor and metadata passed'
}
Write-AfxPreflightReport $cache $report
function Assert-Cache([bool]$Expected, [string]$Why) {
 $actual = Test-AfxPreflightCache $cache (Get-AfxKitHashes $PSScriptRoot) $context
 if ($actual -ne $Expected) { throw $Why }
}
Assert-Cache $true 'Fresh matching cache rejected'
'''
            script = root / 'test.ps1'
            script.write_text(helpers + fixture + assertions + "\nWrite-Output 'PASS'\n")
            result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive',
                                     '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS', result.stdout)

    def test_every_source_and_plan_change_invalidates(self):
        self.execute(r'''
foreach ($file in $script:AfxPreflightFiles) {
 $path=Join-Path $PSScriptRoot $file
 $before=[System.IO.File]::ReadAllText($path)
 [System.IO.File]::WriteAllText($path, 'modified')
 Assert-Cache $false ('Changed dependency accepted: '+$file)
 [System.IO.File]::WriteAllText($path,$before)
 Assert-Cache $true ('Restored identical dependency rejected: '+$file)
}
''')

    def test_truncated_failed_and_incomplete_reports_are_misses(self):
        self.execute(r'''
[System.IO.File]::WriteAllText($cache,'{"status":')
Assert-Cache $false 'Truncated JSON accepted'
foreach ($key in @('hashes','validation_complete','validation_context','cache_schema')) {
 $broken=$report.Clone();$broken.Remove($key)
 Write-AfxPreflightReport $cache $broken
 Assert-Cache $false ('Incomplete report accepted: '+$key)
}
foreach ($key in @('status','settings_written','validation_complete')) {
 $broken=$report.Clone();$broken[$key]=@('ok','false','true')
 Write-AfxPreflightReport $cache $broken
 Assert-Cache $false ('Invalid field type accepted: '+$key)
}
$broken=$report.Clone();$broken.status='failed'
Write-AfxPreflightReport $cache $broken
Assert-Cache $false 'Failed validation accepted'
''')

    def test_hash_set_and_runtime_context_must_match(self):
        self.execute(r'''
$broken=$report.Clone();$broken.hashes=$hashes.Clone();$broken.hashes.Remove('Run-AfxScan.ps1')
Write-AfxPreflightReport $cache $broken
Assert-Cache $false 'Missing tool hash accepted'
$broken=$report.Clone();$broken.hashes=$hashes.Clone();$broken.hashes['unexpected.ps1']='A'*64
Write-AfxPreflightReport $cache $broken
Assert-Cache $false 'Additional dependency accepted'
$broken=$report.Clone();$broken.validation_context='another host/runtime'
Write-AfxPreflightReport $cache $broken
Assert-Cache $false 'Different runtime accepted'
''')

    def test_atomic_replacement_remains_valid_and_cleans_temporary_files(self):
        self.execute(r'''
Write-AfxPreflightReport $cache $report
Assert-Cache $true 'Replaced cache rejected'
if (@(Get-ChildItem $PSScriptRoot -Filter 'cache.json.*.tmp').Count -ne 0) {
 throw 'Temporary cache files left behind'
}
''')


if __name__ == '__main__':
    unittest.main()
