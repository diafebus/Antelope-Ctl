# Reusable GUI knob, binary switch and finite selector capture from reviewed plans.
param([string]$PlanId = '', [string]$DiscoveryDirectory = '',
      [string]$ResumeDirectory = '', [switch]$ResumeReviewed, [switch]$Prepared,
      [switch]$ValidatePlanOnly, [string]$CancellationPath = '', [long]$DeadlineEpoch = 0)
$ErrorActionPreference = 'Stop'
function Assert-CaptureActive {
    if(($CancellationPath -and (Test-Path -LiteralPath $CancellationPath)) -or
       ($DeadlineEpoch -gt 0 -and [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge $DeadlineEpoch)) {
        throw 'Capture cancelled or command deadline reached; no further gesture'
    }
}
$script:captureBudget = $null
$results = Join-Path $PSScriptRoot 'results'
New-Item -ItemType Directory -Path $results -Force | Out-Null
$launchLog = Join-Path $results ('AFX-scan-launch-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.log')
Start-Transcript -Path $launchLog | Out-Null
try {
$planData = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-scan-plans.json') | ConvertFrom-Json
$plans = $planData.plans
$wheelPolicy = $planData.wheel_policy
if (-not [string]::IsNullOrWhiteSpace($DiscoveryDirectory)) {
    $plans = @((Get-Content -Raw (Join-Path $DiscoveryDirectory 'generated-plan.json') | ConvertFrom-Json))
    $PlanId = $plans[0].id
}
if (-not [string]::IsNullOrWhiteSpace($ResumeDirectory)) {
    if (-not $ResumeReviewed -or -not [string]::IsNullOrWhiteSpace($DiscoveryDirectory)) {
        throw 'Resume requires explicit current-state review and cannot combine with discovery.'
    }
    $plans = @((Get-Content -Raw (Join-Path $ResumeDirectory 'remaining-plan.json') | ConvertFrom-Json))
    $PlanId = $plans[0].id
}
if ([string]::IsNullOrWhiteSpace($PlanId)) {
    Write-Host 'Available reviewed control plans:'
    foreach ($candidate in $plans) {
        Write-Host "$($candidate.id): $($candidate.panel), $($candidate.controls.Count) control(s), AFX $($candidate.channel)"
    }
    $PlanId = Read-Host 'Enter the plan ID to scan (for example instinct-filters)'
}
$matchingPlans = @($plans | Where-Object { $_.id -eq $PlanId })
if ($matchingPlans.Count -ne 1) { throw 'Choose one of the listed reviewed plans.' }
$plan = $matchingPlans[0]
if (@($plan.controls | Where-Object { $_.kind -eq 'wheel_button' }).Count -gt 0) {
    $plan | Add-Member -NotePropertyName wheel_policy -NotePropertyValue $wheelPolicy -Force
}
$dropdownData = Get-Content -Raw (Join-Path $PSScriptRoot 'afx-dropdown-options.json') | ConvertFrom-Json
foreach ($keyControl in @($plan.controls | Where-Object { $_.kind -eq 'key_button' })) {
    $definitions = @($dropdownData.plugins | Where-Object { $_.effect_id -eq $plan.effect_id })
    if ($definitions.Count -ne 1 -or $definitions[0].hardware_testing -eq 'excluded') {
        throw 'Key trial plugin is missing or excluded in the dropdown registry.'
    }
    $dropdowns = @($definitions[0].dropdowns | Where-Object { $_.id -eq $keyControl.dropdown_id })
    if ($dropdowns.Count -ne 1 -or $dropdowns[0].class_name -cne $keyControl.class_name -or
        $dropdowns[0].selection_policy -ne 'reviewed-parameter-trial' -or
        $dropdowns[0].ordering -notin @('capture-observed', 'manual-listed')) {
        throw 'Key target needs a measured GUI class and known ordered choices.'
    }
    $labels = @($dropdowns[0].options | ForEach-Object { $_.label })
    if ($labels.Count -lt 2 -or $labels.Count -gt 8 -or
        @($labels | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -ne 0 -or
        @($labels | Select-Object -Unique).Count -ne $labels.Count -or
        $keyControl.activation -ne 'click_open_click_close') { throw 'Key activation/options are invalid.' }
    $keyControl | Add-Member -NotePropertyName option_names -NotePropertyValue $labels -Force
    $keyControl | Add-Member -NotePropertyName positions -NotePropertyValue $labels.Count -Force
}
$controlLimit = 3
if (@($plan.controls | Where-Object { $_.kind -eq 'knob_range' }).Count -gt 0) { $controlLimit = 24 }
if ($ResumeReviewed -and -not [string]::IsNullOrWhiteSpace($ResumeDirectory)) { $controlLimit = 24 }
if (@($plan.controls).Count -lt 1 -or @($plan.controls).Count -gt $controlLimit -or
    @($plan.controls | Where-Object { $_.kind -notin @('binary_button', 'knob_range', 'selector_cycle', 'selector_positions', 'wheel_button', 'menu_positions', 'key_button') }).Count -ne 0) {
    throw 'Choose a reviewed button or knob range plan.'
}
function Get-PlanDragPoint($Definition) {
    if ($Definition.PSObject.Properties.Name -notcontains 'drag_point') {
        return @{x=0.5;y=0.5}
    }
    $point = $Definition.drag_point
    if ($Definition.kind -ne 'knob_range' -or $null -eq $point -or
        $point -isnot [System.Management.Automation.PSCustomObject]) { throw 'Invalid reviewed knob drag point.' }
    $names = @($point.PSObject.Properties.Name)
    if ($names.Count -ne 2 -or 'x' -notin $names -or 'y' -notin $names) { throw 'Drag point requires exactly x/y.' }
    foreach ($name in @('x','y')) {
        $value = $point.$name
        if (($value -isnot [int] -and $value -isnot [long] -and $value -isnot [double] -and $value -isnot [decimal]) -or
            [double]::IsNaN([double]$value) -or [double]::IsInfinity([double]$value) -or
            [double]$value -le 0 -or [double]$value -ge 1) { throw 'Drag point must stay strictly inside its control.' }
    }
    return @{x=[double]$point.x;y=[double]$point.y}
}
function Get-PlanOverflow($Definition) {
    if ($Definition.PSObject.Properties.Name -notcontains 'panel_overflow_px') { return $null }
    $margin = $Definition.panel_overflow_px
    $sslUpper = $plan.panel_class -ceq 'Ssl4kBus' -and $plan.effect_id -ceq 'ssl4kbus' -and
        $Definition.class_name -cin @('Ssl4kBusPotThreshold','Ssl4kBusPotShortRunRate',
            'Ssl4kBusPotShortRunScFilter','Ssl4kBusAttackPot','Ssl4kBusRatioPotNoInherit') -and $margin -eq 19
    if ($Definition.kind -ne 'knob_range' -or $margin -isnot [int] -or $margin -lt 1 -or
        ($margin -gt 14 -and -not $sslUpper)) {
        throw 'Invalid reviewed knob overflow allowance.'
    }
    return $margin
}
function Get-PlanDragAxis($Definition) {
    if ($Definition.PSObject.Properties.Name -notcontains 'drag_axis') { return 'vertical' }
    $axis = $Definition.drag_axis
    if ($Definition.kind -cne 'knob_range' -or $axis -isnot [string] -or
        $axis -cnotin @('vertical','horizontal')) { throw 'Invalid reviewed knob drag axis.' }
    return $axis
}
function Get-PlanSweepDelta($Definition, [int]$Delta) {
    # Endpoint logic uses positive for minimum: down vertically, left horizontally.
    if ((Get-PlanDragAxis $Definition) -ceq 'horizontal') { return -$Delta }
    return $Delta
}
function Get-PlanBoundsShiftX($Definition) {
    if ($Definition.PSObject.Properties.Name -notcontains 'bounds_shift_x_px') { return 0 }
    $shift = $Definition.bounds_shift_x_px
    if ($Definition.kind -cne 'knob_range' -or (Get-PlanDragAxis $Definition) -cne 'horizontal' -or
        $shift -isnot [int] -or $shift -notin @(0,1)) { throw 'Invalid horizontal knob bounds shift.' }
    return $shift
}
foreach ($definition in $plan.controls) {
    $null = Get-PlanDragPoint $definition
    $null = Get-PlanOverflow $definition
    $null = Get-PlanDragAxis $definition
    $null = Get-PlanBoundsShiftX $definition
}
if ($ValidatePlanOnly) {
    # Used by Windows preflight to exercise real metadata loading without
    # loading UIA, calling user32, starting a recorder or moving any control.
    $plan | ConvertTo-Json -Depth 16
    return
}
$panelLabel = $plan.panel -replace '[^a-zA-Z0-9_-]', '_'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -ReferencedAssemblies 'System.Drawing.dll' -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Threading;
public static class AfxScanInput {
    public static string CaptureCancellationPath;
    public static long CaptureDeadlineEpoch;
    public static void CheckCancellation() {
        if ((!String.IsNullOrEmpty(CaptureCancellationPath) && System.IO.File.Exists(CaptureCancellationPath)) ||
            (CaptureDeadlineEpoch > 0 && DateTimeOffset.UtcNow.ToUnixTimeSeconds() >= CaptureDeadlineEpoch))
            throw new Exception("Capture cancelled or command deadline reached.");
    }
    public static void ValidateCancellationGuards() {
        string oldPath=CaptureCancellationPath, temporary=null;
        long oldDeadline=CaptureDeadlineEpoch;
        try {
            CaptureCancellationPath=null; CaptureDeadlineEpoch=1;
            bool rejected=false; try { CheckCancellation(); } catch { rejected=true; }
            if (!rejected) throw new Exception("Expired gesture deadline accepted.");
            CaptureDeadlineEpoch=0; temporary=System.IO.Path.GetTempFileName();
            CaptureCancellationPath=temporary;
            rejected=false; try { CheckCancellation(); } catch { rejected=true; }
            if (!rejected) throw new Exception("Cancelled gesture accepted.");
            CaptureCancellationPath=null; CheckCancellation();
        } finally {
            if (temporary!=null) System.IO.File.Delete(temporary);
            CaptureCancellationPath=oldPath; CaptureDeadlineEpoch=oldDeadline;
        }
    }
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
    [StructLayout(LayoutKind.Sequential)] public struct WindowRect {
        public int left, top, right, bottom;
    }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window, out WindowRect rect);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint owner);
    private delegate bool WindowVisitor(IntPtr window, IntPtr argument);
    [DllImport("user32.dll")] private static extern bool EnumWindows(WindowVisitor visitor, IntPtr argument);
    public static IntPtr[] NativeVisibleWindows(uint owner) {
        var windows = new System.Collections.Generic.List<IntPtr>();
        EnumWindows(delegate(IntPtr window, IntPtr argument) {
            uint actualOwner;
            GetWindowThreadProcessId(window, out actualOwner);
            if (actualOwner == owner && IsWindowVisible(window)) windows.Add(window);
            return true;
        }, IntPtr.Zero);
        return windows.ToArray();
    }
    public static bool IsDropdownPopup(Rectangle rect, Rectangle button, long candidate,
        long panel, uint owner, uint expectedOwner, bool visible, string accessibilityClass) {
        return accessibilityClass == "QComboBoxPrivateContainer" &&
            visible && candidate != 0 && candidate != panel && owner == expectedOwner &&
            rect.Width > 0 && rect.Height > 0 && rect.Width <= 464 && rect.Height <= 704 &&
            Math.Abs(rect.Left - button.Left) <= 32 &&
            Math.Min(Math.Abs(rect.Top - button.Bottom), Math.Abs(rect.Bottom - button.Top)) <= 32;
    }
    [DllImport("user32.dll")] private static extern IntPtr WindowFromPoint(Point point);
    [DllImport("user32.dll")] private static extern bool IsChild(IntPtr parent, IntPtr child);
    public static bool PointOwnedByWindow(Point point, IntPtr window) {
        IntPtr hit = WindowFromPoint(point);
        return hit == window || IsChild(window, hit);
    }
    public static Point ResolveKnobPoint(Rectangle control, Rectangle panel,
        Rectangle window, Rectangle screen, double x, double y) {
        return ResolveKnobPoint(control,panel,window,screen,x,y,false);
    }
    public static Point ResolveKnobPoint(Rectangle control, Rectangle panel,
        Rectangle window, Rectangle screen, double x, double y, bool horizontal) {
        if (Double.IsNaN(x) || Double.IsInfinity(x) || Double.IsNaN(y) || Double.IsInfinity(y) ||
            x <= 0 || x >= 1 || y <= 0 || y >= 1 || control.Width <= 0 || control.Height <= 0)
            throw new Exception("Invalid reviewed knob point.");
        Point point = new Point((int)Math.Round(control.X + control.Width*x),
            (int)Math.Round(control.Y + control.Height*y));
        Rectangle safe = new Rectangle(point.X-8, point.Y-8, 16, 16);
        int position = horizontal ? point.X : point.Y;
        int first = horizontal ? screen.Left : screen.Top;
        int last = horizontal ? screen.Right : screen.Bottom;
        if (!control.Contains(safe) || !panel.Contains(safe) || !window.Contains(safe) ||
            !screen.Contains(safe) || position-first < 24 || last-position < 24)
            throw new Exception("Knob point lacks safe visible drag room.");
        return point;
    }
    public static void ValidateKnobPoints() {
        Rectangle control = new Rectangle(1224,208,119,119);
        Rectangle panel = new Rectangle(957,158,908,215);
        Rectangle window = new Rectangle(680,123,1190,472);
        Rectangle screen = new Rectangle(0,0,1920,1080);
        Point center = ResolveKnobPoint(control,panel,window,screen,.5,.5);
        Point outer = ResolveKnobPoint(control,panel,window,screen,.86,.5);
        if (center != new Point(1284,268) || outer != new Point(1326,268))
            throw new Exception("Reviewed knob point fixtures failed.");
        foreach (double invalid in new double[] {0,1,Double.NaN,Double.PositiveInfinity,.99}) {
            bool rejected = false;
            try { ResolveKnobPoint(control,panel,window,screen,invalid,.5); } catch { rejected=true; }
            if (!rejected) throw new Exception("Unsafe knob point accepted.");
        }
        bool roomRejected=false;
        try { ResolveKnobPoint(new Rectangle(1200,1000,119,119),new Rectangle(0,0,1920,1200),
            new Rectangle(0,0,1920,1200),screen,.5,.5); } catch { roomRejected=true; }
        if (!roomRejected) throw new Exception("Insufficient resolved drag room accepted.");
        Rectangle edgeControl = new Rectangle(90,1060,60,20);
        Rectangle fullScreen = new Rectangle(0,0,1920,1080);
        Point horizontal = ResolveKnobPoint(edgeControl,fullScreen,fullScreen,fullScreen,.5,.5,true);
        if (horizontal != new Point(120,1070)) throw new Exception("Horizontal point fixture failed.");
        bool horizontalRoomRejected=false;
        try { ResolveKnobPoint(new Rectangle(0,100,20,20),fullScreen,fullScreen,fullScreen,.5,.5,true); }
        catch { horizontalRoomRejected=true; }
        if (!horizontalRoomRejected) throw new Exception("Insufficient horizontal drag room accepted.");
    }
    public static bool ControlBoundsMatch(Rectangle anchor, Rectangle current, Point start, int shiftX) {
        Rectangle safe = new Rectangle(start.X-8,start.Y-8,16,16);
        return (shiftX == 0 || shiftX == 1) && anchor.Width > 0 && anchor.Height > 0 &&
            current.Y == anchor.Y && current.Width == anchor.Width && current.Height == anchor.Height &&
            Math.Abs(current.X-anchor.X) <= shiftX && anchor.Contains(safe) && current.Contains(safe);
    }
    public static void ValidateControlBounds() {
        Rectangle anchor = new Rectangle(957,393,60,20);
        Point start = new Point(987,403);
        if (!ControlBoundsMatch(anchor,anchor,start,0) ||
            !ControlBoundsMatch(anchor,new Rectangle(958,393,60,20),start,1) ||
            !ControlBoundsMatch(anchor,new Rectangle(956,393,60,20),start,1) ||
            ControlBoundsMatch(anchor,new Rectangle(958,393,60,20),start,0) ||
            ControlBoundsMatch(anchor,new Rectangle(959,393,60,20),start,1) ||
            ControlBoundsMatch(anchor,new Rectangle(957,394,60,20),start,1) ||
            ControlBoundsMatch(anchor,new Rectangle(957,393,61,20),start,1) ||
            ControlBoundsMatch(anchor,new Rectangle(957,393,60,21),start,1) ||
            ControlBoundsMatch(anchor,anchor,new Point(958,403),1) ||
            ControlBoundsMatch(anchor,anchor,start,2))
            throw new Exception("Anchored control bounds fixtures failed.");
    }
    public static void ValidateDropdownClassifier() {
        Rectangle button = new Rectangle(100, 100, 127, 11);
        Rectangle popup = new Rectangle(100, 110, 127, 56);
        Rectangle host = new Rectangle(0, 0, 1380, 853);
        if (!IsDropdownPopup(popup, button, 2, 1, 7, 7, true, "QComboBoxPrivateContainer") ||
            IsDropdownPopup(popup, button, 2, 1, 7, 7, false, "QComboBoxPrivateContainer") ||
            IsDropdownPopup(host, button, 3, 1, 7, 7, true, "QComboBoxPrivateContainer") ||
            IsDropdownPopup(popup, button, 1, 1, 7, 7, true, "QComboBoxPrivateContainer") ||
            IsDropdownPopup(popup, button, 2, 1, 8, 7, true, "QComboBoxPrivateContainer") ||
            IsDropdownPopup(popup, button, 2, 1, 7, 7, true, "SysShadow") ||
            IsDropdownPopup(popup, button, 2, 1, 7, 7, true, "QTipLabel"))
            throw new Exception("Native dropdown state fixtures failed.");
    }
    [StructLayout(LayoutKind.Sequential)] public struct Mouse {
        public int dx, dy;
        public uint data, flags, time;
        public UIntPtr extra;
    }
    [StructLayout(LayoutKind.Sequential)] public struct Keyboard {
        public ushort key, scan;
        public uint flags, time;
        public UIntPtr extra;
    }
    [StructLayout(LayoutKind.Explicit)] public struct Payload {
        [FieldOffset(0)] public Mouse mouse;
        [FieldOffset(0)] public Keyboard keyboard;
    }
    [StructLayout(LayoutKind.Sequential)] public struct Input {
        public uint type;
        public Payload payload;
    }
    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint SendInput(uint count, Input[] inputs, int size);
    public static void Click() {
        Input[] inputs = new Input[2];
        inputs[0].payload.mouse.flags = 2;
        inputs[1].payload.mouse.flags = 4;
        if (SendInput(2, inputs, Marshal.SizeOf(typeof(Input))) != 2) {
            try { Held(false); } finally {
                throw new Exception("Mouse injection failed; release attempted, no retry permitted.");
            }
        }
    }
    public static void Wheel(int delta) {
        if (delta == 0 || Math.Abs(delta) > 30) throw new Exception("Only a bounded partial wheel notch is allowed.");
        Input[] inputs = new Input[1];
        inputs[0].payload.mouse.flags = 0x0800;
        inputs[0].payload.mouse.data = unchecked((uint)delta);
        if (SendInput(1, inputs, Marshal.SizeOf(typeof(Input))) != 1)
            throw new Exception("Wheel injection failed; no retry permitted.");
    }
    public static void Held(bool down) {
        Input[] inputs = new Input[1];
        inputs[0].payload.mouse.flags = down ? 2u : 4u;
        if (SendInput(1, inputs, Marshal.SizeOf(typeof(Input))) != 1)
            throw new Exception("Mouse button injection failed.");
    }
    public static void PageKey(int key, IntPtr window) {
        if (key != 0x21 && key != 0x22) throw new Exception("Only Page Up/Down are permitted.");
        if (GetForegroundWindow() != window || GetAsyncKeyState(27) < 0 ||
            GetAsyncKeyState(0x21) < 0 || GetAsyncKeyState(0x22) < 0 ||
            GetAsyncKeyState(0x10) < 0 || GetAsyncKeyState(0x11) < 0 || GetAsyncKeyState(0x12) < 0)
            throw new Exception("Focus changed or a navigation/modifier key is held; no key sent.");
        Input[] inputs = new Input[2];
        inputs[0].type = inputs[1].type = 1;
        inputs[0].payload.keyboard.key = inputs[1].payload.keyboard.key = (ushort)key;
        // These are extended navigation keys. The second event releases it.
        inputs[0].payload.keyboard.flags = 1;
        inputs[1].payload.keyboard.flags = 3;
        if (SendInput(2, inputs, Marshal.SizeOf(typeof(Input))) != 2) {
            Input[] release = new Input[] { inputs[1] };
            SendInput(1, release, Marshal.SizeOf(typeof(Input)));
            throw new Exception("Page key injection failed; release attempted, no retry permitted.");
        }
    }
    public static Point ResolveSweepEnd(Point start, int delta, bool horizontal, Rectangle screen) {
        int first = horizontal ? screen.Left : screen.Top;
        int extent = horizontal ? screen.Width : screen.Height;
        int position = horizontal ? start.X : start.Y;
        if (extent <= 8 || !screen.Contains(start)) throw new Exception("Invalid sweep desktop bounds.");
        int end = Math.Max(first + 4, Math.Min(first + extent - 5, position + delta));
        if (Math.Abs(end-position) < 16) throw new Exception("Insufficient screen room for drag.");
        return horizontal ? new Point(end,start.Y) : new Point(start.X,end);
    }
    public static void ValidateSweepAxes() {
        Rectangle screen = new Rectangle(0,0,1920,1080);
        Point start = new Point(987,403);
        if (ResolveSweepEnd(start,-800,true,screen) != new Point(187,403) ||
            ResolveSweepEnd(start,800,true,screen) != new Point(1787,403) ||
            ResolveSweepEnd(start,800,false,screen) != new Point(987,1075) ||
            ResolveSweepEnd(start,-800,false,screen) != new Point(987,4) ||
            ResolveSweepEnd(new Point(1700,403),800,true,screen) != new Point(1915,403) ||
            ResolveSweepEnd(new Point(-900,400),-800,true,new Rectangle(-1920,-100,1920,1080)) != new Point(-1700,400))
            throw new Exception("Sweep axis or clamping fixtures failed.");
        bool rejected=false;
        try { ResolveSweepEnd(new Point(10,403),-800,true,screen); } catch { rejected=true; }
        if (!rejected) throw new Exception("Insufficient horizontal sweep room accepted.");
    }
    public static void Sweep(int x, int y, int delta, IntPtr window) {
        Sweep(x,y,delta,window,false);
    }
    public static void Sweep(int x, int y, int delta, IntPtr window, bool horizontal) {
        Rectangle screen = new Rectangle(GetSystemMetrics(76),GetSystemMetrics(77),
            GetSystemMetrics(78),GetSystemMetrics(79));
        Point end = ResolveSweepEnd(new Point(x,y),delta,horizontal,screen);
        int distance = horizontal ? end.X-x : end.Y-y;
        int samples = Math.Max(2, (int)Math.Ceiling(Math.Abs(distance) / 4.0));
        try {
            CheckCancellation();
            Held(true);
            Thread.Sleep(100);
            for (int i=1; i<=samples; i++) {
                CheckCancellation();
                if (GetForegroundWindow() != window || GetAsyncKeyState(27) < 0)
                    throw new Exception("Focus changed or Escape pressed during sweep.");
                int movement = (int)Math.Round(distance * (double)i / samples);
                if (!SetCursorPos(horizontal ? x+movement : x, horizontal ? y : y+movement))
                    throw new Exception("Pointer sweep failed.");
                Thread.Sleep(12);
            }
            Thread.Sleep(100);
        } finally { Held(false); }
    }
    public static double Difference(Bitmap a, Bitmap b) {
        if (a.Size != b.Size) return 1;
        int changed = 0;
        for (int y=0; y<a.Height; y++) for (int x=0; x<a.Width; x++) {
            Color p=a.GetPixel(x,y), q=b.GetPixel(x,y);
            if (Math.Abs(p.R-q.R)>20 || Math.Abs(p.G-q.G)>20 || Math.Abs(p.B-q.B)>20) changed++;
        }
        return (double)changed/(a.Width*a.Height);
    }
}
'@
[AfxScanInput]::CaptureCancellationPath=$CancellationPath
[AfxScanInput]::CaptureDeadlineEpoch=$DeadlineEpoch

function Write-Record($Path, $Value) {
    # JSON has no numeric infinity. Preserve the displayed endpoint explicitly
    # as a string instead of PowerShell's nonstandard -Infinity token.
    foreach ($key in @($Value.Keys)) {
        if ($Value[$key] -is [double] -and [double]::IsInfinity($Value[$key])) {
            if ($Value[$key] -lt 0) { $Value[$key] = '-Infinity' } else { $Value[$key] = 'Infinity' }
        }
    }
    $temporary = $Path + '.tmp'
    $Value | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $temporary
    Move-Item -LiteralPath $temporary -Destination $Path
}
function Wait-HostFile($Name, $Seconds) {
    Assert-CaptureActive
    if ($null -ne $script:captureBudget) {
        $Seconds = [Math]::Max($Seconds, [int]$script:captureBudget.feedback_seconds)
    }
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath (Join-Path $job 'host-error.json')) {
            throw (Get-Content -Raw (Join-Path $job 'host-error.json'))
        }
        $path = Join-Path $job $Name
        if (Test-Path -LiteralPath $path) {
            return (Get-Content -Raw -LiteralPath $path | ConvertFrom-Json)
        }
        Assert-CaptureActive
        Start-Sleep -Milliseconds 100
    }
    throw "No host response: $Name. No further clicks will be sent."
}
function Assert-Panel {
    Assert-CaptureActive
    if ([AfxScanInput]::GetAsyncKeyState(27) -lt 0) { throw 'Escape pressed; stopped.' }
    if ([AfxScanInput]::GetForegroundWindow() -ne $handle) { throw 'Panel focus changed; stopped.' }
    $now = $root.Current.BoundingRectangle
    if ($now -ne $windowBounds) { throw 'Panel moved or resized; stopped.' }
    Assert-AfxChannel
    $liveBounds = $button.Current.BoundingRectangle
    if ($liveBounds -ne $buttonBounds) {
        $shift = Get-PlanBoundsShiftX $control
        if ($shift -eq 0) { throw 'Control moved; stopped.' }
        # Keep the original anchor and pointer. Never accumulate a new origin.
        $point = Get-KnobPoint $buttonBounds $control
        $safe = [System.Windows.Rect]::new($point.X-8,$point.Y-8,16,16)
        $anchorRect = [System.Drawing.Rectangle]::new([int]$buttonBounds.X,[int]$buttonBounds.Y,
            [int]$buttonBounds.Width,[int]$buttonBounds.Height)
        $liveRect = [System.Drawing.Rectangle]::new([int]$liveBounds.X,[int]$liveBounds.Y,
            [int]$liveBounds.Width,[int]$liveBounds.Height)
        if ($liveBounds.Y -ne $buttonBounds.Y -or $liveBounds.Width -ne $buttonBounds.Width -or
            $liveBounds.Height -ne $buttonBounds.Height -or [Math]::Abs($liveBounds.X-$buttonBounds.X) -gt $shift -or
            -not $button.Current.IsEnabled -or $button.Current.IsOffscreen -or
            $button.Current.ClassName -cne $control.class_name -or ($button.GetRuntimeId()-join ':') -cne $buttonRuntimeId -or
            -not $liveBounds.Contains($safe) -or -not $windowBounds.Contains($liveBounds) -or
            -not $visible[0].Current.BoundingRectangle.Contains($liveBounds) -or
            -not [AfxScanInput]::ControlBoundsMatch($anchorRect,$liveRect,$point,$shift)) {
            throw 'Control moved outside its measured horizontal allowance; stopped.'
        }
    }
}
function Assert-AfxChannel {
    $tabs = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'AfxTabButton'))
    $selected = @()
    foreach ($tab in $tabs) {
        $pattern = $null
        if ($tab.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern) -and
            $pattern.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On) {
            $selected += $tab.Current.Name.Trim()
        }
    }
    if ($selected.Count -ne 1 -or $selected[0] -ne [string]$plan.channel) {
        throw "Select unlinked AFX channel $($plan.channel) with $($plan.panel) open."
    }
}
function Save-Button($Name) {
    Assert-Panel
    $bitmap = New-Object System.Drawing.Bitmap ([int]$crop.Width), ([int]$crop.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen([int]$crop.X, [int]$crop.Y, 0, 0, $bitmap.Size)
        $bitmap.Save((Join-Path $job $Name), [System.Drawing.Imaging.ImageFormat]::Png)
    } catch { $bitmap.Dispose(); throw }
    finally { $graphics.Dispose() }
    return $bitmap
}

