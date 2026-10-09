# Windows AFX panel inspection

First stage of the VM gesture runner: inspect actual UI Automation support
before choosing semantic selectors or calibrated panel coordinates. This is
read-only. It does not load effects, click buttons, query HID or change settings.

Copy this directory into the existing shared folder as `antelope-afx-tools`.
In Windows, open the desired plugin panel, then double-click
`Z:\antelope-afx-tools\Inspect-AfxPanel.cmd`. During the ten-second delay,
focus the plugin panel and keep it unobscured until inspection completes.
The inspector writes `results/panel-TIMESTAMP/controls.json` and `panel.png`
beside the scripts. Linux reads those same files directly; there is no export,
packet selection or transfer step. Each run uses a new results directory.

Inspect Instinct first: its existing Orion capture has parameter changes but
unresolved labels. Memory Cat remains useful as an optional known-map pilot;
there is no need to repeat its manual mapping.

The JSON contains visible control names, automation IDs, supported patterns,
UI values and positions relative to the selected window. UI values are not
device readbacks and do not prove wire ranges. Custom-drawn controls may expose
no useful names or patterns; the screenshot then supports a one-time coordinate
calibration. Windows may expose the whole control-panel window rather than a
separate plugin window. Review the selected title and screenshot before using
any result. This inspector is not yet a gesture runner or USB batch recorder.

Keep results and screenshots local in the shared folder or ignored `captures/`.
Password controls are skipped, but any other visible text in the selected
window can appear in local evidence. Do not focus account/activation windows.

No extra Windows package is required: the script uses Windows PowerShell,
.NET UI Automation and System.Drawing. It must run in the interactive guest
session. The `.cmd` launcher bypasses execution policy for this invocation only;
it does not change the machine's execution policy.

API reference: Microsoft's [UI Automation element inspection](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/obtaining-ui-automation-elements).