function Assert-MenuOwner([switch]$Discovering) {
    $foregroundHandle = [AfxScanInput]::GetForegroundWindow()
    $foreground = [System.Windows.Automation.AutomationElement]::FromHandle($foregroundHandle)
    if ($null -eq $foreground -or $foreground.Current.ProcessId -ne $root.Current.ProcessId -or
        $root.Current.BoundingRectangle -ne $windowBounds -or
        $button.Current.BoundingRectangle -ne $buttonBounds -or [AfxScanInput]::GetAsyncKeyState(27) -lt 0) {
        throw 'Menu owner, bounds or focus changed; stopped.'
    }
    Assert-AfxChannel
    if (-not $Discovering -and $foregroundHandle -ne $handle -and
        $foregroundHandle.ToInt64() -notin $script:menuPopupHandles) {
        throw 'Foreground is neither the original panel nor its verified menu popup.'
    }
}
function Visible-MenuRows($Windows) {
    $seen = @{}
    $found = @()
    foreach ($window in $Windows) {
        foreach ($node in $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $menuOptionCondition)) {
            $c = $node.Current; $r = $c.BoundingRectangle; $id = $node.GetRuntimeId() -join ':'
            if (-not [AfxScanInput]::IsWindowVisible([IntPtr]::new([long]$window.Current.NativeWindowHandle)) -or
                -not $window.Current.BoundingRectangle.Contains($r) -or $c.ProcessId -ne $root.Current.ProcessId -or $c.IsPassword -or $c.IsOffscreen -or
                -not $c.IsEnabled -or $r.IsEmpty -or $r.Width -le 0 -or $r.Height -le 0 -or
                -not $menuScreen.Contains([System.Drawing.Rectangle]::new([int]$r.X, [int]$r.Y, [int][Math]::Ceiling($r.Width), [int][Math]::Ceiling($r.Height))) -or
                [Math]::Abs($r.X - $buttonBounds.X) -gt 32 -or $r.Width -gt 400 -or $r.Height -gt 80 -or
                -not $menuSearchBounds.Contains($r) -or
                $seen.ContainsKey($id)) { continue }
            $seen[$id] = $true
            if ($found.Count -ge 64) { throw 'Menu item discovery exceeds the bounded tree.' }
            $found += @{ element = $node; id = $id; name = $c.Name; rect = $r }
        }
    }
    return $found
}
function Menu-Windows {
    # Qt can retain rows with IsOffscreen=false after closing a popup. Only
    # currently visible, native ComboBox popup roots establish an open menu.
    $buttonRect = [System.Drawing.Rectangle]::new([int]$buttonBounds.X, [int]$buttonBounds.Y,
        [int][Math]::Ceiling($buttonBounds.Width), [int][Math]::Ceiling($buttonBounds.Height))
    $result = @()
    foreach ($native in [AfxScanInput]::NativeVisibleWindows([uint32]$root.Current.ProcessId)) {
        # Anchor each popup directly: a UIA desktop-scoped proxy can omit
        # owned submenu windows or truncate their accessible descendants.
        $node = [System.Windows.Automation.AutomationElement]::FromHandle($native)
        $nativeRect = [AfxScanInput+WindowRect]::new(); [uint32]$owner = 0
        if ($native -eq [IntPtr]::Zero -or
            [AfxScanInput]::GetWindowThreadProcessId($native, [ref]$owner) -eq 0 -or
            -not [AfxScanInput]::GetWindowRect($native, [ref]$nativeRect)) { continue }
        $rect = [System.Drawing.Rectangle]::FromLTRB($nativeRect.left, $nativeRect.top,
            $nativeRect.right, $nativeRect.bottom)
        if ([AfxScanInput]::IsDropdownPopup($rect, $buttonRect, $native.ToInt64(), $handle.ToInt64(),
            $owner, [uint32]$root.Current.ProcessId, [AfxScanInput]::IsWindowVisible($native),
            $node.Current.ClassName)) { $result += $node }
    }
    return $result
}
function Save-MenuDiscovery([string]$Suffix, [string]$Stage, $Windows, $Rows) {
    # Save before validation so unsupported accessibility leaves useful evidence.
    Write-Record (Join-Path $job ($filePrefix + '-' + $Suffix + '-menu.json')) @{
        stage = $Stage; selected = $menuValue.Current.Value;
        popup_windows = @($Windows | Where-Object { $null -ne $_ } | ForEach-Object {
            $r = $_.Current.BoundingRectangle
            @{ runtime_id = ($_.GetRuntimeId() -join ':'); handle = [long]$_.Current.NativeWindowHandle;
                x = $r.X - $windowBounds.X; y = $r.Y - $windowBounds.Y; width = $r.Width; height = $r.Height }
        });
        options = @($Rows | Where-Object { $null -ne $_ } | ForEach-Object { @{ name = $_.name; runtime_id = $_.id;
            x = $_.rect.X - $windowBounds.X; y = $_.rect.Y - $windowBounds.Y;
            width = $_.rect.Width; height = $_.rect.Height } })
    }
    $capture = [System.Drawing.Rectangle]::FromLTRB(
        [int][Math]::Floor([Math]::Min($windowBounds.Left, $menuSearchBounds.Left)),
        [int][Math]::Floor([Math]::Min($windowBounds.Top, $menuSearchBounds.Top)),
        [int][Math]::Ceiling([Math]::Max($windowBounds.Right, $menuSearchBounds.Right)),
        [int][Math]::Ceiling([Math]::Max($windowBounds.Bottom, $menuSearchBounds.Bottom)))
    $capture = [System.Drawing.Rectangle]::Intersect($capture, $menuScreen)
    $bitmap = [System.Drawing.Bitmap]::new($capture.Width, $capture.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($capture.X, $capture.Y, 0, 0, $bitmap.Size)
        $bitmap.Save((Join-Path $job ($filePrefix + '-' + $Suffix + '-menu.png')), [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
function Close-ConfirmedMenu {
    if ($script:menuOpened) {
        Assert-MenuOwner
        $windows = @(Menu-Windows)
        $stillOpen = @($windows | Where-Object { ($_.GetRuntimeId() -join ':') -in $script:menuPopupIds }).Count -gt 0 -or
            @(Visible-MenuRows $windows | Where-Object { $_.id -in $script:menuOptionIds }).Count -gt 0
        if (-not $stillOpen) { $script:menuOpened = $false; return }
        Assert-MenuOwner
        [System.Windows.Forms.SendKeys]::SendWait('{ESC}')
        Start-Sleep -Milliseconds 300
        $script:menuOpened = $false
    }
}
function Open-NamedMenu([string]$Suffix) {
    Assert-Panel
    $beforeSelection = $menuValue.Current.Value
    $script:menuOpened = $false
    $script:menuPopupIds = @(); $script:menuOptionIds = @(); $script:menuPopupHandles = @()
    $beforeWindows = @(Menu-Windows)
    Save-MenuDiscovery ($Suffix + '-before-scan') 'before row discovery; menu not invoked' $beforeWindows @()
    $beforeRows = @(Visible-MenuRows $beforeWindows)
    Save-MenuDiscovery ($Suffix + '-before') 'before invocation' $beforeWindows $beforeRows
    if ($beforeRows.Count -ne 0) { throw 'Adjacent menu rows already visible before invocation; no menu opened.' }
    $beforeOptionIds = @($beforeRows | ForEach-Object { $_.id })
    $invoke = $null
    if (-not $button.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invoke)) {
        throw 'Menu lacks an Invoke pattern; no guessed click.'
    }
    Assert-Panel
    if ($menuValue.Current.Value -cne $beforeSelection) { throw 'Menu changed during discovery; no menu opened.' }
    $invoke.Invoke()
    Start-Sleep -Milliseconds 1500
    # This process-only check permits metadata discovery, never input delivery.
    # Popup handles are accepted only after the named/anchored list is verified.
    Assert-MenuOwner -Discovering
    if ($menuValue.Current.Value -cne $beforeSelection) { throw 'Menu changed selection merely by opening.' }
    $afterWindows = @(Menu-Windows)
    Save-MenuDiscovery ($Suffix + '-after-scan') 'after invocation; before row discovery' $afterWindows @()
    if ($afterWindows.Count -gt 4) { throw 'Too many adjacent menu windows; inventory saved.' }
    # Qt can reuse a popup container. Its rows must become visible this opening;
    # the container itself need not have a new runtime ID.
    $rows = @(Visible-MenuRows $afterWindows | Where-Object { $_.id -notin $beforeOptionIds } |
        Sort-Object { $_.rect.Y }, { $_.rect.X })
    Save-MenuDiscovery $Suffix 'after scoped row discovery' $afterWindows $rows
    if ($rows.Count -ne [int]$control.positions -or
        @($rows | Where-Object { [string]::IsNullOrWhiteSpace($_.name) }).Count -ne 0 -or
        @($rows | ForEach-Object { $_.name } | Select-Object -Unique).Count -ne $rows.Count) {
        throw 'Menu does not expose the reviewed number of unique named choices; inventory saved.'
    }
    for ($n = 0; $n -lt $rows.Count; $n++) {
        $r = $rows[$n].rect
        if ([Math]::Abs($r.X - $buttonBounds.X) -gt 32 -or $r.Width -gt 400 -or $r.Height -gt 80 -or
            ($n -gt 0 -and $r.Top -lt $rows[$n - 1].rect.Bottom)) { throw 'Menu rows are not a clear list anchored to the dropdown.' }
    }
    if ([Math]::Min([Math]::Abs($rows[0].rect.Top - $buttonBounds.Bottom),
        [Math]::Abs($rows[-1].rect.Bottom - $buttonBounds.Top)) -gt 32) { throw 'Menu list is not adjacent to the reviewed dropdown.' }
    $verifiedWindows = @($afterWindows | Where-Object {
        $pr = $_.Current.BoundingRectangle
        @($rows | Where-Object { -not $pr.Contains($_.rect) }).Count -eq 0
    })
    $script:menuPopupIds = @($verifiedWindows | ForEach-Object { $_.GetRuntimeId() -join ':' })
    $script:menuPopupHandles = @($verifiedWindows | ForEach-Object { [long]$_.Current.NativeWindowHandle } | Where-Object { $_ -ne 0 })
    $script:menuOptionIds = @($rows | ForEach-Object { $_.id })
    $script:menuOpened = $true
    Assert-MenuOwner
    return $rows
}
function Select-NamedMenu($Rows, [int]$Position) {
    Assert-MenuOwner
    $row = $Rows[$Position]; $now = $row.element.Current
    if ($now.Name -cne $row.name -or $now.BoundingRectangle -ne $row.rect -or
        $now.IsOffscreen -or -not $now.IsEnabled -or $now.ProcessId -ne $root.Current.ProcessId) {
        throw 'Named menu choice changed before selection.'
    }
    $currentWindows = @(Menu-Windows | Where-Object {
        [long]$_.Current.NativeWindowHandle -in $script:menuPopupHandles -and
        $_.Current.BoundingRectangle.Contains($now.BoundingRectangle)
    })
    if ($currentWindows.Count -ne 1) { throw 'Named row has no unique native-visible popup; no click sent.' }
    if (-not [AfxScanInput]::SetCursorPos([int]($row.rect.X + $row.rect.Width/2),
        [int]($row.rect.Y + $row.rect.Height/2))) { throw 'Cannot position menu pointer.' }
    Assert-MenuOwner
    [AfxScanInput]::Click()
    Start-Sleep -Milliseconds 1500
    Assert-Panel
    if ($menuValue.Current.Value -cne $row.name) { throw 'Menu selected a different name; stopped.' }
    $after = @(Menu-Windows)
    if (@($after | Where-Object { ($_.GetRuntimeId() -join ':') -in $script:menuPopupIds }).Count -gt 0 -or
        @(Visible-MenuRows $after | Where-Object { $_.id -in $script:menuOptionIds }).Count -gt 0) {
        throw 'Menu remained open after selection.'
    }
    $script:menuOpened = $false
}

function Get-KeyPopups {
    $result = @()
    foreach ($native in [AfxScanInput]::NativeVisibleWindows([uint32]$root.Current.ProcessId)) {
        $node = [System.Windows.Automation.AutomationElement]::FromHandle($native)
        if ($native -eq [IntPtr]::Zero) { continue }
        $nativeRect = [AfxScanInput+WindowRect]::new(); [uint32]$nativeOwner = 0
        if ([AfxScanInput]::GetWindowThreadProcessId($native, [ref]$nativeOwner) -eq 0 -or
            -not [AfxScanInput]::GetWindowRect($native, [ref]$nativeRect)) { continue }
        $rect = [System.Drawing.Rectangle]::FromLTRB($nativeRect.left, $nativeRect.top,
            $nativeRect.right, $nativeRect.bottom)
        if ([AfxScanInput]::IsDropdownPopup($rect, $keyButtonRect, $native.ToInt64(), $handle.ToInt64(),
            $nativeOwner, [uint32]$root.Current.ProcessId, [AfxScanInput]::IsWindowVisible($native),
            $node.Current.ClassName)) {
            $result += @{ handle = $native.ToInt64(); rect = $rect; class_name = $node.Current.ClassName }
        }
    }
    if ($result.Count -gt 4) { throw 'Too many native dropdown windows; stopped before further input.' }
    return $result
}
function Assert-KeyOwner($PopupHandles, [switch]$Discovering) {
    $foreground = [AfxScanInput]::GetForegroundWindow(); [uint32]$foregroundOwner = 0
    if ([AfxScanInput]::GetWindowThreadProcessId($foreground, [ref]$foregroundOwner) -eq 0 -or
        $foregroundOwner -ne [uint32]$root.Current.ProcessId -or
        $root.Current.BoundingRectangle -ne $windowBounds -or
        $button.Current.BoundingRectangle -ne $buttonBounds -or
        [AfxScanInput]::GetAsyncKeyState(27) -lt 0) { throw 'Key activation owner, bounds or focus changed.' }
    Assert-AfxChannel
    if (-not $Discovering -and $foreground -ne $handle -and $foreground.ToInt64() -notin $PopupHandles) {
        throw 'Key activation focus is neither the panel nor its observed native dropdown.'
    }
}
function Activate-KeyTarget {
    Assert-Panel
    $keyDesktop = [System.Windows.Automation.AutomationElement]::RootElement
    $keyOwnerCondition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$root.Current.ProcessId)
    $keyButtonRect = [System.Drawing.Rectangle]::new([int]$buttonBounds.X, [int]$buttonBounds.Y,
        [int][Math]::Ceiling($buttonBounds.Width), [int][Math]::Ceiling($buttonBounds.Height))
    if (@(Get-KeyPopups).Count -ne 0) { throw 'A native dropdown is already open; no activation click sent.' }
    $x = [int]($buttonBounds.X + $buttonBounds.Width/2)
    $y = [int]($buttonBounds.Y + $buttonBounds.Height/2)
    if (-not [AfxScanInput]::SetCursorPos($x, $y)) { throw 'Cannot position activation pointer.' }
    Assert-Panel
    if ($selection.Current.Value -cne $initialSelection) { throw 'Selection changed before activation.' }
    [AfxScanInput]::Click()
    $deadline = [DateTime]::UtcNow.AddSeconds(8)
    $opened = @()
    do {
        Assert-KeyOwner @() -Discovering
        if ($selection.Current.Value -cne $initialSelection) { throw 'Opening changed selection; no closing click sent.' }
        $opened = @(Get-KeyPopups)
        if ($opened.Count -ne 0) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($opened.Count -eq 0) { throw 'No native dropdown opening observed; no retry or closing click.' }
    $openedHandles = @($opened | ForEach-Object { $_.handle })
    Write-Record (Join-Path $job 'key-activation-open.json') @{
        source = 'native popup visibility and bounds; no menu screenshot';
        handles = $openedHandles; windows = $opened; selected = $selection.Current.Value
    }
    # Recheck the actual open state after a short settling interval. No menu
    # screenshot or UIA option traversal is used to decide opening/closure.
    Start-Sleep -Milliseconds 300
    $currentPopups = @(Get-KeyPopups)
    Assert-KeyOwner $openedHandles
    if ($selection.Current.Value -cne $initialSelection -or $currentPopups.Count -eq 0 -or
        @($currentPopups | Where-Object { $_.handle -notin $openedHandles -or $_.rect.Contains($x, $y) }).Count -ne 0) {
        throw 'Dropdown changed or covers its toggle point; no closing click sent.'
    }
    [AfxScanInput]::Click()
    $deadline = [DateTime]::UtcNow.AddSeconds(8)
    do {
        Assert-KeyOwner $openedHandles -Discovering
        if ($selection.Current.Value -cne $initialSelection) { throw 'Closing changed selection; no key sent.' }
        $remaining = @(Get-KeyPopups)
        $visibleOpened = @($openedHandles | Where-Object {
            [AfxScanInput]::IsWindowVisible([IntPtr]::new([long]$_))
        })
        if ($remaining.Count -eq 0 -and $visibleOpened.Count -eq 0) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($remaining.Count -ne 0 -or $visibleOpened.Count -ne 0) { throw 'Dropdown closure was not observed; no key sent.' }
    Assert-Panel
    Write-Record (Join-Path $job 'key-activation-closed.json') @{
        source = 'same-control closing click and native popup disappearance';
        activation_verified = $true; selected = $selection.Current.Value; menu_screenshots = $false
    }
}

function Read-Knob {
    Assert-Panel
    $labels = $visible[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, 'NameLabel'))
    $texts = @($labels | Where-Object { -not $_.Current.IsOffscreen -and $_.Current.Name -match $control.status_pattern })
    if ($texts.Count -ne 1) {
        $observed = @($labels | ForEach-Object { $_.Current.Name }) -join '; '
        throw "Expected knob status is missing or ambiguous. Observed: $observed"
    }
    $text = $texts[0].Current.Name
    if ($text -notmatch $control.status_pattern) { throw 'Numeric knob label changed.' }
    $token = $Matches[1]
    if ($token -match '^-(inf(?:inity)?|\u221e)$') { return [double]::NegativeInfinity }
    if ($token -match '^(inf(?:inity)?|\u221e)$') { return [double]::PositiveInfinity }
    return [double]::Parse($token, [System.Globalization.CultureInfo]::InvariantCulture)
}
function Get-KnobPoint($Bounds, $Definition) {
    $fraction = Get-PlanDragPoint $Definition
    $horizontal = (Get-PlanDragAxis $Definition) -ceq 'horizontal'
    $panel = $visible[0].Current.BoundingRectangle
    return [AfxScanInput]::ResolveKnobPoint(
        [System.Drawing.Rectangle]::new([int]$Bounds.X,[int]$Bounds.Y,[int]$Bounds.Width,[int]$Bounds.Height),
        [System.Drawing.Rectangle]::new([int]$panel.X,[int]$panel.Y,[int]$panel.Width,[int]$panel.Height),
        [System.Drawing.Rectangle]::new([int]$windowBounds.X,[int]$windowBounds.Y,[int]$windowBounds.Width,[int]$windowBounds.Height),
        [System.Windows.Forms.SystemInformation]::VirtualScreen, $fraction.x, $fraction.y, $horizontal)
}
function Drag-Knob([int]$Delta, [bool]$ReadStatus = $true) {
    Assert-Panel
    if (-not $button.Current.IsEnabled -or $button.Current.IsOffscreen) { throw 'Knob is disabled or offscreen.' }
    $point = Get-KnobPoint $buttonBounds $control
    $x = $point.X; $y = $point.Y
    if (-not [AfxScanInput]::PointOwnedByWindow($point, $handle)) { throw 'Knob point is occluded; no input.' }
    if (-not [AfxScanInput]::SetCursorPos($x, $y)) { throw 'Cannot position pointer.' }
    # One continuous held sweep. Some controls limit each move event, so a
    # single pointer jump is insufficient even when its distance is large.
    # Native motion avoids expensive UI Automation traversal at every point.
    $horizontal = (Get-PlanDragAxis $control) -ceq 'horizontal'
    $motion = Get-PlanSweepDelta $control $Delta
    [AfxScanInput]::Sweep($x, $y, $motion, $handle, $horizontal)
    Assert-Panel
    # Re-enter the knob after the large sweep so its numeric status is visible.
    [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Left + 8), [int]($windowBounds.Bottom - 8))
    Start-Sleep -Milliseconds 200
    [void][AfxScanInput]::SetCursorPos($x, $y)
    if (-not $ReadStatus) { Start-Sleep -Milliseconds 300; return }
    for ($retry = 0; $retry -lt 6; $retry++) {
        Start-Sleep -Milliseconds 300
        Assert-Panel
        try { return Read-Knob } catch {
            if ($retry -eq 5) { throw }
        }
    }
}
function Run-WireKnobRange {
    foreach ($phase in @('minimum', 'maximum')) {
        $script:index++
        Assert-Panel
        Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
        $null = Wait-HostFile "action-$index-go.json" 10
        # Prime away from the lower clamp so the minimum has a fresh captured
        # parameter block even when this knob starts at its minimum.
        if ($phase -eq 'minimum') {
            # Exercise both directions: an initially maximum knob may suppress
            # writes for an upward-only prime. Stay within the bounded sweep.
            if ($control.feedback -eq 'captured_block') { Drag-Knob 800 $false }
            Drag-Knob -800 $false
        }
        if ($control.feedback -eq 'captured_block') {
            Write-Record (Join-Path $job "action-$index-primed.json") @{ status = 'ok' }
            $null = Wait-HostFile "action-$index-primed-ack.json" 10
        }
        $finished = $false
        for ($sweep = 1; $sweep -le 12; $sweep++) {
            $delta = 800
            if ($phase -eq 'maximum') { $delta = -800 }
            Drag-Knob $delta $false
            Write-Record (Join-Path $job "action-$index-sweep-$sweep-done.json") @{ status = 'ok'; sweep = $sweep }
            $feedback = Wait-HostFile "action-$index-sweep-$sweep-feedback.json" 10
            if (-not $feedback.continue) {
                if ($control.feedback -eq 'captured_block') {
                    if (-not $feedback.plateau_observed) { throw 'Host did not observe a stable captured block.' }
                } elseif (-not $feedback.endpoint_verified) { throw 'Host did not verify the captured endpoint.' }
                $finished = $true; break
            }
        }
        if (-not $finished) { throw 'Captured endpoint not reached within the bounded sweeps.' }
        $image = Save-Button ($filePrefix + '-' + $phase + '.png')
        $image.Dispose()
        Write-Record (Join-Path $job "action-$index-done.json") @{
            status = 'ok'; phase = $phase; observed_raw = $feedback.observed_raw;
            source = $feedback.source; restored = $false
            endpoint_verified = $feedback.endpoint_verified; plateau_observed = $feedback.plateau_observed
        }
        $null = Wait-HostFile "action-$index-ack.json" 10
    }
}
function Run-KnobRange {
    # Range-only scan: owner authorized leaving knobs at the final endpoint.
    $point = Get-KnobPoint $buttonBounds $control
    if (-not [AfxScanInput]::PointOwnedByWindow($point, $handle)) { throw 'Knob point is occluded; no input.' }
    [void][AfxScanInput]::SetCursorPos($point.X, $point.Y)
    Start-Sleep -Milliseconds 2200
    $startValue = Read-Knob
    $currentValue = $startValue
    $rangeValues = @()
    foreach ($phase in @('minimum', 'maximum')) {
        $script:index++
        Assert-Panel
        if ((Read-Knob) -ne $currentValue) { throw 'Knob changed outside the trial; stopped.' }
        Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
        $null = Wait-HostFile "action-$index-go.json" 10
        $stable = 0; $finished = $false
        $stepLimit = 4
        for ($step = 0; $step -lt $stepLimit; $step++) {
            $delta = 800
            if ($phase -eq 'maximum') { $delta = -800 }
            $next = Drag-Knob $delta
            if (($phase -eq 'minimum' -and $next -gt $currentValue) -or
                ($phase -eq 'maximum' -and $next -lt $currentValue)) { throw 'Drag direction differs from the reviewed gesture.' }
            if ($next -eq $currentValue) { $stable++ } else { $stable = 0 }
            if ($stable -ge 1 -and $step -ge 1) { $finished = $true; $currentValue = $next; break }
            $currentValue = $next
        }
        if (-not $finished) { throw 'Large sweeps did not establish a stable endpoint; stopped.' }
        $labelStatus = 'endpoint label observed'
        if ($phase -eq 'maximum' -and $currentValue -eq $rangeValues[0]) {
            $labelStatus = 'unchanged label; wire range needs review'
        }
        $rangeValues += $currentValue
        $image = Save-Button ($filePrefix + '-' + $phase + '.png')
        $image.Dispose()
        Write-Record (Join-Path $job "action-$index-done.json") @{
            status = 'ok'; phase = $phase; starting_value = $startValue; displayed_value = $currentValue;
            source = 'numeric vendor status; rounded display, not device readback'; restored = $false;
            range_label_status = $labelStatus
        }
        $null = Wait-HostFile "action-$index-ack.json" 10
    }
}

[void][AfxScanInput]::SetProcessDPIAware()
Write-Host "$($plan.panel): AFX $($plan.channel), $($plan.controls.Count) reviewed control(s)."
$coverage = $plan.coverage
if ($null -eq $coverage) { $coverage = @{ status = 'partial; controls outside plan unknown' } }
Write-Host "Coverage: $($coverage.status)"
foreach ($pending in $coverage.pending) { Write-Host "Pending outside this batch: $pending" }
Write-Host "Prepare $($plan.panel) on unlinked AFX $($plan.channel). Linux recorder must already be waiting."
Write-Host 'The runner operates the selected controls automatically; do not click plugin buttons yourself.'
Write-Host 'After pressing Enter, the terminal minimizes. Focus the plugin using its title bar within 10 seconds.'
Write-Host 'Then leave mouse and keyboard alone. The terminal returns when finished or stopped.'
if (@($plan.controls | Where-Object { $_.kind -eq 'knob_range' }).Count -gt 0) {
    Write-Host 'Range-only test: knobs are left at maximum. Starting values will not be restored.'
}
Write-Host "Launch log saved automatically: $launchLog"
if (-not $Prepared) { $null = Read-Host 'Press Enter when the panel is ready' }
$console = [AfxScanInput]::GetConsoleWindow()
if ($console -ne [IntPtr]::Zero) { [void][AfxScanInput]::ShowWindow($console, 6) }
$job = $null
$baseline = $null
$changed = $null
$restored = $null
try {
    if (-not $Prepared) { Start-Sleep -Seconds 10 }
    $handle = [AfxScanInput]::GetForegroundWindow()
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
    if ((Get-Process -Id $root.Current.ProcessId).ProcessName -ne $plan.process_name) {
        throw 'Focus the Orion vendor panel.'
    }
    $windowBounds = $root.Current.BoundingRectangle
    $panels = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ClassNameProperty, $plan.panel_class))
    $visible = @($panels | Where-Object {
        -not $_.Current.IsOffscreen -and $windowBounds.Contains($_.Current.BoundingRectangle)
    })
    if ($visible.Count -ne 1) { throw 'Exactly one fully visible target panel is required.' }
    $targets = @()
    foreach ($control in $plan.controls) {
        $buttons = $visible[0].FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::ClassNameProperty, $control.class_name))
        $panelBounds = $visible[0].Current.BoundingRectangle
        $candidates = @($buttons | Where-Object {
            $rect = $_.Current.BoundingRectangle
            $inside = -not $_.Current.IsOffscreen -and $panelBounds.Contains($rect)
            # PowerGate's measured Pan containers extend 11px above / 1px
            # below their parent, but the knob centres are inside the panel.
            # VEQ-4K PINK lower rotary containers extend 14px below their
            # parent: unattended-20261027T015403Z-load-veq4k-pink/raw-ui.json.
            # Only explicit reviewed knob plans may allow this small overflow.
            $margin = Get-PlanOverflow $control
            if ($null -ne $margin) {
                $expanded = [System.Windows.Rect]::new($panelBounds.X - $margin,
                    $panelBounds.Y - $margin, $panelBounds.Width + 2*$margin, $panelBounds.Height + 2*$margin)
                $centre = [System.Windows.Rect]::new($rect.X + $rect.Width/2 - 8,
                    $rect.Y + $rect.Height/2 - 8, 16, 16)
                $inside = -not $_.Current.IsOffscreen -and $windowBounds.Contains($rect) -and
                    $expanded.Contains($rect) -and $panelBounds.Contains($centre)
            }
            if ($null -ne $control.region) {
                $rx = ($rect.X + $rect.Width/2 - $panelBounds.X)/$panelBounds.Width
                $ry = ($rect.Y + $rect.Height/2 - $panelBounds.Y)/$panelBounds.Height
                $inside = $inside -and $rx -ge $control.region.x[0] -and $rx -le $control.region.x[1] -and
                    $ry -ge $control.region.y[0] -and $ry -le $control.region.y[1]
            }
            $inside
        })
        if ($candidates.Count -ne 1) { throw "Missing or ambiguous control: $($control.label)" }
        $candidateBounds = $candidates[0].Current.BoundingRectangle
        if (-not $candidates[0].Current.IsEnabled -or $candidateBounds.IsEmpty -or
            $candidateBounds.Width -le 0 -or $candidateBounds.Height -le 0) {
            throw "Control is disabled or has empty bounds: $($control.label). No batch started."
        }
        if ($control.kind -eq 'knob_range') {
            $null = Get-KnobPoint $candidateBounds $control
        }
        $targets += @{ definition = $control; element = $candidates[0] }
    }
    $control = $targets[0].definition
    $button = $targets[0].element
    $buttonBounds = $button.Current.BoundingRectangle
    $buttonRuntimeId = $button.GetRuntimeId()-join ':'
    if (-not $button.Current.IsEnabled -or -not $windowBounds.Contains($buttonBounds)) {
        throw 'Target button is not fully visible and enabled.'
    }
    $crop = [System.Drawing.Rectangle]::new([int]$buttonBounds.X - 2, [int]$buttonBounds.Y - 2,
        [int]$buttonBounds.Width + 4, [int]$buttonBounds.Height + 4)
    Assert-Panel
    $job = Join-Path $PSScriptRoot ('results\scan-' + $panelLabel + '-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
    New-Item -ItemType Directory -Path $job | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($DiscoveryDirectory)) {
        Copy-Item -LiteralPath (Join-Path $DiscoveryDirectory 'inventory.json') -Destination (Join-Path $job 'discovery-inventory.json')
    }
    if (-not [string]::IsNullOrWhiteSpace($ResumeDirectory)) {
        Write-Record (Join-Path $job 'resume-source.json') @{ job = (Split-Path -Leaf $ResumeDirectory) }
    }
    # Move away from the target so hover highlighting cannot impersonate a state change.
    [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Right - 3), [int]($windowBounds.Bottom - 3))
    Start-Sleep -Milliseconds 500
    $jobRequest = @{
        version = 2; plan_id = $plan.id; panel = $plan.panel; channel = $plan.channel;
        controls = @($plan.controls | ForEach-Object { $_.id });
        actions = [int](($plan.controls | ForEach-Object { if ($_.kind -eq 'selector_cycle') { [int]$_.positions } elseif ($_.kind -in @('selector_positions', 'menu_positions')) { [int]$_.positions + 1 } else { 2 } } | Measure-Object -Sum).Sum)
    }
    if (@($plan.controls | Where-Object {
        $_.PSObject.Properties.Name -contains 'drag_point' -or $_.PSObject.Properties.Name -contains 'drag_axis'
    }).Count -gt 0) {
        $jobRequest.version = 5
        $jobRequest.executed_plan = $plan
    }
    if (-not [string]::IsNullOrWhiteSpace($DiscoveryDirectory)) {
        $jobRequest.version = 3
        $jobRequest.executed_plan = $plan
    }
    if (-not [string]::IsNullOrWhiteSpace($ResumeDirectory)) {
        $jobRequest.version = 4
        $jobRequest.executed_plan = $plan
        $jobRequest.resume_reviewed = $true
    }
    Write-Record (Join-Path $job 'request.json') $jobRequest
    $ready = Wait-HostFile 'ready.json' 45
    $script:captureBudget = $ready.budget
    if ($null -eq $script:captureBudget -or $script:captureBudget.feedback_seconds -lt 10 -or
        $script:captureBudget.feedback_seconds -gt 60) { throw 'Host capture budget is missing or invalid.' }
    $index = 0
    foreach ($target in $targets) {
    foreach ($oldBitmap in @($baseline, $changed, $restored)) {
        if ($null -ne $oldBitmap) { $oldBitmap.Dispose() }
    }
    $baseline = $null; $changed = $null; $restored = $null
    $control = $target.definition
    $button = $target.element
    $buttonBounds = $button.Current.BoundingRectangle
    $buttonRuntimeId = $button.GetRuntimeId()-join ':'
    if (-not $button.Current.IsEnabled -or -not $windowBounds.Contains($buttonBounds)) { throw 'Target is no longer enabled/visible.' }
    $crop = [System.Drawing.Rectangle]::new([int]$buttonBounds.X - 2, [int]$buttonBounds.Y - 2,
        [int]$buttonBounds.Width + 4, [int]$buttonBounds.Height + 4)
    $filePrefix = $panelLabel + '-' + $control.id
    if ($control.kind -eq 'menu_positions') {
        $menuDesktop = [System.Windows.Automation.AutomationElement]::RootElement
        $menuOwnerCondition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$root.Current.ProcessId)
        $menuOptionCondition = [System.Windows.Automation.OrCondition]::new(
            [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem),
            [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::MenuItem))
        $menuScreen = [System.Windows.Forms.SystemInformation]::VirtualScreen
        $menuRootId = $root.GetRuntimeId() -join ':'
        $menuExtent = [int]$control.positions * 80 + 32
        $menuSearchBounds = [System.Windows.Rect]::new($buttonBounds.X - 32,
            $buttonBounds.Top - $menuExtent, 464, $buttonBounds.Height + 2 * $menuExtent)
    }
    if ($control.kind -eq 'menu_positions') {
        if ([int]$control.positions -lt 2 -or [int]$control.positions -gt 8 -or
            [int]$control.dwell_ms -lt 3000 -or [int]$control.dwell_ms -gt 10000 -or
            $button.Current.ControlType -ne [System.Windows.Automation.ControlType]::ComboBox) {
            throw 'Named menu requires a reviewed finite count, slow dwell and ComboBox.'
        }
        $menuValue = $null
        if (-not $button.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$menuValue)) {
            throw 'Menu selected value is unavailable.'
        }
        $startingSelection = $menuValue.Current.Value
        if ([string]::IsNullOrWhiteSpace($startingSelection)) { throw 'Starting menu choice is unknown.' }
        $optionNames = @(); $startingPosition = -1; $acceptedSelection = $startingSelection
        $crop = [System.Drawing.Rectangle]::new([int]$windowBounds.X, [int]$windowBounds.Y,
            [int]$windowBounds.Width, [int]$windowBounds.Height)
        try {
            foreach ($menuPhase in @(1..([int]$control.positions + 1))) {
                $index++
                Assert-Panel
                if ($menuValue.Current.Value -cne $acceptedSelection) { throw 'Menu changed outside scan; no further selection.' }
                Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
                $null = Wait-HostFile "action-$index-go.json" 10
                Assert-Panel
                if ($menuValue.Current.Value -cne $acceptedSelection) { throw 'Menu changed while waiting; no further selection.' }
                $rows = @(Open-NamedMenu ('phase-' + $menuPhase))
                $names = @($rows | ForEach-Object { $_.name })
                if ($optionNames.Count -eq 0) {
                    $optionNames = $names
                    $matchingStart = @(0..($names.Count - 1) | Where-Object { $names[$_] -ceq $startingSelection })
                    if ($matchingStart.Count -ne 1) { throw 'Starting choice is not exactly one visible menu entry.' }
                    $startingPosition = $matchingStart[0]
                } elseif (($names | ConvertTo-Json -Compress) -cne ($optionNames | ConvertTo-Json -Compress)) {
                    throw 'Named menu choices changed during scan.'
                }
                $position = $menuPhase - 1
                if ($menuPhase -gt [int]$control.positions) { $position = $startingPosition }
                if ($menuValue.Current.Value -ceq $names[$position]) {
                    # A selected entry can suppress OUT. Prime a different named
                    # entry only when needed, then capture the requested target.
                    Select-NamedMenu $rows (($position + 1) % $names.Count)
                    $rows = @(Open-NamedMenu ('phase-' + $menuPhase + '-target'))
                    $freshNames = @($rows | ForEach-Object { $_.name })
                    if (($freshNames | ConvertTo-Json -Compress) -cne ($optionNames | ConvertTo-Json -Compress)) {
                        throw 'Menu choices changed after priming.'
                    }
                }
                Select-NamedMenu $rows $position
                [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Right - 3), [int]($windowBounds.Bottom - 3))
                Start-Sleep -Milliseconds ([int]$control.dwell_ms)
                Assert-Panel
                if ($menuValue.Current.Value -cne $optionNames[$position]) { throw 'Menu choice changed during dwell.' }
                $image = Save-Button ($filePrefix + '-position-' + $menuPhase + '.png'); $image.Dispose()
                Write-Record (Join-Path $job "action-$index-done.json") @{
                    status = 'ok'; option_names = $optionNames; selection = $menuValue.Current.Value;
                    starting_selection = $startingSelection; starting_position = $startingPosition;
                    popup_closed = $true; dwell_ms = [int]$control.dwell_ms;
                    source = 'explicit named GUI menu choices; not device readback'
                }
                $ack = Wait-HostFile "action-$index-ack.json" 10
                if ($menuPhase -eq [int]$control.positions -and
                    ($null -eq $ack.restore_position -or [int]$ack.restore_position -ne $startingPosition)) {
                    throw 'Host restore position disagrees with starting menu name.'
                }
                $acceptedSelection = $optionNames[$position]
            }
        } catch {
            Close-ConfirmedMenu
            throw
        }
        continue
    }
    if ($control.kind -eq 'knob_range') {
        $crop = [System.Drawing.Rectangle]::new([int]$windowBounds.X, [int]$windowBounds.Y,
            [int]$windowBounds.Width, [int]$windowBounds.Height)
        if ($control.feedback -in @('captured_wire', 'captured_block')) { Run-WireKnobRange } else { Run-KnobRange }
        continue
    }
    if ($control.feedback -eq 'gui_toggle') {
        $toggle = $null
        if (-not $button.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$toggle)) {
            throw 'Binary TogglePattern is unavailable.'
        }
        $initialToggle = $toggle.Current.ToggleState.ToString()
        if ($initialToggle -notin @('On', 'Off')) { throw 'Toggle is not binary.' }
        $acceptedToggle = $initialToggle
        foreach ($togglePhase in @(1, 2)) {
            $index++
            Assert-Panel
            if ($toggle.Current.ToggleState.ToString() -cne $acceptedToggle) { throw 'Toggle changed outside trial.' }
            Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
            $null = Wait-HostFile "action-$index-go.json" 10
            Assert-Panel
            if ($toggle.Current.ToggleState.ToString() -cne $acceptedToggle) { throw 'Toggle changed while waiting; no click sent.' }
            if (-not [AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width/2),
                [int]($buttonBounds.Y + $buttonBounds.Height/2))) { throw 'Cannot position toggle pointer.' }
            [AfxScanInput]::Click()
            [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Right - 3), [int]($windowBounds.Bottom - 3))
            Start-Sleep -Milliseconds 700
            Assert-Panel
            $nowToggle = $toggle.Current.ToggleState.ToString()
            $expectedToggle = $initialToggle
            if ($togglePhase -eq 1) { if ($initialToggle -eq 'On') { $expectedToggle = 'Off' } else { $expectedToggle = 'On' } }
            $image = Save-Button ($filePrefix + '-toggle-' + $togglePhase + '.png'); $image.Dispose()
            if ($nowToggle -cne $expectedToggle) { throw 'Toggle did not change/restore; no further click.' }
            Write-Record (Join-Path $job "action-$index-done.json") @{
                status = 'ok'; starting_selection = $initialToggle; selection = $nowToggle;
                source = 'binary GUI TogglePattern round trip; not device readback'
            }
            $null = Wait-HostFile "action-$index-ack.json" 10
            $acceptedToggle = $nowToggle
        }
        continue
    }
    if ($control.kind -eq 'key_button') {
        if ($control.dwell_ms -ne 5000 -or
            $button.Current.ControlType -ne [System.Windows.Automation.ControlType]::ComboBox) {
            throw 'Page key trial requires an exact reviewed ComboBox and five-second dwell.'
        }
        $selection = $null
        if (-not $button.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$selection)) {
            throw 'Key target selected value is unavailable.'
        }
        $initialSelection = $selection.Current.Value
        if ([string]::IsNullOrWhiteSpace($initialSelection)) { throw 'Starting key selection is unknown.' }
        $acceptedSelection = $initialSelection
        $crop = [System.Drawing.Rectangle]::new([int]$windowBounds.X, [int]$windowBounds.Y,
            [int]$windowBounds.Width, [int]$windowBounds.Height)
        $activationNames = @($control.option_names)
        $initialPositions = @(0..($activationNames.Count - 1) | Where-Object { $activationNames[$_] -ceq $initialSelection })
        if ($initialPositions.Count -ne 1 -or $initialPositions[0] -eq $activationNames.Count - 1) {
            throw 'Page Down needs a known starting choice with a following visible option; no key sent.'
        }
        Activate-KeyTarget
        foreach ($keyPhase in @(1, 2)) {
            $index++
            Assert-Panel
            if ($selection.Current.Value -cne $acceptedSelection) { throw 'Selection changed outside key trial.' }
            Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
            $null = Wait-HostFile "action-$index-go.json" 10
            Assert-Panel
            if ($selection.Current.Value -cne $acceptedSelection) { throw 'Selection changed while waiting; no key sent.' }
            if (-not [AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width/2),
                [int]($buttonBounds.Y + $buttonBounds.Height/2))) { throw 'Cannot hover key target.' }
            $button.SetFocus()
            Assert-Panel
            if (-not $button.Current.HasKeyboardFocus -or $selection.Current.Value -cne $acceptedSelection) {
                throw 'Exact ComboBox keyboard focus/value was not preserved; no key sent.'
            }
            $keyName = 'PageDown'; $keyCode = 0x22
            if ($keyPhase -eq 2) { $keyName = 'PageUp'; $keyCode = 0x21 }
            [AfxScanInput]::PageKey($keyCode, $handle)
            Start-Sleep -Milliseconds 5000
            Assert-Panel
            if (-not $button.Current.HasKeyboardFocus) { throw 'Key target lost keyboard focus during dwell.' }
            $nowSelection = $selection.Current.Value
            $expectedSelection = $activationNames[$initialPositions[0] + 1]
            if ($keyPhase -eq 2) { $expectedSelection = $initialSelection }
            if ([string]::IsNullOrWhiteSpace($nowSelection) -or
                $nowSelection -cne $expectedSelection) {
                throw 'Page key did not change/restore selection; no further key sent.'
            }
            $image = Save-Button ($filePrefix + '-' + $keyName + '.png'); $image.Dispose()
            if ($selection.Current.Value -cne $nowSelection) { throw 'Selection changed during key screenshot.' }
            Write-Record (Join-Path $job "action-$index-done.json") @{
                status = 'ok'; starting_selection = $initialSelection; selection = $nowSelection;
                key = $keyName; keypresses = 1; dwell_ms = 5000; keyboard_focus_verified = $true;
                activation_verified = $true; option_names = $activationNames;
                source = 'clicked open/close activation and focused Page key GUI round trip; not device readback'
            }
            $null = Wait-HostFile "action-$index-ack.json" 10
            $acceptedSelection = $nowSelection
        }
        continue
    }
    if ($control.kind -eq 'wheel_button') {
        if ($null -eq $wheelPolicy -or
            ($wheelPolicy.step_delta -isnot [int] -and $wheelPolicy.step_delta -isnot [long]) -or
            ($wheelPolicy.pause_ms -isnot [int] -and $wheelPolicy.pause_ms -isnot [long]) -or
            ($wheelPolicy.max_pulses -isnot [int] -and $wheelPolicy.max_pulses -isnot [long]) -or
            $wheelPolicy.step_delta -lt 1 -or $wheelPolicy.step_delta -gt 30 -or
            $wheelPolicy.pause_ms -lt 1000 -or $wheelPolicy.pause_ms -gt 3000 -or
            $wheelPolicy.max_pulses -lt 1 -or $wheelPolicy.max_pulses -gt 12 -or
            ($wheelPolicy.step_delta * $wheelPolicy.max_pulses) -gt 120 -or
            ($wheelPolicy.pause_ms * $wheelPolicy.max_pulses) -gt 20000) { throw 'Wheel pacing policy is invalid.' }
        if ($button.Current.ControlType -ne [System.Windows.Automation.ControlType]::ComboBox) { throw 'Wheel target must be a reviewed ComboBox.' }
        $selection = $null
        if (-not $button.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$selection)) { throw 'Dropdown selection is unavailable.' }
        $initialSelection = $selection.Current.Value
        if ([string]::IsNullOrWhiteSpace($initialSelection)) { throw 'Dropdown starting selection is unknown.' }
        $acceptedSelection = $initialSelection
        $forwardPulses = 0
        $crop = [System.Drawing.Rectangle]::new([int]$windowBounds.X, [int]$windowBounds.Y,
            [int]$windowBounds.Width, [int]$windowBounds.Height)
        foreach ($wheelPhase in @(1, 2)) {
            $index++
            Assert-Panel
            if ($selection.Current.Value -cne $acceptedSelection) { throw 'Dropdown changed outside trial; no wheel sent.' }
            Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
            $null = Wait-HostFile "action-$index-go.json" 10
            Assert-Panel
            if ($selection.Current.Value -cne $acceptedSelection) { throw 'Dropdown changed while waiting; no wheel sent.' }
            $wheelDelta = -[int]$wheelPolicy.step_delta
            $pulseLimit = [int]$wheelPolicy.max_pulses
            if ($wheelPhase -eq 2) { $wheelDelta = [int]$wheelPolicy.step_delta; $pulseLimit = $forwardPulses }
            $pulseRows = @()
            $nowSelection = $acceptedSelection
            for ($pulse = 1; $pulse -le $pulseLimit; $pulse++) {
                Assert-Panel
                if ($selection.Current.Value -cne $acceptedSelection) { throw 'Dropdown changed between pulses; no further wheel sent.' }
                if (-not [AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width/2),
                    [int]($buttonBounds.Y + $buttonBounds.Height/2))) { throw 'Cannot hover dropdown.' }
                [AfxScanInput]::Wheel($wheelDelta)
                Start-Sleep -Milliseconds ([int]$wheelPolicy.pause_ms)
                Assert-Panel
                $nowSelection = $selection.Current.Value
                $pulseRow = @{ delta = $wheelDelta; pause_ms = [int]$wheelPolicy.pause_ms;
                    starting_selection = $acceptedSelection; selection = $nowSelection }
                $pulseRows += $pulseRow
                Write-Record (Join-Path $job "action-$index-wheel-pulse-$pulse.json") $pulseRow
                $image = Save-Button ($filePrefix + '-wheel-' + $wheelPhase + '-pulse-' + $pulse + '.png')
                $image.Dispose()
                if ([string]::IsNullOrWhiteSpace($nowSelection)) { throw 'Dropdown selection became unknown; no further wheel sent.' }
                # Do not queue more input once the first visible change occurs.
                if ($nowSelection -cne $acceptedSelection) { break }
            }
            if ($wheelPhase -eq 1) { $forwardPulses = $pulseRows.Count }
            [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Right - 3), [int]($windowBounds.Bottom - 3))
            Assert-Panel
            if ($selection.Current.Value -cne $nowSelection) { throw 'Dropdown changed after the paced wheel; stopped.' }
            $ok = -not [string]::IsNullOrWhiteSpace($nowSelection)
            if ($wheelPhase -eq 1) { $ok = $ok -and $nowSelection -cne $initialSelection }
            else { $ok = $ok -and $nowSelection -ceq $initialSelection }
            $image = Save-Button ($filePrefix + '-wheel-' + $wheelPhase + '.png')
            $image.Dispose()
            $status = 'failed'; if ($ok) { $status = 'ok' }
            Write-Record (Join-Path $job "action-$index-done.json") @{
                status = $status; starting_selection = $initialSelection; selection = $nowSelection;
                source = 'paced partial wheel and GUI ValuePattern round trip; not device readback';
                wheel_delta = $wheelDelta; wheel_pulses = $pulseRows
            }
            if (-not $ok) { throw 'Wheel did not change/restore dropdown; no retry or blind repair.' }
            $null = Wait-HostFile "action-$index-ack.json" 10
            $acceptedSelection = $nowSelection
        }
        continue
    }
    if ($null -ne $control.visual_region) {
        # Some switches indicate their state in a separate LED above the button.
        $region = $control.visual_region
        $visualBounds = [System.Windows.Rect]::new(
            $windowBounds.X + [double]$region.x, $windowBounds.Y + [double]$region.y,
            [double]$region.width, [double]$region.height)
        if (-not $windowBounds.Contains($visualBounds) -or -not $visualBounds.Contains($buttonBounds)) {
            throw 'Reviewed visual region must contain the button and stay inside the window.'
        }
        $crop = [System.Drawing.Rectangle]::new([int]$visualBounds.X, [int]$visualBounds.Y,
            [int]$visualBounds.Width, [int]$visualBounds.Height)
    }
    $baseline = Save-Button ($filePrefix + '-before.png')
    $phaseCount = 2
    if ($control.kind -in @('selector_cycle', 'selector_positions')) {
        $phaseCount = [int]$control.positions
        if ($phaseCount -lt 2 -or $phaseCount -gt 8) { throw 'Selector needs a reviewed finite cycle.' }
    }
    $positionCount = $phaseCount
    if ($control.kind -eq 'selector_positions') {
        if (@($control.position_points).Count -ne $positionCount) { throw 'Direct selector points are missing.' }
        $phaseCount++
    }
    $restorePosition = -1
    $startingPosition = -1
    $minimumChange = .05
    if ($null -ne $control.minimum_visual_change) {
        $minimumChange = [double]$control.minimum_visual_change
        if ($minimumChange -le 0 -or $minimumChange -gt .05) { throw 'Invalid visual comparison threshold.' }
    }
    $cycleImages = @()
    foreach ($phase in @(1..$phaseCount)) {
        $index++
        Assert-Panel
        if ($control.feedback -ne 'captured_toggle') {
            $current = Save-Button ($filePrefix + '-before-restore.png')
            try {
                $reference = $changed
                if ($phase -eq 1) { $reference = $baseline }
                if ([AfxScanInput]::Difference($reference, $current) -gt [Math]::Min(.02, $minimumChange)) {
                    throw 'Button changed since trial; restoration blocked to preserve newer edits.'
                }
            } finally { $current.Dispose() }
        }
        Write-Record (Join-Path $job "action-$index-request.json") @{ action = $index; control = $control.id }
        $null = Wait-HostFile "action-$index-go.json" 10
        Assert-Panel
        if ($control.kind -eq 'selector_positions') {
            $position = $phase - 1
            if ($phase -eq $phaseCount) { $position = $restorePosition }
            if ($position -lt 0 -or $position -ge $positionCount) { throw 'No verified restore position.' }
            # Prime another position first so an already-selected target has fresh OUT evidence.
            foreach ($pointIndex in @((($position + 1) % $positionCount), $position)) {
                $point = $control.position_points[$pointIndex]
                if ([double]$point.x -le 0 -or [double]$point.x -ge 1 -or [double]$point.y -le 0 -or [double]$point.y -ge 1) {
                    throw 'Direct selector point must stay inside its control.'
                }
                Assert-Panel
                if (-not [AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width * [double]$point.x),
                    [int]($buttonBounds.Y + $buttonBounds.Height * [double]$point.y))) { throw 'Could not position selector mouse.' }
                [AfxScanInput]::Click()
                Start-Sleep -Milliseconds 200
            }
        } else {
            if (-not [AfxScanInput]::SetCursorPos([int]($buttonBounds.X + $buttonBounds.Width/2),
                [int]($buttonBounds.Y + $buttonBounds.Height/2))) { throw 'Could not position mouse; stopped.' }
            [AfxScanInput]::Click()
        }
        [void][AfxScanInput]::SetCursorPos([int]($windowBounds.Right - 3), [int]($windowBounds.Bottom - 3))
        Start-Sleep -Milliseconds 700
        if ($phase -lt $phaseCount) {
            $stateFile = $filePrefix + '-changed.png'
            if ($control.kind -in @('selector_cycle', 'selector_positions')) { $stateFile = $filePrefix + '-position-' + $phase + '.png' }
            $changed = Save-Button $stateFile
            $difference = [AfxScanInput]::Difference($baseline, $changed)
            $ok = $difference -gt $minimumChange
            if ($control.kind -eq 'selector_positions') { $ok = $true }
            if ($control.kind -in @('selector_cycle', 'selector_positions')) {
                foreach ($image in $cycleImages) {
                    if ([AfxScanInput]::Difference($image, $changed) -le $minimumChange) { $ok = $false }
                }
                $cycleImages += $changed
            }
        } else {
            $stateFile = $filePrefix + '-restored.png'
            if ($control.kind -in @('selector_cycle', 'selector_positions')) { $stateFile = $filePrefix + '-position-' + $phase + '.png' }
            $restored = Save-Button $stateFile
            $difference = [AfxScanInput]::Difference($baseline, $restored)
            $ok = $difference -le [Math]::Min(.02, $minimumChange)
        }
        if ($control.kind -eq 'selector_positions' -and $phase -eq $positionCount) {
            $matches = @()
            for ($positionIndex = 0; $positionIndex -lt $cycleImages.Count; $positionIndex++) {
                if ([AfxScanInput]::Difference($baseline, $cycleImages[$positionIndex]) -le $minimumChange) { $matches += $positionIndex }
            }
            if ($matches.Count -ne 1) { throw 'Starting appearance does not match exactly one captured position.' }
            $startingPosition = $matches[0]
        }
        if ($control.feedback -eq 'captured_toggle') { $ok = $true }
        $status = 'failed'
        if ($ok) { $status = 'ok' }
        $verificationSource = 'screen comparison; not device readback'
        if ($control.feedback -eq 'captured_toggle') {
            $verificationSource = 'screenshots only; host must verify measured toggle writes before ACK'
        }
        Write-Record (Join-Path $job "action-$index-done.json") @{
            status = $status; changed_pixel_fraction = $difference;
            cycle_position = $phase; starting_position = $startingPosition;
            source = $verificationSource; guest_utc = [DateTime]::UtcNow.ToString('o')
        }
        if (-not $ok) { throw 'Visual verification failed; no further clicks.' }
        $ack = Wait-HostFile "action-$index-ack.json" 10
        if ($control.kind -eq 'selector_positions' -and $phase -eq $positionCount) {
            if ($null -eq $ack.restore_position) { throw 'Host did not verify restore position.' }
            $restorePosition = [int]$ack.restore_position
        }
    }
    foreach ($image in $cycleImages) { $image.Dispose() }
    if ($control.kind -notin @('selector_cycle', 'selector_positions') -and $null -ne $changed) { $changed.Dispose() }
    $changed = $null
    }
    Write-Record (Join-Path $job 'completed.json') @{
        status = 'ok'; coverage = $coverage; visual_restoration = (@($plan.controls | Where-Object { $_.kind -in @('knob_range', 'wheel_button', 'menu_positions', 'key_button') -or $_.feedback -in @('captured_toggle', 'gui_toggle') }).Count -eq 0);
        device_readback_verified = $false; range_knobs_left_at = 'maximum';
        restoration_source = 'images, measured toggle writes or GUI selection checks; range knobs intentionally not restored'
    }
    $null = Wait-HostFile 'host-completed.json' ([int]$script:captureBudget.finalization_seconds)
    Write-Host "Planned controls completed; check coverage for remaining controls. Evidence saved to $job"
} catch {
    if ($null -ne $job) {
        Write-Record (Join-Path $job 'guest-error.json') @{
            error = $_.Exception.Message; stop = $true; restoration = 'inspect screenshots; not assumed'
            script_stack = $_.ScriptStackTrace; position = $_.InvocationInfo.PositionMessage
        }
    }
    Write-Host "Pilot stopped: $($_.Exception.Message)"
    Write-Host $_.ScriptStackTrace
    Write-Host 'Review current state and saved screenshots. No blind restoration will be attempted.'
    exit 1
} finally {
    foreach ($bitmap in @($baseline, $changed, $restored)) {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
    }
    if ($console -ne [IntPtr]::Zero) { [void][AfxScanInput]::ShowWindow($console, 9) }
}
} finally {
    Stop-Transcript | Out-Null
}
