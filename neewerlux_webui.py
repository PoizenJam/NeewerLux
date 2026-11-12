"""Web dashboard served by the NeewerLux HTTP server.

Light control, animation playback, preset recall, and status monitoring.
"""

def getWebDashboardHTML(serverAddr="", version="0.0.0"):
    """Return the complete HTML for the web dashboard."""
    return WEB_DASHBOARD_HTML.replace("{{SERVER}}", serverAddr).replace("{NLVERSION}", version)


WEB_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NeewerLux Control Panel</title>
<style>
:root {
    --bg: #1e1e2e;
    --bg2: #181828;
    --bg3: #24243a;
    --border: #3c3c50;
    --text: #d4d4d8;
    --muted: #888;
    --accent: #5b8def;
    --accent-dim: #3d6bc7;
    --green: #4caf50;
    --green-dim: #388e3c;
    --red: #e05555;
    --radius-sm: 3px;
    --radius: 4px;
    --radius-lg: 8px;
    --radius-pill: 999px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', 'Helvetica Neue', sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    min-height: 100vh;
}
a { color: var(--green); text-decoration: none; }
a:hover { text-decoration: underline; }

/* HEADER */
.header {
    background: var(--bg2);
    border-bottom: 2px solid var(--accent);
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
}
.header h1 {
    font-size: 18px;
    font-weight: 600;
    color: var(--green);
    flex-shrink: 0;
}
.header h1 span { color: var(--accent); }
.header .status-pill {
    font-size: 11px;
    padding: 3px 10px;
    border-radius: var(--radius-pill);
    background: var(--bg3);
    border: 1px solid var(--border);
}
.header .status-pill.connected { border-color: var(--green); color: var(--green); }
.header .spacer { flex: 1; }
.header .refresh-btn {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 14px;
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 12px;
}
.header .refresh-btn:hover { border-color: var(--accent); }

/* LAYOUT */
.container {
    max-width: 1100px;
    margin: 0 auto;
    padding: 16px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}
@media (max-width: 768px) { .container { grid-template-columns: 1fr; } }

/* CARDS */
.card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
}
.card-header {
    background: var(--bg3);
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    font-weight: 600;
    font-size: 13px;
    color: var(--green);
    display: flex;
    align-items: center;
    gap: 8px;
}
.card-body { padding: 14px; }
.card.full-width { grid-column: 1 / -1; }
.swatch { display:inline-block; width:14px; height:14px; border-radius:3px; border:1px solid var(--border); vertical-align:middle; }
.stage-grid { display:flex; flex-wrap:wrap; gap:12px; }
.stage-tile { width:150px; text-align:center; font-size:12px; }
.stage-box { position:relative; height:84px; border-radius:10px; border:4px solid #5a5a5a; margin-bottom:4px; }
.stage-box .sim { position:absolute; top:5px; left:5px; background:rgba(0,0,0,.6); color:#e6e6e6; font-size:10px; padding:1px 5px; border-radius:4px; }
.stage-box .unknown { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#ccc; font-size:20px; }
.stage-name { color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.stage-box .hb { position:absolute; top:5px; right:5px; background:rgba(0,0,0,.6); border-radius:4px; padding:3px 4px; display:flex; flex-direction:column; gap:2px; }
.stage-box .hb i { display:block; width:10px; height:3px; background:#555; }
.stage-box .hb i.on { background:#ebebeb; }
.stage-box .aim { position:absolute; bottom:4px; right:6px; color:#fff; font-size:13px; text-shadow:0 0 3px #000; }
.stage-cam { display:flex; justify-content:center; align-items:center; color:#888; font-size:11px; gap:4px; }
.pos-aim { display:grid; grid-template-columns:repeat(3, 26px); gap:2px; margin-top:4px; }
.pos-aim button { height:24px; padding:0; border:1px solid var(--border); background:var(--bg3); color:#bbb; border-radius:4px; cursor:pointer; }
.pos-aim button.sel { background:var(--accent); color:#fff; border-color:#8fb0ff; }
.settings-cols { display:grid; grid-template-columns:repeat(auto-fit, minmax(380px, 1fr)); gap:18px; }
.settings-cols h4 { margin:12px 0 6px; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.5px; }
.stage-plan { display:grid; grid-template-columns:auto repeat(3, minmax(160px, auto)); gap:6px; align-items:stretch; }
.stage-plan .ph { color:var(--muted); font-size:11px; text-align:center; }
.stage-plan .pr { color:var(--muted); font-size:11px; display:flex; align-items:center; justify-content:flex-end; padding-right:4px; }
.stage-plan .pc { border:1px dashed #3a3a4a; border-radius:6px; padding:6px; display:flex; gap:8px; justify-content:center; align-items:flex-start; min-height:140px; }
.stage-plan .you { color:#666; font-size:12px; align-self:center; }
.pos-picker { display:flex; gap:10px; align-items:flex-start; }
.pos-grid { display:grid; grid-template-columns:auto repeat(3, 84px); gap:3px; font-size:11px; }
.pos-grid .ph { color:var(--muted); text-align:center; }
.pos-grid .pr { color:var(--muted); display:flex; align-items:center; padding-right:4px; }
.pos-cell, .pos-h { min-height:44px; border:1px solid var(--border); background:var(--bg3); color:#888; border-radius:var(--radius); font-size:11px; cursor:pointer; padding:2px; overflow:hidden; white-space:pre-line; line-height:1.25; }
.pos-cell.has { color:#bbb; }
.pos-cell.sel, .pos-h.sel { background:var(--accent); color:#fff; font-weight:bold; border-color:#8fb0ff; }
.pos-hcol { display:flex; flex-direction:column; gap:3px; font-size:11px; }
.pos-h { min-height:30px; width:80px; }
.btn.unsaved { background:#c77d12; color:#fff; border-color:#c77d12; font-weight:bold; }
.stage-detail { color:var(--muted); }
.layer-base { border-color:#5a5a5a; } .layer-sound { border-color:#3cc8a0; } .layer-show { border-color:#468cff; } .layer-effect { border-color:#ffa028; } .layer-override { border-color:#eb4646; }
.seq-progress { height:8px; background:var(--bg3); border-radius:4px; cursor:pointer; margin:8px 0 4px; }
.seq-progress > div { height:100%; width:0; background:var(--accent); border-radius:4px; }
.form-grid { display:grid; grid-template-columns: 170px 1fr; gap:6px 10px; align-items:center; font-size:13px; }
.form-grid input[type=number] { width:80px; }
.form-grid .hint { grid-column: 2; color:var(--muted); font-size:11px; margin-top:-4px; }
.modal-bg { position:fixed; inset:0; background:rgba(0,0,0,.7); display:none; align-items:center; justify-content:center; z-index:50; }
.modal-bg.open { display:flex; }
.modal { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:14px; max-width:95vw; max-height:94vh; overflow:auto; }
#presetModal .modal, #animModal .modal { min-height:min(85vh, 1000px); }
.modal.wide { width:min(1100px, 95vw); }
.modal.full { width:97vw; height:94vh; max-height:94vh; display:flex; flex-direction:column; overflow:hidden; }
.modal h3 { margin:0 0 10px; color:var(--accent); }
.modal-title { display:flex; align-items:center; gap:8px; margin-bottom:10px; flex-wrap:wrap; }
.modal-title b { font-size:15px; }
.toolbar { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-bottom:6px; font-size:12px; }
.toolbar input[type=number], .toolbar select { width:auto; }
.toolbar input[type=text] { width:220px; }
.btn.small { padding:3px 9px; font-size:11px; }
.snd-row { display:flex; align-items:center; gap:6px; margin:3px 0; font-size:12px; }
.snd-row > label:first-child { min-width:70px; color:var(--muted); }
.snd-row select, .snd-row input[list] { flex:1; min-width:0; }
.snd-row input[type=range] { flex:1; }
.snd-row input[type=number] { width:64px; }
.snd-swatch { display:inline-block; width:18px; height:18px; border:1px solid #666; border-radius:3px; }
.snd-part { flex-wrap:wrap; border-top:1px solid var(--border); padding-top:3px; }
.snd-part input[list] { flex:2; min-width:150px; }
.snd-meter { display:flex; align-items:center; gap:6px; font-size:11px; margin:2px 0; }
.snd-meter span { min-width:120px; color:var(--muted); }
.snd-meter > div { flex:1; height:8px; background:var(--border); border-radius:4px; overflow:hidden; }
.snd-meter > div > div { height:100%; background:#3cc8a0; }
.popup-menu { position:fixed; z-index:80; background:var(--bg2); border:1px solid var(--border); border-radius:6px; padding:4px 0; min-width:200px; box-shadow:0 6px 20px rgba(0,0,0,.5); }
.popup-menu div { padding:6px 14px; cursor:pointer; font-size:13px; }
.popup-menu div:hover { background:var(--accent); color:white; }
.popup-menu div.disabled { color:var(--muted); pointer-events:none; }
.popup-menu hr { border:0; border-top:1px solid var(--border); margin:4px 0; }
.edit-table { width:100%; border-collapse:collapse; font-size:12px; }
.edit-table th { text-align:left; color:var(--muted); font-weight:600; padding:4px; border-bottom:1px solid var(--border); }
.edit-table td { padding:3px 4px; border-bottom:1px solid var(--border); }
.edit-table tr.selected td { background:rgba(91,141,239,.18); }
.edit-table input[type=number] { width:70px; }
.edit-table select { width:auto; min-width:90px; }
.tabs { display:flex; gap:2px; border-bottom:1px solid var(--border); margin-bottom:8px; }
.tabs div { padding:6px 14px; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent; }
.tabs div.active { color:var(--accent); border-bottom-color:var(--accent); }
textarea.json { width:100%; min-height:320px; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:4px; font-family:monospace; font-size:12px; padding:8px; box-sizing:border-box; }
.tl-wrap { display:flex; gap:10px; flex:1; min-height:0; }
.tl-main { flex:1; display:flex; flex-direction:column; min-width:0; overflow:auto; }
.tl-props { width:290px; flex-shrink:0; overflow:auto; border-left:1px solid var(--border); padding-left:10px; font-size:12px; }
.tl-props .form-grid { grid-template-columns: 95px 1fr; }
#tlCanvas { display:block; width:100%; cursor:default; outline:none; }
.tl-status { font-size:12px; min-height:16px; margin-top:4px; }
.tl-hint { color:var(--muted); font-size:11px; margin:4px 0 8px; }

/* LIGHT TABLE */
.light-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}
.light-table th {
    text-align: left;
    padding: 8px 10px;
    background: var(--bg3);
    color: var(--green);
    border-bottom: 1px solid var(--accent);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.light-table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
}
.light-table tr:hover td { background: rgba(145, 0, 255, 0.08); }
.light-table .linked { color: var(--green); font-weight: 600; }
.light-table .not-linked { color: var(--muted); }
.light-table .light-id {
    color: var(--accent);
    font-weight: 700;
    font-size: 14px;
    width: 30px;
    text-align: center;
}

/* CONTROLS */
.control-group { margin-bottom: 14px; }
.control-group:last-child { margin-bottom: 0; }
.control-group label {
    display: block;
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}
.slider-row {
    display: flex;
    align-items: center;
    gap: 10px;
}
.slider-row input[type="range"] {
    flex: 1;
    accent-color: var(--accent);
    height: 6px;
}
.slider-row .val {
    width: 50px;
    text-align: right;
    font-weight: 600;
    font-family: monospace;
    font-size: 13px;
    color: var(--accent);
}
select, input[type="number"], input[type="text"] {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 5px 8px;
    font-size: 12px;
    width: 100%;
}
select:focus, input:focus { border-color: var(--accent); outline: none; }

/* BUTTONS */
.btn {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 7px 16px;
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    transition: all 0.15s;
}
.btn:hover { border-color: var(--accent); background: #2a2a4a; }
.btn:active { background: var(--accent); color: white; }
.btn.primary { background: var(--accent); color: white; border-color: var(--accent-dim); }
.btn.primary:hover { background: #a933ff; }
.btn.success { border-color: var(--green-dim); color: var(--green); }
.btn.success:hover { background: var(--green-dim); color: var(--bg); }
.btn.danger { border-color: var(--red); color: var(--red); }
.btn.danger:hover { background: var(--red); color: white; }
.btn-row { display: flex; gap: 6px; flex-wrap: wrap; }
.btn-row .btn { flex: 1; text-align: center; }

/* SCENE GRID */
.scene-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
}
.scene-btn {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 10px 6px;
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 11px;
    text-align: center;
    line-height: 1.3;
    transition: all 0.15s;
}
.scene-btn:hover { border-color: var(--accent); }
.scene-btn.active { background: var(--green); color: var(--bg); border-color: var(--green-dim); font-weight: 600; }

/* PRESET BUTTONS */
.preset-btn {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    padding: 8px 4px;
    cursor: pointer;
    text-align: center;
    font-size: 11px;
    line-height: 1.3;
    transition: all 0.15s;
    min-height: 50px;
}
.preset-btn:hover { border-color: var(--accent); transform: translateY(-1px); }
.preset-btn .preset-num { font-size: 16px; font-weight: 700; color: var(--accent); display: block; }
.preset-btn.custom-global { border-color: #5b8def; background: rgba(91,141,239,0.12); }
.preset-btn.custom-snap { border-color: var(--green); background: rgba(76,175,80,0.12); }

/* ANIMATIONS LIST */
.anim-list {
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 10px;
}
.anim-item {
    padding: 8px 10px;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    transition: background 0.1s;
}
.anim-item:hover { background: rgba(145, 0, 255, 0.1); }
.anim-item.selected { background: var(--accent); color: white; }
.anim-item.selected span { color: rgba(255,255,255,.85) !important; }
.anim-item:last-child { border-bottom: none; }

/* MODE TABS */
.mode-tabs {
    display: flex;
    border-bottom: 2px solid var(--border);
    margin-bottom: 14px;
}
.mode-tab {
    padding: 8px 18px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.15s;
}
.mode-tab:hover { color: var(--text); }
.mode-tab.active {
    color: var(--green);
    border-color: var(--accent);
}
.mode-pane { display: none; }
.mode-pane.active { display: block; }

/* LOG */
.log {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 10px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    max-height: 150px;
    overflow-y: auto;
    color: var(--muted);
}
.log .ok { color: var(--green); }
.log .err { color: var(--red); }

/* API DOCS */
.api-section { margin-bottom: 12px; }
.api-section h3 { font-size: 13px; color: var(--accent); margin-bottom: 6px; }
.api-code {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 6px 10px;
    font-family: monospace;
    font-size: 11px;
    color: var(--green);
    word-break: break-all;
    margin: 4px 0;
}
.api-desc { font-size: 12px; color: var(--muted); margin-bottom: 4px; }

/* Scrollbar */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--bg2); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: var(--radius); }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }
</style>
</head>
<body>

<div class="header">
    <h1><span>Neewer</span>Lux <small style="color:#888;font-size:12px">{NLVERSION}</small></h1>
    <div class="spacer"></div>
    <span class="status-pill" id="connStatus">Loading...</span>
    <button class="refresh-btn" onclick="scanForLights()" title="Scan for new Bluetooth lights">Scan</button>
    <button class="refresh-btn" onclick="linkAllLights()" title="Link to all discovered lights">Link All</button>
    <button class="refresh-btn" onclick="openSettings()" title="Light and global preferences">Settings</button>
    <button class="refresh-btn" onclick="refreshAll()">&#x21BB; Refresh</button>
</div>

<div class="container">
    <!-- LIGHTS -->
    <div class="card full-width">
        <div class="card-header">Lights</div>
        <div class="card-body" style="padding:0">
            <table class="light-table">
                <thead><tr><th>#</th><th></th><th>Light Name</th><th>MAC Address</th><th>Status</th><th>Role</th><th>Layer</th><th>Current</th><th>Actions</th></tr></thead>
                <tbody id="lightTableBody"><tr><td colspan="9" style="text-align:center;padding:20px;color:#888">Loading lights...</td></tr></tbody>
            </table>
        </div>
    </div>

    <!-- STAGE -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="toggleStage(this)">Stage <span style="float:right;color:var(--muted);font-size:11px;font-weight:normal">click to hide/show</span></div>
        <div class="card-body" id="stageBody">
            <div style="font-size:12px;color:var(--muted);margin-bottom:8px">View <select id="stageView" onchange="setStageView(this.value)"><option value="plan">Plan (from above)</option><option value="height">Height (facing the camera)</option><option value="strip">Strip (sweep order)</option></select>
            <span style="margin-left:8px">Plan: where each light stands, from your seat facing the camera; bars = height, arrow = where it points (none = at you).</span></div>
            <div class="stage-grid" id="stageGrid"><div style="color:var(--muted)">Loading...</div></div>
            <div style="color:var(--muted);font-size:11px;margin-top:8px">Approximate colours. Outline: grey = manual/preset, teal = sound mode, blue = sequence, orange = effect, red = override animation.
            Simulated lights show what they received; real lights show what was last sent to them.</div>
        </div>
    </div>

    <!-- PRESETS -->
    <div class="card full-width">
        <div class="card-header">Custom Presets</div>
        <div class="card-body">
            <div id="presetGrid" style="display:grid;grid-template-columns:repeat(8,1fr);gap:6px;max-height:140px;overflow-y:auto;">
                <div style="color:#888;grid-column:1/-1;text-align:center;padding:10px;">Loading presets...</div>
            </div>
        </div>
    </div>

    <!-- CONTROL PANEL -->
    <div class="card">
        <div class="card-header">Light Control</div>
        <div class="card-body">
            <div class="control-group">
                <label>Target Light</label>
                <select id="targetLight"><option value="*">All Lights</option></select>
            </div>

            <div class="mode-tabs">
                <div class="mode-tab active" onclick="switchMode('cct')">CCT</div>
                <div class="mode-tab" onclick="switchMode('hsi')">HSI</div>
                <div class="mode-tab" onclick="switchMode('scene')">Scene</div>
            </div>

            <!-- CCT -->
            <div class="mode-pane active" id="pane-cct">
                <div class="control-group">
                    <label>Color Temperature</label>
                    <div class="slider-row">
                        <span style="font-size:11px;color:#ff9329">3200K</span>
                        <input type="range" id="cctTemp" min="32" max="56" value="56">
                        <span style="font-size:11px;color:#c9e2ff">5600K</span>
                        <span class="val" id="cctTempVal">5600K</span>
                    </div>
                </div>
                <div class="control-group">
                    <label>Brightness</label>
                    <div class="slider-row">
                        <input type="range" id="cctBri" min="0" max="100" value="100">
                        <span class="val" id="cctBriVal">100%</span>
                    </div>
                </div>
                <button class="btn primary" style="width:100%" onclick="sendCCT()">Apply CCT</button>
            </div>

            <!-- HSI -->
            <div class="mode-pane" id="pane-hsi">
                <div class="control-group">
                    <label>Hue</label>
                    <div class="slider-row">
                        <input type="range" id="hsiHue" min="0" max="360" value="240">
                        <span class="val" id="hsiHueVal">240&deg;</span>
                    </div>
                </div>
                <div class="control-group">
                    <label>Saturation</label>
                    <div class="slider-row">
                        <input type="range" id="hsiSat" min="0" max="100" value="100">
                        <span class="val" id="hsiSatVal">100%</span>
                    </div>
                </div>
                <div class="control-group">
                    <label>Intensity</label>
                    <div class="slider-row">
                        <input type="range" id="hsiBri" min="0" max="100" value="100">
                        <span class="val" id="hsiBriVal">100%</span>
                    </div>
                </div>
                <div id="huePreview" style="height:8px;border-radius: var(--radius);margin-bottom:10px;background:hsl(240,100%,50%)"></div>
                <button class="btn primary" style="width:100%" onclick="sendHSI()">Apply HSI</button>
            </div>

            <!-- SCENE -->
            <div class="mode-pane" id="pane-scene">
                <div class="scene-grid" id="sceneGrid">
                    <button class="scene-btn" onclick="sendScene(1,this)">1 - Police A<br>(Red/Blue)</button>
                    <button class="scene-btn" onclick="sendScene(2,this)">1 - Police B<br>(Red)</button>
                    <button class="scene-btn" onclick="sendScene(3,this)">1 - Police C<br>(Blue)</button>
                    <button class="scene-btn" onclick="sendScene(4,this)">2 - Party A<br>(All)</button>
                    <button class="scene-btn" onclick="sendScene(5,this)">2 - Party B<br>(Green)</button>
                    <button class="scene-btn" onclick="sendScene(6,this)">2 - Party C<br>(Blue)</button>
                    <button class="scene-btn" onclick="sendScene(7,this)">3 - Lightning A<br>(All)</button>
                    <button class="scene-btn" onclick="sendScene(8,this)">3 - Lightning B<br>(Green)</button>
                    <button class="scene-btn" onclick="sendScene(9,this)">3 - Lightning C<br>(Blue)</button>
                </div>
                <div class="control-group" style="margin-top:10px">
                    <label>Scene Brightness</label>
                    <div class="slider-row">
                        <input type="range" id="sceneBri" min="0" max="100" value="100">
                        <span class="val" id="sceneBriVal">100%</span>
                    </div>
                </div>
            </div>

            <div class="btn-row" style="margin-top:12px">
                <button class="btn success" onclick="sendPower('on')">On</button>
                <button class="btn danger" onclick="sendPower('off')">Off</button>
            </div>
        </div>
    </div>

    <!-- ANIMATIONS -->
    <div class="card">
        <div class="card-header">Animations</div>
        <div class="card-body">
            <div class="anim-list" id="animList">
                <div class="anim-item" style="color:#888">Loading...</div>
            </div>
            <div id="selectedAnimLabel" style="padding:4px 8px;font-size:12px;color:var(--accent);font-weight:600;text-align:center;border-top:1px solid var(--border);">No animation selected</div>
            <div class="control-group">
                <label>Speed / Rate / Brightness</label>
                <div style="display:flex;gap:6px">
                    <select id="animSpeed"><option>0.25x</option><option>0.5x</option><option selected>1x</option><option>1.5x</option><option>2x</option><option>3x</option></select>
                    <input type="number" id="animRate" value="5" min="1" max="30" style="width:60px" title="Updates/sec">
                    <input type="number" id="animBri" value="100" min="5" max="100" style="width:60px" title="Brightness %">
                </div>
            </div>
            <div class="control-group">
                <label style="display:flex;align-items:center;gap:6px;text-transform:none;color:var(--text)">
                    <input type="checkbox" id="animLoop"> Loop animation
                </label>
                <div style="display:flex;align-items:center;gap:6px;margin-top:4px">
                    <label style="text-transform:none;color:var(--muted);font-size:12px">Loops:</label>
                    <input type="number" id="animLoopCount" value="0" min="0" max="999" style="width:60px" title="0 = infinite, N = play N times">
                    <span style="color:var(--muted);font-size:11px">(0 = forever)</span>
                </div>
                <label style="display:flex;align-items:center;gap:6px;text-transform:none;color:var(--text);margin-top:4px">
                    <input type="checkbox" id="animRevert" checked> Revert lights on finish
                </label>
                <label style="display:flex;align-items:center;gap:6px;text-transform:none;color:var(--text);margin-top:4px" title="Send to all lights at once (synchronized). Off: one light at a time, as before 1.3.1.">
                    <input type="checkbox" id="animParallel" checked> Parallel (synchronized send)
                </label>
            </div>
            <div class="btn-row">
                <button class="btn success" onclick="playAnimation()">&#x25B6; Play</button>
                <button class="btn danger" onclick="stopAnimation()">&#x25A0; Stop</button>
            </div>
            <div class="btn-row" style="margin-top:6px">
                <button class="btn small" onclick="animNew()">+ New</button>
                <button class="btn small" onclick="animEdit()">Edit</button>
                <button class="btn small" onclick="animDuplicate()">Duplicate</button>
                <button class="btn small" onclick="animDelete()">Delete</button>
            </div>
            <div class="btn-row" style="margin-top:6px">
                <button class="btn small" onclick="animExport()" title="Download the selected animation as a JSON file">Export</button>
                <button class="btn small" onclick="document.getElementById('animImportFile').click()" title="Add an animation from a JSON file">Import</button>
                <button class="btn small" onclick="animReload()" title="Reload animation files from light_prefs/animations">Reload</button>
                <input type="file" id="animImportFile" accept=".json,application/json" style="display:none" onchange="animImport(this)">
            </div>
        </div>
    </div>

    <!-- SEQUENCES -->
    <div class="card">
        <div class="card-header">Sequences</div>
        <div class="card-body">
            <div class="anim-list" id="seqList"><div class="anim-item" style="color:#888">Loading...</div></div>
            <div id="seqStatus" style="padding:6px 8px;font-size:12px;color:var(--accent);font-weight:600;text-align:center;border-top:1px solid var(--border);">No sequence playing</div>
            <div class="seq-progress" id="seqProgress" title="Click to seek" onclick="seqSeek(event)"><div id="seqProgressFill"></div></div>
            <div class="btn-row">
                <button class="btn success" onclick="seqPlay()" title="Play the selected sequence from the start">&#x25B6; Play</button>
                <button class="btn" id="seqPauseBtn" onclick="seqPauseResume()" title="Pause returns the lights to where they were; Resume carries on">Pause</button>
                <button class="btn danger" onclick="seqCmd('stop')">&#x25A0; Stop</button>
            </div>
            <div class="btn-row" style="margin-top:6px">
                <button class="btn" onclick="seqRender()" title="Show what the selected sequence does to each light, without playing it">Render</button>
                <button class="btn" onclick="seqReload()" title="Reload sequence files from light_prefs/sequences">Reload</button>
            </div>
            <div class="btn-row" style="margin-top:6px">
                <button class="btn small" onclick="tlNewMenu(event)" title="Open the timeline editor on a new sequence, blank or from a starter">+ New</button>
                <button class="btn small" onclick="tlOpenSelected()" title="Open the selected sequence in the timeline editor">Edit</button>
                <button class="btn small" onclick="seqDuplicate()">Duplicate</button>
                <button class="btn small" onclick="seqDelete()">Delete</button>
            </div>
            <div style="color:var(--muted);font-size:11px;margin-top:8px">Sliders and presets don't interrupt a playing sequence: they become what the lights return to when it ends.</div>
        </div>
    </div>

    <!-- SOUND -->
    <div class="card" id="soundCard">
        <div class="card-header">Sound</div>
        <div class="card-body">
            <div id="sndUnavailable" style="display:none;color:var(--muted);font-size:12px"></div>
            <div id="sndControls">
                <div class="snd-row"><label>Listen to</label><select id="sndDevice" onchange="sndSetDevice(this.value)" title="What an output plays (loopback), or an input such as a microphone or audio interface"></select>
                    <button class="btn small" onclick="sndDevices()" title="List the audio devices again">Refresh</button></div>
                <div class="snd-row"><label>Mode</label><select id="sndMode" onchange="sndModeChosen(this.value)"></select></div>
                <div id="sndDesc" style="color:var(--muted);font-size:11px;margin:2px 0 6px"></div>
                <div class="btn-row">
                    <button class="btn success" onclick="sndStart()">&#x25B6; Start</button>
                    <button class="btn danger" id="sndStopBtn" onclick="sndStop()">&#x25A0; Stop</button>
                </div>
                <div id="sndStatus" style="padding:6px 0;font-size:12px;color:var(--accent);font-weight:600;text-align:center">Not playing</div>
                <div id="sndMeters"></div>
                <div id="sndTempo" style="font-size:12px;color:var(--muted);margin-bottom:6px">Tempo: -</div>
                <div id="sndSliders"></div>
                <div class="snd-row"><label>Palette</label><select id="sndPalKind" onchange="sndPaletteKind(this.value)"><option value="hsi">Colours</option><option value="cct">White (Kelvin)</option></select>
                    <button class="btn small" onclick="sndPaletteAdd()">+ Colour</button></div>
                <div id="sndPalette"></div>
                <div style="font-size:12px;margin:6px 0 2px">Lights and what drives them</div>
                <div id="sndParts"></div>
                <datalist id="sndTargets"><option value="@rim;@background;@practical"><option value="@all"><option value="@key"><option value="@fill"><option value="@rim"><option value="@background"><option value="@practical"><option value="@front"><option value="@back"><option value="@left"><option value="@right"><option value="@high"><option value="@low"></datalist>
                <div class="btn-row" style="margin-top:6px">
                    <button class="btn small" onclick="sndPartAdd()" title="Add a group of lights (by role, position or number)">+ Lights</button>
                    <button class="btn small" onclick="sndSave()">Save</button>
                    <button class="btn small" onclick="sndSaveAs()">Save as</button>
                    <button class="btn small" onclick="sndRevert()" title="Go back to the saved mode">Revert</button>
                    <button class="btn small" onclick="sndDelete()">Delete</button>
                </div>
                <div style="color:var(--muted);font-size:11px;margin-top:8px">A sound mode plays under sequences and effects. A preset or slider on one of its lights stops it; switching a light off takes just that light out.</div>
            </div>
        </div>
    </div>

    <!-- SETTINGS -->
    <div class="card full-width" id="settingsCard">
        <div class="card-header" style="cursor:pointer" onclick="toggleSettings(this)">Settings <span style="float:right;color:var(--muted);font-size:11px;font-weight:normal">light and global preferences</span></div>
        <div class="card-body" id="settingsBody" style="display:none">
            <h3 style="margin-top:0;color:var(--accent)">Light Preferences</h3>
            <div class="form-grid"><label>Light</label><select id="lpLight" onchange="fillLightPrefs()"></select></div>
            <div class="settings-cols">
                <div>
                    <h4>This light</h4>
                    <div class="form-grid">
                        <label>Custom name</label><input type="text" id="lpName" maxlength="64" placeholder="(model name)">
                        <label>Preferred ID</label><input type="number" id="lpID" min="0" max="99"><div class="hint">0 = automatic. Used in URLs and batch commands.</div>
                        <label>Colour temperature range</label><span><input type="number" id="lpTempMin" min="1000" max="5600" step="100"> to <input type="number" id="lpTempMax" min="1000" max="10000" step="100"> K <button class="btn" style="padding:2px 8px;font-size:11px" onclick="resetTempRange()">Default</button></span>
                        <label>CCT-only light</label><label style="text-transform:none"><input type="checkbox" id="lpCCTOnly"> Only accepts CCT (older lights)</label>
                    </div>
                    <h4>Limits</h4>
                    <div class="form-grid">
                        <label>Max brightness</label><input type="number" id="lpMaxBri" min="-1" max="100"><div class="hint">-1 = use the global limit.</div>
                        <label>Min brightness</label><input type="number" id="lpMinBri" min="-1" max="100"><div class="hint">-1 = use the global limit.</div>
                        <label>Locked</label><label style="text-transform:none"><input type="checkbox" id="lpLocked"> Ignore sequences and effects</label>
                        <label>Eye line</label><label style="text-transform:none"><input type="checkbox" id="lpEyeline"> In my eye line (a light I look into; @eyeline)</label>
                    </div>
                </div>
                <div>
                    <h4>In sequences and effects</h4>
                    <div class="form-grid">
                        <label>Role</label><select id="lpRole" title="Key: main light on you. Fill: softens the key's shadows. Rim / back: behind you, outlines you. Background: lights the wall or set behind you. Practical: a light that is visible in shot. Lights without a role count as Background."></select>
                        <label>Sweep order</label><input type="number" id="lpOrder" min="0" max="99"><div class="hint">0 = automatic (left to right, front to back, low to high).</div>
                    </div>
                    <div style="margin-top:8px;color:var(--muted);font-size:12px">Position, height and aim (from your seat, facing the camera)</div>
                    <div class="pos-picker" id="lpPos" style="margin-top:6px"></div>
                </div>
            </div>
            <div class="btn-row" style="margin-top:10px"><button class="btn primary" onclick="saveLightPrefs()">Save Light Preferences</button></div>

            <h3 style="color:var(--accent);margin-top:22px">Global Preferences</h3>
            <div class="settings-cols">
                <div>
                    <h4>Safety</h4>
                    <div class="form-grid">
                        <label>Flash guard</label><label style="text-transform:none"><input type="checkbox" id="gpFlashGuard" onchange="gpFlashGuardChanged(this)"> At most 3 flashes a second per light (recommended)</label><div class="hint">The WCAG limit for photosensitive seizures. Applies to everything except the desktop's sliders.</div>
                        <label>Eye-line lights during flashes</label><select id="gpEyelineFlash"><option value="same">Same as other lights</option><option value="gentler">Gentler: at most 1 flash a second</option><option value="calm">Calm: one change every 2 seconds</option></select><div class="hint">For lights marked "In my eye line". Applies even with the flash guard off.</div>
                        <label>Max brightness</label><input type="number" id="gpEnvMax" min="1" max="100"><div class="hint">Presets, URLs, animations and sequences. Sliders are exempt.</div>
                        <label>Min brightness</label><input type="number" id="gpEnvMin" min="0" max="100">
                    </div>
                    <h4>Playback</h4>
                    <div class="form-grid">
                        <label>Fade in (ms)</label><input type="number" id="gpFadeIn" min="0" max="5000" step="100"><div class="hint">When a preset is recalled, or an animation or sequence takes lights over (including one animation replacing another). 0 = cut.</div>
                        <label>Fade back (ms)</label><input type="number" id="gpHandback" min="0" max="5000" step="100"><div class="hint">When an effect, sequence or animation lets go of a light, fade to what comes next. 0 = cut. Each preset, animation and sequence can set its own; the desktop sliders stay instant.</div>
                        <label>Sequence frame rate</label><input type="number" id="gpSeqFps" min="1" max="30"><div class="hint">Updates per second for sequences without their own.</div>
                        <label>Effect time limit (s)</label><input type="number" id="gpEffectMax" min="1" max="600"><div class="hint">Forever-looping effects stop after this.</div>
                    </div>
                </div>
                <div>
                    <h4>Your rig</h4>
                    <div class="form-grid">
                        <label>Main camera</label><select id="gpCamera"><option value="front">Front (straight ahead)</option><option value="front-left">Front left</option><option value="front-right">Front right</option><option value="left">Your left</option><option value="right">Your right</option><option value="back-left">Back left</option><option value="back">Behind you</option><option value="back-right">Back right</option></select><div class="hint">Shown on the Stage plan. Positions stay relative to you.</div>
                        <label>Global CCT range</label><span><input type="number" id="gpCCTMin" min="2700" max="8500" step="100"> to <input type="number" id="gpCCTMax" min="2700" max="8500" step="100"> K</span>
                        <label>Colour on CCT-only lights</label><select id="gpFallback"><option value="convert">Convert to white</option><option value="ignore">Ignore</option></select>
                    </div>
                    <h4>Simulation</h4>
                    <div class="form-grid">
                        <label>Simulated lights</label><select id="gpSim"></select><div class="hint">Takes effect at the next start.</div>
                        <label>Simulated CCT-only light</label><label style="text-transform:none"><input type="checkbox" id="gpSimCCT"> Add one (takes effect at the next start)</label>
                    </div>
                </div>
            </div>
            <div class="btn-row" style="margin-top:10px"><button class="btn primary" id="gpSaveBtn" onclick="saveGlobalPrefs()">Save Global Preferences</button></div>
            <div style="color:var(--muted);font-size:11px;margin-top:8px">Network access, keyboard shortcuts and startup options are only changed in the desktop app.</div>
        </div>
    </div>

    <!-- COMMAND LOG (collapsible) -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            Command Log
        </div>
        <div class="card-body" style="padding:8px">
            <div class="log" id="commandLog" style="max-height:150px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.6"></div>
        </div>
    </div>

    <!-- INFO (collapsible) -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            About NeewerLux
        </div>
        <div class="card-body" style="display:none">
            <h3 style="color:var(--accent);margin-top:0">NeewerLux {NLVERSION}</h3>
            <p>This dashboard controls the same lights as the desktop app, over HTTP.
            Anything here can also be driven by a plain URL, which is how hardware like a
            Stream Deck talks to it. See the API Reference below for the full list.</p>
            <p style="color:var(--muted)">Presets (right-click one), animations and sequences can be
            edited here as on the desktop. Network access, keyboard shortcuts and startup options
            are only changed in the desktop app.</p>
            <hr style="border-color:var(--border)">
            <div id="updateCheckArea">
                <button class="btn" onclick="checkForUpdates()">Check for Updates</button>
                <span id="updateResult" style="margin-left:10px;font-size:12px;"></span>
            </div>
            <hr style="border-color:var(--border)">
            <p style="color:var(--muted);font-size:0.9em;">
                <b>Repository:</b> <a href="https://github.com/poizenjam/NeewerLux/" style="color:var(--accent)">github.com/poizenjam/NeewerLux</a><br>
                <b>Releases:</b> <a href="https://github.com/poizenjam/NeewerLux/releases" style="color:var(--accent)">github.com/poizenjam/NeewerLux/releases</a><br><br>
                Based on <a href="https://github.com/taburineagle/NeewerLite-Python/" style="color:var(--accent)">NeewerLite-Python</a> (v0.12d) by Zach Glenwright.
                Originally from <a href="https://github.com/keefo/NeewerLite" style="color:var(--accent)">NeewerLite</a> by Xu Lian
            </p>
        </div>
    </div>

    <!-- API REFERENCE (collapsible) -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            API Reference
        </div>
        <div class="card-body" style="display:none">
            <div class="api-section">
                <h3>Light Control</h3>
                <div class="api-desc">Set CCT mode</div>
                <div class="api-code">GET /NeewerLux/doAction?light=1&amp;mode=CCT&amp;temp=5600&amp;bri=80</div>
                <div class="api-desc">Set HSI mode</div>
                <div class="api-code">GET /NeewerLux/doAction?light=1&amp;mode=HSI&amp;hue=240&amp;sat=100&amp;bri=50</div>
                <div class="api-desc">Set Scene mode</div>
                <div class="api-code">GET /NeewerLux/doAction?light=1&amp;mode=SCENE&amp;scene=3&amp;bri=80</div>
            </div>
            <div class="api-section">
                <h3>Batch Commands</h3>
                <div class="api-desc">Different settings per light in one request</div>
                <div class="api-code">GET /NeewerLux/doAction?batch=Key:HSI:0:100:50;Fill:CCT:56:80</div>
                <div class="api-desc">Lights can be addressed by index, alias name, or MAC address</div>
                <div class="api-desc">JSON batch (temperature in Kelvin or hundreds of Kelvin). Commands for the same light coalesce: the latest wins, nothing is refused as busy.</div>
                <div class="api-code">POST /NeewerLux/batch {"commands":[{"light":"1","mode":"CCT","temp":5600,"bri":80},{"light":"@rim","mode":"HSI","hue":300,"sat":100,"bri":60}]}</div>
                <div class="api-desc">Structured state of every light, with apiVersion (see docs/HTTP_API.md)</div>
                <div class="api-code">GET /NeewerLux/doAction?list_json</div>
            </div>
            <div class="api-section">
                <h3>Animations</h3>
                <div class="api-desc">Play by name (GET). Format: <code>Name|speed|rate|bri|loop|maxLoops|revert</code></div>
                <div class="api-code">GET /NeewerLux/doAction?animate=Concert%20Sweep|1.0|10|80</div>
                <div class="api-desc">With loop control: play twice then revert</div>
                <div class="api-code">GET /NeewerLux/doAction?animate=Halloween|1.0|10|50|true|2|true</div>
                <div class="api-desc">Play/stop/list (POST JSON)</div>
                <div class="api-code">POST /NeewerLux/animate {"action":"play","name":"Concert Sweep","loop":true,"maxLoops":3,"revert":true}</div>
                <div class="api-code">POST /NeewerLux/animate {"action":"stop"}</div>
            </div>
            <div class="api-section">
                <h3>Sequences</h3>
                <div class="api-desc">Play, pause, resume, stop, seek (GET)</div>
                <div class="api-code">GET /NeewerLux/doAction?sequence=play|Example%20-%20Four%20Light%20Demo</div>
                <div class="api-desc">JSON API: list, reload, play, pause, resume, stop, seek, set_position, status, validate, save, render</div>
                <div class="api-code">POST /NeewerLux/sequence {"action":"play","name":"Example - Four Light Demo"}</div>
                <div class="api-code">POST /NeewerLux/sequence {"action":"seek","ms":12000}</div>
                <div class="api-code">POST /NeewerLux/sequence {"action":"render","name":"Example - Four Light Demo","format":"png"}</div>
                <div class="api-desc">Live status of layers, the sequence and every light (with approximate colour)</div>
                <div class="api-code">GET /NeewerLux/doAction?status_json</div>
            </div>
            <div class="api-section">
                <h3>Sound modes</h3>
                <div class="api-desc">Lights following live audio: start, switch, stop (GET)</div>
                <div class="api-code">GET /NeewerLux/doAction?sound=start|Pulse</div>
                <div class="api-desc">JSON API: start, stop, mode, set, device, devices, status (with live levels and tempo), list, get, save, delete, validate, reload</div>
                <div class="api-code">POST /NeewerLux/sound {"action":"set","params":{"sensitivity":1.5}}</div>
            </div>
            <div class="api-section">
                <h3>Editing</h3>
                <div class="api-desc">Presets: list, get, save, rename, move, duplicate, delete, add, snapshot, recall</div>
                <div class="api-code">POST /NeewerLux/presets {"action":"rename","index":3,"name":"Stream"}</div>
                <div class="api-desc">Animations and sequences: get, save (with "original" to rename), duplicate, delete</div>
                <div class="api-code">POST /NeewerLux/animate {"action":"save","animation":{...},"original":"Old Name"}</div>
                <div class="api-code">POST /NeewerLux/sequence {"action":"get","name":"Example - Four Light Demo"}</div>
            </div>
            <div class="api-section">
                <h3>Settings</h3>
                <div class="api-desc">Light and show preferences, as on this page's Settings panel</div>
                <div class="api-code">POST /NeewerLux/settings {"action":"get"}</div>
                <div class="api-code">POST /NeewerLux/settings {"action":"set_light","light":0,"settings":{"role":"key","maxBri":60}}</div>
                <div class="api-code">POST /NeewerLux/settings {"action":"set_global","settings":{"envMaxBri":80}}</div>
            </div>
            <div class="api-section">
                <h3>Utility</h3>
                <div class="api-code">GET /NeewerLux/doAction?list</div>
                <div class="api-code">GET /NeewerLux/doAction?discover</div>
                <div class="api-code">GET /NeewerLux/doAction?link=1</div>
                <div class="api-code">GET /NeewerLux/doAction?nopage (suppress HTML response)</div>
            </div>
        </div>
    </div>
</div>

<div class="modal-bg" id="renderModal" onclick="if(event.target===this)closeRender()">
    <div class="modal">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <b id="renderTitle">Render</b><span style="flex:1"></span>
            <button class="btn" onclick="saveRenderPNG()">Save PNG</button>
            <button class="btn" onclick="closeRender()">Close</button>
        </div>
        <div style="position:relative;display:inline-block">
            <canvas id="renderCanvas" onclick="renderSeekClick(event)"></canvas>
            <div id="renderMarker" style="position:absolute;top:0;width:2px;background:#fff;display:none;pointer-events:none;box-shadow:0 0 3px #000"></div>
        </div>
        <div style="font-size:11px;color:var(--muted)">While this sequence plays, the white line shows where it is; click the strip to jump there.</div>
        <div id="renderCues" style="font-size:11px;color:var(--muted);max-height:160px;overflow:auto;margin-top:6px;font-family:monospace"></div>
    </div>
</div>

<!-- PRESET EDITOR -->
<div class="modal-bg" id="presetModal">
    <div class="modal wide">
        <div class="modal-title"><b id="peTitle">Edit preset</b><span style="flex:1"></span>
            <button class="btn primary" onclick="peSave()">Save</button><button class="btn" onclick="peClose()">Cancel</button></div>
        <div class="form-grid" style="grid-template-columns:80px 1fr;margin-bottom:10px">
            <label>Name</label><input type="text" id="peName" maxlength="20" placeholder="Preset name (optional)">
            <label>Fade in (ms)</label><span><input type="number" id="peFade" min="-1" max="10000" step="100" style="width:110px"> <span class="hint" style="display:inline">-1 = the global Fade in</span></span>
        </div>
        <div class="tl-hint">One entry for all lights makes a global preset (it applies to whichever lights you recall it on). Entries for individual lights make a snapshot.</div>
        <table class="edit-table"><thead><tr><th>#</th><th>Light</th><th>Mode</th><th>Values</th><th></th></tr></thead><tbody id="peRows"></tbody></table>
        <div class="toolbar" style="margin-top:8px">
            <button class="btn small" onclick="peAdd()">+ Entry</button>
            <button class="btn small" onclick="peDup()">Duplicate</button>
            <button class="btn small" onclick="peDel()">Delete</button>
            <button class="btn small" onclick="peMove(-1)">Up</button>
            <button class="btn small" onclick="peMove(1)">Down</button>
        </div>
    </div>
</div>

<!-- ANIMATION EDITOR -->
<div class="modal-bg" id="animModal">
    <div class="modal wide">
        <div class="modal-title"><b id="aeTitle">Edit animation</b><span style="flex:1"></span>
            <button class="btn primary" onclick="aeSave()">Save</button><button class="btn" onclick="aeClose()">Cancel</button></div>
        <div class="form-grid" style="grid-template-columns:90px 1fr;margin-bottom:8px">
            <label>Name</label><input type="text" id="aeName">
            <label>Description</label><input type="text" id="aeDesc">
            <label>Loop</label><label style="text-transform:none"><input type="checkbox" id="aeLoop"> Loop animation</label>
            <label>Fades (ms)</label><span>in <input type="number" id="aeFadeIn" min="-1" max="10000" step="100" style="width:100px"> back <input type="number" id="aeFadeOut" min="-1" max="10000" step="100" style="width:100px"> <span class="hint" style="display:inline">-1 = the global settings</span></span>
        </div>
        <div class="tabs"><div id="aeTabVisual" class="active" onclick="aeTab('visual')">Visual editor</div><div id="aeTabJson" onclick="aeTab('json')">JSON editor</div></div>
        <div id="aeVisual">
            <table class="edit-table"><thead><tr><th>#</th><th>Lights</th><th>Hold (ms)</th><th>Fade (ms)</th></tr></thead><tbody id="aeFrames"></tbody></table>
            <div class="toolbar" style="margin-top:6px">
                <button class="btn small" onclick="aeAddFrame()">+ Frame</button>
                <button class="btn small" onclick="aeDupFrame()">Duplicate</button>
                <button class="btn small" onclick="aeDelFrame()">Delete</button>
                <button class="btn small" onclick="aeMoveFrame(-1)">Up</button>
                <button class="btn small" onclick="aeMoveFrame(1)">Down</button>
                <button class="btn small" onclick="aeCopyFrame()">Copy</button>
                <button class="btn small" onclick="aePasteFrame()">Paste</button>
            </div>
            <h3 style="margin-top:12px;font-size:13px" id="aeFrameTitle">Frame</h3>
            <div class="toolbar">Hold <input type="number" id="aeHold" min="0" step="50" style="width:90px" onchange="aeFrameField()"> ms
                &nbsp; Fade <input type="number" id="aeFade" min="0" step="50" style="width:90px" onchange="aeFrameField()"> ms</div>
            <table class="edit-table"><thead><tr><th>Light</th><th>Mode</th><th>Values</th><th></th></tr></thead><tbody id="aeLights"></tbody></table>
            <div class="toolbar" style="margin-top:6px"><button class="btn small" onclick="aeAddLight()">+ Light</button>
                <span class="tl-hint" style="margin:0">Lights are * (every light), or 1, 2, 3... (positions; your light IDs when played on their own), or a light name.</span></div>
        </div>
        <div id="aeJson" style="display:none">
            <div class="tl-hint">The keyframes as JSON (the format of the files in light_prefs/animations).</div>
            <textarea class="json" id="aeJsonText" spellcheck="false"></textarea>
        </div>
    </div>
</div>

<!-- SEQUENCE TIMELINE EDITOR -->
<div class="modal-bg" id="tlModal">
    <div class="modal full">
        <div class="toolbar">
            Name <input type="text" id="tlName" oninput="tlNameEdited()">
            Length <input type="number" id="tlDuration" min="1" step="0.5" style="width:80px" onchange="tlDurationEdited()"> s
            Tempo <input type="number" id="tlBpm" min="0" max="300" step="0.5" style="width:70px" title="BPM, 0 = off. Beat lines and beat snapping." onchange="tlTempoEdited()">
            Beat 1 at <input type="number" id="tlBeatOffset" min="0" step="10" style="width:80px" onchange="tlTempoEdited()"> ms
            Snap <select id="tlSnap"></select>
            <button class="btn small" onclick="tlZoom(0.8)">Zoom -</button><button class="btn small" onclick="tlZoom(1.25)">Zoom +</button><button class="btn small" onclick="tlFit()">Fit</button>
            <span style="flex:1"></span>
            <button class="btn small" onclick="tlSettingsToggle()">Settings</button>
            <button class="btn small" onclick="tlValidate()">Check</button>
            <button class="btn small primary" onclick="tlSave(false)">Save</button>
            <button class="btn small" onclick="tlSave(true)">Save As</button>
            <button class="btn small" onclick="tlClose()">Close</button>
        </div>
        <div class="toolbar">
            <button class="btn small" onclick="tlSetPlayhead(0)" title="Playhead to the start (Home)">|&lt;</button>
            <button class="btn small" id="tlPlayBtn" onclick="tlTogglePlay()" title="Play or pause from the playhead (Space)">Play</button>
            <button class="btn small" onclick="tlStop()">Stop</button>
            <b id="tlTime" style="font-family:monospace">0:00.000</b>
            <label style="text-transform:none;margin-left:12px" title="Play the edit through the real lights from the playhead. Off: preview on screen only."><input type="checkbox" id="tlSend" onchange="tlSendToggled()"> Send to lights</label>
            <span style="flex:1"></span>
            <button class="btn small" onclick="tlAddCue('state')">+ Colour cue</button>
            <button class="btn small" onclick="tlAddCue('clip')">+ Clip cue</button>
            <button class="btn small" onclick="tlUndo()">Undo</button>
            <button class="btn small" onclick="tlRedo()">Redo</button>
        </div>
        <div id="tlSettings" style="display:none;border:1px solid var(--border);border-radius:6px;padding:8px;margin-bottom:6px">
            <div class="form-grid" style="grid-template-columns:150px 1fr 150px 1fr">
                <label>Frame rate</label><input type="number" id="tlFps" min="0" max="30" title="0 = the global default">
                <label>At the end</label><select id="tlEnd"></select>
                <label>While paused</label><select id="tlPause"><option value="revert">Return lights to their earlier state</option><option value="freeze">Freeze the current frame</option></select>
                <label>During effects</label><select id="tlInterrupt"><option value="continue">Keep running underneath (stay in sync)</option><option value="pause">Pause until the interruption ends</option></select>
                <label>Artist</label><input type="text" id="tlArtist">
                <label>Song</label><input type="text" id="tlSong">
                <label>Fade in (ms)</label><input type="number" id="tlFadeIn" min="-1" max="10000" step="100" title="-1 = the global Fade in">
                <label>Fade back (ms)</label><input type="number" id="tlFadeOut" min="-1" max="10000" step="100" title="-1 = the global Fade back">
                <label>Description</label><input type="text" id="tlDesc" style="grid-column: span 3">
            </div>
            <div class="toolbar" style="margin-top:6px"><button class="btn small primary" onclick="tlSettingsApply()">Apply</button></div>
        </div>
        <div class="tl-wrap">
            <div class="tl-main">
                <canvas id="tlCanvas" tabindex="0"></canvas>
                <div class="tl-hint">Double-click a track to add a cue. Drag a cue to move it, its right edge to change its length, the notch at its top to change the fade. Right-click for more. Ctrl+wheel zooms. Dashed outlines are cues shared by several lights.</div>
                <div style="color:var(--muted);font-size:12px;margin-bottom:4px">Preview at the playhead <select id="tlStageView" style="float:right" onchange="setStageView(this.value)"><option value="plan">Plan</option><option value="height">Height</option><option value="strip">Strip</option></select></div>
                <div class="stage-grid" id="tlStage"></div>
            </div>
            <div class="tl-props" id="tlProps"></div>
        </div>
        <div class="tl-status" id="tlStatus"></div>
    </div>
</div>

<div class="popup-menu" id="popupMenu" style="display:none"></div>

<script>
const BASE = '/NeewerLux/doAction?';
let selectedAnim = '';
let activeSceneBtn = null;

// SLIDER LIVE UPDATES
document.getElementById('cctTemp').oninput = e => document.getElementById('cctTempVal').textContent = (e.target.value * 100) + 'K';
document.getElementById('cctBri').oninput = e => document.getElementById('cctBriVal').textContent = e.target.value + '%';
document.getElementById('hsiHue').oninput = e => {
    document.getElementById('hsiHueVal').innerHTML = e.target.value + '&deg;';
    document.getElementById('huePreview').style.background = `hsl(${e.target.value},${document.getElementById('hsiSat').value}%,50%)`;
};
document.getElementById('hsiSat').oninput = e => {
    document.getElementById('hsiSatVal').textContent = e.target.value + '%';
    document.getElementById('huePreview').style.background = `hsl(${document.getElementById('hsiHue').value},${e.target.value}%,50%)`;
};
document.getElementById('hsiBri').oninput = e => document.getElementById('hsiBriVal').textContent = e.target.value + '%';
document.getElementById('sceneBri').oninput = e => document.getElementById('sceneBriVal').textContent = e.target.value + '%';

// MODE TABS
function switchMode(mode) {
    document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.mode-pane').forEach(p => p.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('pane-' + mode).classList.add('active');
}

// API CALLS
async function apiCall(url, label) {
    try {
        const r = await fetch(url);
        const text = await r.text();
        logMsg(label, 'ok');
        return text;
    } catch(e) {
        logMsg(label + ' FAILED: ' + e.message, 'err');
        return null;
    }
}

function logMsg(msg, cls='') {
    const log = document.getElementById('commandLog');
    const ts = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = cls;
    entry.style.borderBottom = '1px solid var(--border)';
    entry.style.padding = '2px 0';
    entry.textContent = '[' + ts + '] ' + msg;
    log.appendChild(entry);
    // Limit to last 50 entries
    while (log.children.length > 50) log.removeChild(log.firstChild);
    log.scrollTop = log.scrollHeight;
}

// LIGHT CONTROL
function sendCCT() {
    const light = document.getElementById('targetLight').value;
    const temp = document.getElementById('cctTemp').value;
    const bri = document.getElementById('cctBri').value;
    apiCall(`${BASE}light=${light}&mode=CCT&temp=${temp * 100}&bri=${bri}&nopage`, `CCT: light=${light} temp=${temp*100}K bri=${bri}%`);
}
function sendHSI() {
    const light = document.getElementById('targetLight').value;
    const hue = document.getElementById('hsiHue').value;
    const sat = document.getElementById('hsiSat').value;
    const bri = document.getElementById('hsiBri').value;
    apiCall(`${BASE}light=${light}&mode=HSI&hue=${hue}&sat=${sat}&bri=${bri}&nopage`, `HSI: light=${light} H:${hue} S:${sat} I:${bri}`);
}
function sendScene(num, btn) {
    const light = document.getElementById('targetLight').value;
    const bri = document.getElementById('sceneBri').value;
    if (activeSceneBtn) activeSceneBtn.classList.remove('active');
    btn.classList.add('active');
    activeSceneBtn = btn;
    apiCall(`${BASE}light=${light}&mode=SCENE&scene=${num}&bri=${bri}&nopage`, `Scene ${num}: light=${light} bri=${bri}%`);
}
function sendPower(state) {
    const light = document.getElementById('targetLight').value;
    if (state === 'on') {
        apiCall(`${BASE}batch=${light}:ON&nopage`, `Power ON: light=${light}`);
    } else {
        apiCall(`${BASE}batch=${light}:OFF&nopage`, `Power OFF: light=${light}`);
    }
}

// ANIMATIONS
function playAnimation() {
    if (!selectedAnim) { logMsg('No animation selected', 'err'); return; }
    const speed = document.getElementById('animSpeed').value.replace('x','');
    const rate = document.getElementById('animRate').value;
    const bri = document.getElementById('animBri').value;
    const loop = document.getElementById('animLoop').checked;
    const maxLoops = parseInt(document.getElementById('animLoopCount').value) || 0;
    const revert = document.getElementById('animRevert').checked;
    const parallel = document.getElementById('animParallel').checked;

    fetch('/NeewerLux/animate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action:'play', name:selectedAnim, speed:parseFloat(speed), rate:parseInt(rate), brightness:parseInt(bri), loop:loop, maxLoops:maxLoops, revert:revert, parallel:parallel})
    }).then(r => r.json()).then(d => {
        let msg = '▶ Playing: ' + selectedAnim;
        if (loop) msg += maxLoops > 0 ? ' (' + maxLoops + ' loops)' : ' (looping)';
        logMsg(msg, 'ok');
    }).catch(e => logMsg('Animation error: ' + e.message, 'err'));
}
function stopAnimation() {
    fetch('/NeewerLux/animate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action:'stop'})
    }).then(() => logMsg('■ Animation stopped', 'ok'))
      .catch(e => logMsg('Stop error: ' + e.message, 'err'));
}

// SCAN AND LINK
async function scanForLights() {
    logMsg('Scanning for Bluetooth lights... (takes ~5 seconds)', 'ok');
    document.getElementById('connStatus').textContent = 'Scanning...';
    document.getElementById('connStatus').classList.remove('connected');
    await apiCall(BASE + 'discover&nopage', 'Scan + auto-connect');
    // Give BLE discovery + connection time, then refresh
    setTimeout(refreshAll, 6000);
    setTimeout(refreshAll, 10000); // second refresh catches late connections
}
async function linkAllLights() {
    logMsg('Linking to all lights...', 'ok');
    await apiCall(BASE + 'link=all&nopage', 'Link all lights');
    setTimeout(refreshAll, 3000);
}

// AUTO-REFRESH (poll every 5 seconds)
let autoRefreshTimer = null;
function startAutoRefresh() {
    if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(refreshAll, 5000);
}
function stopAutoRefresh() {
    if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
}

// REFRESH / LOAD
async function refreshAll() {
    loadLights();
    if (!settingsData) loadSettings();
}

async function loadLights() {
    try {
        const r = await fetch(BASE + 'list_json');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        renderLightsJSON(data);
        renderPresetsJSON(data);
        loadAnimationsJSON(data);
        if (data.sequences) renderSeqList(data.sequences);  // no separate request per refresh
    } catch(e) {
        document.getElementById('lightTableBody').innerHTML =
            '<tr><td colspan="9" style="text-align:center;padding:20px;color:var(--muted)">Could not load light data. <a href="#" onclick="refreshAll();return false;">Retry</a></td></tr>';
        logMsg('Load error: ' + e.message, 'err');
    }
}

function renderLightsJSON(data) {
    const lights = data.lights || [];
    window._lastLights = lights;
    const select = document.getElementById('targetLight');
    select.innerHTML = '<option value="*">All Lights</option>';

    if (lights.length === 0) {
        document.getElementById('lightTableBody').innerHTML =
            '<tr><td colspan="9" style="text-align:center;padding:20px;color:var(--muted)">No lights discovered. <a href="#" onclick="scanForLights();return false;">Click to Scan</a></td></tr>';
        document.getElementById('connStatus').textContent = '0 lights';
        return;
    }

    let html2 = '', linkedCount = 0;
    const byId = {};
    (lastStatus && lastStatus.lights || []).forEach(s => byId[s.id] = s);
    lights.forEach(l => {
        if (l.linked) linkedCount++;
        const displayName = l.name || l.model || l.mac;
        const st = byId[l.id] || {};
        select.innerHTML += `<option value="${l.id}">${l.id} - ${displayName}</option>`;
        html2 += `<tr>
            <td class="light-id">${l.id}</td>
            <td><span class="swatch" data-swatch="${l.id}" style="background:${st.color || '#464646'}"></span></td>
            <td>${displayName}${l.model && l.name !== l.model ? ' <span style="color:var(--muted);font-size:11px">(' + l.model + ')</span>' : ''}</td>
            <td style="font-family:monospace;font-size:11px">${l.mac}</td>
            <td class="${l.linked ? 'linked' : 'not-linked'}">${l.linked ? '● LINKED' : '○ Not linked'}</td>
            <td style="font-size:11px" data-role="${l.id}">${esc(cap(st.role || ''))}${st.locked ? ' (locked)' : ''}</td>
            <td style="font-size:11px" data-layer="${l.id}">${esc(st.layer || '')}</td>
            <td style="font-size:11px">${l.status}</td>
            <td>${l.linked
                ? '<button class="btn" style="padding:3px 8px;font-size:11px" onclick="apiCall(\''+BASE+'light='+l.id+'&mode=CCT&temp=5600&bri=100&nopage\',\'Send: light '+l.id+'\')">Send</button>'
                : '<button class="btn success" style="padding:3px 8px;font-size:11px" onclick="apiCall(\''+BASE+'link='+l.id+'&nopage\',\'Link: light '+l.id+'\');setTimeout(refreshAll,3000)">Link</button>'
            }</td>
        </tr>`;
    });
    document.getElementById('lightTableBody').innerHTML = html2;
    document.getElementById('connStatus').textContent = linkedCount + '/' + lights.length + ' linked';
    if (linkedCount > 0) document.getElementById('connStatus').classList.add('connected');
    if (!window._lightsLoadedOnce) { logMsg('Loaded ' + lights.length + ' light(s)', 'ok'); window._lightsLoadedOnce = true; }
}

function renderPresetsJSON(data) {
    const presets = data.presets || [];
    window._lastPresets = presets;
    const grid = document.getElementById('presetGrid');
    if (presets.length === 0) {
        grid.innerHTML = '<div style="color:#888;grid-column:1/-1;text-align:center;padding:10px;">No presets configured</div>';
        return;
    }
    let html = '';
    presets.forEach(p => {
        const cls = p.custom ? 'preset-btn custom-global' : (p.name ? 'preset-btn custom-snap' : 'preset-btn');
        const label = p.name || (p.custom ? 'CUSTOM' : 'PRESET');
        html += '<button class="' + cls + '" onclick="usePreset(' + p.index + ')" oncontextmenu="presetMenu(event,' + p.index + ')" title="Click: recall | Right-click: edit, rename, move, duplicate, delete">'
            + '<span class="preset-num">' + p.index + '</span>'
            + '<span>' + label + '</span></button>';
    });
    // Add "+" button
    html += '<button class="preset-btn" onclick="addPreset()" title="Add a new preset" style="opacity:0.6"><span class="preset-num">+</span><span>NEW</span></button>';
    html += '<div style="grid-column:1/-1;font-size:11px;color:var(--muted);text-align:center;padding:4px 0;">Click to recall &bull; Right-click for options</div>';
    grid.innerHTML = html;
}

function addPreset() {
    apiCall(BASE + 'add_preset&nopage', 'Added new preset');
    setTimeout(refreshAll, 500);
}

function usePreset(idx) {
    const light = document.getElementById('targetLight').value;
    apiCall(BASE + 'use_preset=' + idx + '&light=' + light + '&nopage', 'Preset ' + idx);
}

async function checkForUpdates() {
    const el = document.getElementById('updateResult');
    el.textContent = 'Checking...';
    el.style.color = 'var(--muted)';
    try {
        const r = await fetch('https://api.github.com/repos/poizenjam/NeewerLux/releases/latest',
            {headers: {'Accept': 'application/vnd.github.v3+json'}});
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        const tag = (data.tag_name || '').replace(/^[vV]/, '');
        const url = data.html_url || 'https://github.com/poizenjam/NeewerLux/releases';
        const local = '{NLVERSION}';
        if (tag && tag !== local) {
            const rv = tag.split('.').map(Number);
            const lv = local.split('.').map(Number);
            const newer = rv[0] > lv[0] || (rv[0] === lv[0] && rv[1] > lv[1]) || (rv[0] === lv[0] && rv[1] === lv[1] && rv[2] > lv[2]);
            if (newer) {
                el.innerHTML = '<span style="color:var(--green)"><b>Update available: v' + tag + '</b></span>. <a href="' + url + '" target="_blank" style="color:var(--accent)">Download</a>';
            } else {
                el.innerHTML = '<span style="color:var(--accent)">You are on v' + local + ' (latest: v' + tag + ')</span>';
            }
        } else {
            el.innerHTML = '<span style="color:var(--green)">You are running the latest version (v' + local + ')</span>';
        }
    } catch(e) {
        el.innerHTML = '<span style="color:var(--red)">Could not check: ' + e.message + '</span>';
    }
}

function loadAnimationsJSON(data) {
    const anims = data.animations || [];
    const animDiv = document.getElementById('animList');
    animDiv.innerHTML = '';

    if (anims.length === 0) {
        animDiv.innerHTML = '<div class="anim-item" style="color:var(--muted)">No animations found</div>';
        return;
    }

    // Classify animations by mode
    const groups = {'HSI Only':[], 'Mixed':[], 'CCT Only':[], 'Scene Only':[]};
    anims.forEach(a => {
        const modes = new Set();
        (a.modes || []).forEach(m => modes.add(m.toUpperCase()));
        let cat = 'Mixed';
        if (modes.size === 1 && modes.has('HSI')) cat = 'HSI Only';
        else if (modes.size === 1 && modes.has('CCT')) cat = 'CCT Only';
        else if (modes.size === 1 && modes.has('ANM')) cat = 'Scene Only';
        else if (modes.size === 0) cat = 'Mixed';
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(a);
    });

    ['HSI Only','Mixed','CCT Only','Scene Only'].forEach(group => {
        if (!groups[group] || groups[group].length === 0) return;
        const header = document.createElement('div');
        header.style.cssText = 'padding:4px 8px;font-weight:700;color:var(--accent);font-size:12px;border-bottom:1px solid var(--border);margin-top:4px;';
        header.textContent = '━━━ ' + group + ' ━━━';
        animDiv.appendChild(header);

        groups[group].forEach(a => {
            const item = document.createElement('div');
            item.className = 'anim-item';
            if (selectedAnim === a.name) item.classList.add('selected');
            item.innerHTML = '<strong>' + a.name + '</strong>' + (a.description ? ' <span style="color:var(--muted);font-size:11px">' + a.description + '</span>' : '') + ' <span style="float:right;color:var(--muted);font-size:11px">' + a.frames + 'f' + (a.loop?' ↻':'') + '</span>';
            item.onclick = () => {
                document.querySelectorAll('.anim-item').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
                selectedAnim = a.name;
                document.getElementById('selectedAnimLabel').textContent = 'Selected: ' + a.name;
            };
            animDiv.appendChild(item);
        });
    });

    // Update selected label and playing state
    if (data.animationPlaying && data.currentAnimation) {
        document.getElementById('selectedAnimLabel').textContent = 'Playing: ' + data.currentAnimation;
    } else if (selectedAnim) {
        document.getElementById('selectedAnimLabel').textContent = 'Selected: ' + selectedAnim;
    }
    if (!window._animsLoadedOnce) { logMsg('Loaded ' + anims.length + ' animation(s)', 'ok'); window._animsLoadedOnce = true; }
}

async function loadAnimations() {
    // Standalone animation reload (also called from list_json via loadLights)
    try {
        const r = await fetch(BASE + 'list_json');
        if (!r.ok) return;
        const data = await r.json();
        loadAnimationsJSON(data);
    } catch(e) {
        document.getElementById('animList').innerHTML = '<div class="anim-item" style="color:var(--red)">Error loading animations</div>';
    }
}

// ---------------------------------------------------------------------------
// LIVE STATUS: stage tiles, table swatches, sequence and animation status
let lastStatus = null;
let lastStatusAt = 0;
let stageVisible = true;
function esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function cap(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : ''; }
function fmtMs(ms) { ms = Math.max(0, ms || 0); const s = Math.floor(ms / 1000); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); }

async function pollStatus() {
    if (document.visibilityState === 'hidden') return;
    try {
        const r = await fetch(BASE + 'status_json');
        if (!r.ok) return;
        lastStatus = await r.json();
        lastStatusAt = performance.now();
    } catch(e) { return; }
    renderStage();
    renderSeqStatus();
    renderAnimStatus();
    renderSoundStatus();
    (lastStatus.lights || []).forEach(l => {
        const sw = document.querySelector('[data-swatch="' + l.id + '"]');
        if (sw) sw.style.background = l.color || '#464646';
        const ly = document.querySelector('[data-layer="' + l.id + '"]');
        if (ly) ly.textContent = l.layer || '';
        const ro = document.querySelector('[data-role="' + l.id + '"]');
        if (ro) ro.textContent = cap(l.role) + (l.locked ? ' (locked)' : '');
    });
}

function toggleStage(hdr) {
    const b = document.getElementById('stageBody');
    stageVisible = b.style.display === 'none';
    b.style.display = stageVisible ? 'block' : 'none';
}

// Stage view (plan, height or strip), remembered in this browser (storage may be unavailable, so it's best-effort)
let stageView = 'plan';
try { stageView = localStorage.getItem('nlStageView') || 'plan'; } catch (e) {}
function setStageView(v) {
    stageView = ['plan', 'height', 'strip'].includes(v) ? v : 'plan';
    try { localStorage.setItem('nlStageView', stageView); } catch (e) {}
    ['stageView', 'tlStageView'].forEach(id => { const el = document.getElementById(id); if (el) el.value = stageView; });
    renderStage();
    if (typeof tlUpdateStage === 'function') tlUpdateStage();
}
function setStagePlan(on) { setStageView(on ? 'plan' : 'strip'); }  // older name
const HEIGHT_LEVEL = {low: 1, middle: 2, high: 3};
function stageTileHTML(t) {
    // t: name, role, color, mode, bri, linked, simulated, layer, side, depth, height, aim
    let detail = cap(t.role || '');
    if (t.mode) detail += '  ' + t.mode + (t.mode === 'OFF' || t.bri == null ? '' : ' ' + t.bri + '%');
    const pos = (t.side || 'centre') + ', ' + (t.depth || 'beside') + ', ' + (t.height || 'middle') + ' height, points ' + ((t.aim || 'you') === 'you' ? 'at you' : t.aim);
    const lvl = HEIGHT_LEVEL[t.height];
    return '<div class="stage-tile" title="' + esc(t.name) + ' (' + esc(pos) + ')">'
        + '<div class="stage-box layer-' + esc(t.layer || 'base') + '" style="background:' + (t.color || '#373737') + ';' + (t.linked === false ? 'filter:brightness(.4);' : '') + '">'
        + (t.simulated ? '<span class="sim">SIM</span>' : '')
        + (stageView === 'plan' && lvl ? '<span class="hb">' + [3, 2, 1].map(n => '<i class="' + (lvl >= n ? 'on' : '') + '"></i>').join('') + '</span>' : '')
        + (stageView === 'plan' && t.aim && t.aim !== 'you' && AIM_ARROW[t.aim] ? '<span class="aim">' + AIM_ARROW[t.aim] + '</span>' : '')
        + (t.color ? '' : '<span class="unknown">?</span>') + '</div>'
        + '<div class="stage-name">' + esc(t.name) + '</div>'
        + '<div class="stage-detail">' + esc(detail) + '</div>'
        + '<div class="stage-detail">' + esc(t.linked === false ? 'not linked' : (t.layer || 'base')) + '</div></div>';
}
function stageLayout(box, tiles, camera) {
    // Strip in sweep order, the plan (columns your left to right, front row at the top, you in
    // the middle, the camera outside the grid), or the height view (high row at the top)
    box.className = stageView === 'strip' ? 'stage-grid' : 'stage-plan';
    let html = '';
    if (stageView === 'strip') html = tiles.map(stageTileHTML).join('');
    else {
        const sides = ['left', 'centre', 'right'];
        const plan = stageView === 'plan';
        const rows = plan ? ['front', 'beside', 'back'] : ['high', 'middle', 'low'];
        const key = plan ? 'depth' : 'height';
        const cam = camera || 'front';
        const camHTML = '<div class="stage-cam">' + CAMERA_SVG + ' camera</div>';
        const camRow = r => {  // a row above or below the grid with the camera in its column
            const col = cam.endsWith('left') ? 0 : cam.endsWith('right') ? 2 : 1;
            return '<div></div>' + sides.map((_, c) => c === col ? camHTML : '<div></div>').join('');
        };
        if (plan && cam.startsWith('front')) html += camRow();
        html += '<div></div>' + ['Your left', 'Centre', 'Your right'].map(n => '<div class="ph">' + n + '</div>').join('');
        rows.forEach(d => {
            const side = plan && d === 'beside' && (cam === 'left' || cam === 'right') ? cam : null;
            html += '<div class="pr">' + (side === 'left' ? CAMERA_SVG + ' ' : '') + cap(d) + '</div>';
            sides.forEach(sd => {
                const here = tiles.filter(t => (sides.includes(t.side) ? t.side : 'centre') === sd && (rows.includes(t[key]) ? t[key] : rows[1]) === d);
                html += '<div class="pc" data-cell="' + sd + '/' + d + '">' + (here.length ? here.map(stageTileHTML).join('')
                    : (plan && sd === 'centre' && d === 'beside' ? '<span class="you">' + PERSON_SVG + '</span>' : ''))
                    + (side === 'right' && sd === 'right' ? '<span style="align-self:center">' + CAMERA_SVG + '</span>' : '') + '</div>';
            });
        });
        if (plan && cam.startsWith('back')) html += camRow();
    }
    if (box._last !== html) { box.innerHTML = html; box._last = html; }
}
function renderStage() {
    if (!stageVisible || !lastStatus) return;
    const lights = lastStatus.lights || [];
    const grid = document.getElementById('stageGrid');
    if (!lights.length) { grid.className = 'stage-grid'; grid.innerHTML = '<div style="color:var(--muted)">No lights yet</div>'; grid._last = ''; return; }
    stageLayout(grid, lights, (lastStatus.stage || {}).camera);
}

function renderAnimStatus() {
    const ov = lastStatus && lastStatus.layers && lastStatus.layers.override;
    const fx = lastStatus && lastStatus.layers && lastStatus.layers.effect;
    const el = document.getElementById('selectedAnimLabel');
    if (ov) el.textContent = 'Playing: ' + ov.name + ' (frame ' + Math.max(1, ov.keyframe || 0) + '/' + (ov.keyframes || '?') + ')';
    else if (fx) el.textContent = 'Effect: ' + fx.name;
    else el.textContent = selectedAnim ? 'Selected: ' + selectedAnim : 'No animation selected';
}

// ---------------------------------------------------------------------------
// SEQUENCES
let selectedSeq = '';
let seqNames = [];
async function seqPost(body) {
    const r = await fetch('/NeewerLux/sequence', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    return r.json();
}
function renderSeqList(list) {
    const div = document.getElementById('seqList');
    const names = list.map(s => s.name).join('|');
    if (div._last === names) return;
    div._last = names;
    seqNames = list.map(s => s.name);
    if (!list.length) { div.innerHTML = '<div class="anim-item" style="color:var(--muted)">No sequences in light_prefs/sequences</div>'; return; }
    div.innerHTML = '';
    list.forEach(s => {
        const item = document.createElement('div');
        item.className = 'anim-item' + (s.name === selectedSeq ? ' selected' : '');
        item.innerHTML = '<strong>' + esc(s.name) + '</strong> <span style="float:right;color:var(--muted);font-size:11px">' + fmtMs(s.duration_ms) + (s.cues != null ? ', ' + s.cues + ' cues' : '') + '</span>'
            + (s.description ? '<br><span style="color:var(--muted);font-size:11px">' + esc(s.description) + '</span>' : '');
        item.onclick = () => {
            div.querySelectorAll('.anim-item').forEach(i => i.classList.remove('selected'));
            item.classList.add('selected');
            selectedSeq = s.name;
        };
        div.appendChild(item);
    });
}
async function seqReload() {
    try {
        const d = await seqPost({action:'reload'});
        document.getElementById('seqList')._last = null;
        renderSeqList(d.sequences || []);
        logMsg('Reloaded ' + (d.sequences || []).length + ' sequence(s)', 'ok');
    } catch(e) { logMsg('Reload failed: ' + e.message, 'err'); }
}
function seqResult(label, d) {
    if (d.success === false) logMsg(label + ' failed: ' + ((d.errors || []).join('; ') || d.error || 'unknown error'), 'err');
    else logMsg(label, 'ok');
}
async function seqPlay() {
    if (!selectedSeq) { logMsg('No sequence selected', 'err'); return; }
    try { seqResult('▶ Sequence: ' + selectedSeq, await seqPost({action:'play', name:selectedSeq})); } catch(e) { logMsg('Sequence error: ' + e.message, 'err'); }
    pollStatus();
}
async function seqCmd(action, ms) {
    try { seqResult('Sequence ' + action, await seqPost({action:action, ms:ms})); } catch(e) { logMsg('Sequence error: ' + e.message, 'err'); }
    pollStatus();
}
function seqPauseResume() {
    const seq = lastStatus && lastStatus.sequence;
    if (!seq) { logMsg('No sequence playing', 'err'); return; }
    seqCmd(seq.state === 'paused' ? 'resume' : 'pause');
}
function seqSeek(ev) {
    const seq = lastStatus && lastStatus.sequence;
    if (!seq || !seq.duration_ms) return;
    const bar = document.getElementById('seqProgress').getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (ev.clientX - bar.left) / bar.width));
    seqCmd('seek', Math.round(frac * seq.duration_ms));
}
function renderSeqStatus() {
    const seq = lastStatus && lastStatus.sequence;
    const label = document.getElementById('seqStatus');
    const fill = document.getElementById('seqProgressFill');
    const btn = document.getElementById('seqPauseBtn');
    if (!seq) { label.textContent = 'No sequence playing'; fill.style.width = '0'; btn.textContent = 'Pause'; return; }
    label.textContent = cap(seq.state) + ': ' + seq.name + '  ' + fmtMs(seq.position_ms) + ' / ' + fmtMs(seq.duration_ms);
    fill.style.width = (seq.duration_ms ? Math.min(100, 100 * seq.position_ms / seq.duration_ms) : 0) + '%';
    btn.textContent = seq.state === 'paused' ? 'Resume' : 'Pause';
}

// Render: drawn here from the JSON render, so it also works when NeewerLux runs without its window
let lastRender = null;
async function seqRender() {
    if (!selectedSeq) { logMsg('No sequence selected', 'err'); return; }
    let d;
    try { d = await seqPost({action:'render', name:selectedSeq}); } catch(e) { logMsg('Render error: ' + e.message, 'err'); return; }
    if (!d.success) { seqResult('Render', d); return; }
    lastRender = d;
    drawRender(d);
    document.getElementById('renderModal').classList.add('open');
}
function drawRender(d) {
    const cv = document.getElementById('renderCanvas');
    const ctx = cv.getContext('2d');
    ctx.font = '13px sans-serif';
    const labels = d.lights.map(l => l.name + '  (' + l.role + ')');
    const labelW = Math.min(420, Math.max(80, ...labels.map(t => ctx.measureText(t).width)) + 20);
    const rowH = 26, rulerH = 24, pad = 30;
    const width = Math.min(1600, Math.max(700, Math.floor(window.innerWidth * 0.95) - 40));
    cv.width = width; cv.height = rulerH + rowH * d.lights.length + pad;
    const plotW = width - labelW - 12, t0 = d.start_ms, t1 = d.end_ms, span = Math.max(1, t1 - t0);
    const x = t => labelW + (t - t0) / span * plotW;
    renderAxis = {labelW, plotW, t0, span, height: cv.height, name: d.sequence};
    ctx.fillStyle = '#181818'; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.font = '13px sans-serif'; ctx.textBaseline = 'middle';
    d.lights.forEach((l, r) => {
        const y = rulerH + r * rowH;
        ctx.fillStyle = '#e6e6e6'; ctx.fillText(labels[r], 6, y + rowH / 2);
        const ch = d.changes[l.id] || [];
        ch.forEach((c, i) => {
            const end = i + 1 < ch.length ? ch[i + 1][0] : t1;
            ctx.fillStyle = c[1] || '#373737';
            ctx.fillRect(x(c[0]), y + 3, Math.max(1, x(end) - x(c[0])), rowH - 6);
        });
    });
    const stepS = span > 120000 ? 30000 : span > 30000 ? 5000 : 1000;
    ctx.fillStyle = '#aaa'; ctx.font = '11px sans-serif'; ctx.textBaseline = 'top';
    for (let t = Math.ceil(t0 / stepS) * stepS; t <= t1; t += stepS) {
        ctx.fillRect(x(t), rulerH - 6, 1, 6);
        const lbl = fmtMs(t), w = ctx.measureText(lbl).width;
        ctx.fillText(lbl, x(t) + 2 + w > width ? x(t) - w - 2 : x(t) + 2, 4);
    }
    ctx.strokeStyle = 'rgba(255,255,255,.35)';
    (d.cues || []).forEach(c => { ctx.beginPath(); ctx.moveTo(x(c.at_ms) + .5, rulerH); ctx.lineTo(x(c.at_ms) + .5, rulerH + rowH * d.lights.length); ctx.stroke(); });
    document.getElementById('renderTitle').textContent = 'Render: ' + d.sequence + ' (' + fmtMs(d.duration_ms) + ')';
    document.getElementById('renderCues').innerHTML = (d.cues || []).map(c => fmtMs(c.at_ms) + '  ' + esc(c.target) + '  ' + esc(c.what) + (c.label ? '  [' + esc(c.label) + ']' : '')).join('<br>')
        + ((d.warnings || []).length ? '<br><span style="color:var(--red)">' + d.warnings.map(esc).join('<br>') + '</span>' : '');
}
function closeRender() { document.getElementById('renderModal').classList.remove('open'); }
// Play marker on the render: follows the playing sequence (extrapolated between status polls)
let renderAxis = null;
function renderPlayingMs() {
    const seq = lastStatus && lastStatus.sequence;
    if (!renderAxis || !seq || seq.name !== renderAxis.name) return null;
    let ms = seq.position_ms;
    if (seq.state === 'playing') ms += performance.now() - lastStatusAt;
    return Math.min(renderAxis.t0 + renderAxis.span, ms);
}
setInterval(() => {
    const m = document.getElementById('renderMarker');
    if (!m || !document.getElementById('renderModal').classList.contains('open')) return;
    const ms = renderPlayingMs();
    if (ms == null) { m.style.display = 'none'; return; }
    const cv = document.getElementById('renderCanvas');
    const scale = cv.getBoundingClientRect().width / cv.width;
    m.style.display = 'block';
    m.style.height = (renderAxis.height * scale) + 'px';
    m.style.left = ((renderAxis.labelW + (ms - renderAxis.t0) / renderAxis.span * renderAxis.plotW) * scale - 1) + 'px';
}, 50);
function renderSeekClick(ev) {
    if (!renderAxis || renderPlayingMs() == null) return;
    const r = ev.target.getBoundingClientRect();
    const px = (ev.clientX - r.left) * ev.target.width / r.width;
    if (px < renderAxis.labelW) return;
    seqCmd('seek', Math.round(renderAxis.t0 + Math.min(1, (px - renderAxis.labelW) / renderAxis.plotW) * renderAxis.span));
}
function saveRenderPNG() {
    const a = document.createElement('a');
    a.href = document.getElementById('renderCanvas').toDataURL('image/png');
    a.download = (lastRender ? lastRender.sequence : 'render') + ' - render.png';
    a.click();
}

// ---------------------------------------------------------------------------
// SETTINGS
let settingsData = null;
async function settingsPost(body) {
    const r = await fetch('/NeewerLux/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    return r.json();
}
function openSettings() {
    const b = document.getElementById('settingsBody');
    if (b.style.display === 'none') { b.style.display = 'block'; loadSettings(); }
    document.getElementById('settingsCard').scrollIntoView({behavior: 'smooth'});
}
function toggleSettings(hdr) {
    const b = document.getElementById('settingsBody');
    const open = b.style.display === 'none';
    b.style.display = open ? 'block' : 'none';
    if (open) loadSettings();
}
async function loadSettings() {
    try { const d = await settingsPost({action:'get'}); if (d.success) applySettings(d); } catch(e) {}
}
function fillSelect(id, values, labels) {
    const sel = document.getElementById(id);
    const keep = sel.value;
    sel.innerHTML = values.map((v, i) => '<option value="' + esc(v) + '">' + esc(labels ? labels[i] : cap(v)) + '</option>').join('');
    if (values.map(String).includes(keep)) sel.value = keep;
}
function applySettings(d) {
    settingsData = d;
    fillSelect('lpRole', d.roles, d.roles.map(r => r === 'rim' ? 'Rim / back' : r.charAt(0).toUpperCase() + r.slice(1)));

    fillSelect('gpSim', d.simulatedRigs.map((_, i) => i), d.simulatedRigs.map((r, i) => i ? i + ' (' + r + ')' : r));
    fillSelect('lpLight', d.lights.map(l => l.index), d.lights.map(l => l.id + ' - ' + (l.customName || l.model) + (l.simulated ? ' (simulated)' : '')));
    fillLightPrefs();
    const g = d.global;
    document.getElementById('gpFlashGuard').checked = g.flashGuardEnabled !== false;
    document.getElementById('gpEnvMax').value = g.envMaxBri;
    document.getElementById('gpEnvMin').value = g.envMinBri;
    document.getElementById('gpSeqFps').value = g.seqFrameRate;
    document.getElementById('gpEffectMax').value = g.effectMaxSeconds;
    document.getElementById('gpCCTMin').value = g.globalCCTMin;
    document.getElementById('gpCCTMax').value = g.globalCCTMax;
    document.getElementById('gpFallback').value = g.cctFallbackMode;
    document.getElementById('gpSim').value = g.simulatedLights;
    document.getElementById('gpSimCCT').checked = !!g.simulatedCCTOnly;
    document.getElementById('gpCamera').value = g.cameraPosition || 'front';
    document.getElementById('gpEyelineFlash').value = g.eyelineFlash || 'same';
    document.getElementById('gpHandback').value = g.handbackFadeMs != null ? g.handbackFadeMs : 500;
    document.getElementById('gpFadeIn').value = g.fadeInMs != null ? g.fadeInMs : 0;
    setGlobalPrefsDirty(false);
}
// Save Global Preferences is highlighted while the form has changes it hasn't saved
function setGlobalPrefsDirty(dirty) {
    const b = document.getElementById('gpSaveBtn');
    if (!b) return;
    b.classList.toggle('unsaved', dirty);
    b.classList.toggle('primary', !dirty);
    b.textContent = dirty ? 'Save Global Preferences (unsaved changes)' : 'Save Global Preferences';
}
function watchGlobalPrefs() {
    document.querySelectorAll('[id^="gp"]').forEach(el => {
        if (el.id === 'gpSaveBtn') return;
        el.addEventListener('input', () => setGlobalPrefsDirty(true));
        el.addEventListener('change', () => setGlobalPrefsDirty(true));
    });
}
function gpFlashGuardChanged(box) {
    if (!box.checked && !confirm('The flash guard keeps every light to at most 3 flashes a second, the WCAG limit for photosensitive seizures. Without it, fast animations, speeds and effects can flash much faster, in the room and on stream.\n\nTurn it off anyway? (It takes effect when you save.)')) box.checked = true;
}
function currentLightPrefs() {
    if (!settingsData) return null;
    const idx = parseInt(document.getElementById('lpLight').value);
    return settingsData.lights.find(l => l.index === idx) || null;
}
function fillLightPrefs() {
    const l = currentLightPrefs();
    if (!l) return;
    document.getElementById('lpName').value = l.customName;
    document.getElementById('lpName').placeholder = l.model;
    document.getElementById('lpID').value = l.preferredID;
    document.getElementById('lpTempMin').value = l.tempRange[0];
    document.getElementById('lpTempMax').value = l.tempRange[1];
    document.getElementById('lpCCTOnly').checked = l.cctOnly;
    document.getElementById('lpRole').value = l.role;
    lpPos = {side: l.side, depth: l.depth || 'beside', height: l.height || 'middle', aim: l.aim || 'you'};
    renderPosPicker();
    document.getElementById('lpOrder').value = l.order;
    document.getElementById('lpEyeline').checked = !!l.eyeline;
    document.getElementById('lpMaxBri').value = l.maxBri;
    document.getElementById('lpMinBri').value = l.minBri;
    document.getElementById('lpLocked').checked = !!l.locked;
}
// Position picker: a 3 x 3 grid from your seat (your left to right, front at the top) plus height
let lpPos = {side: 'centre', depth: 'beside', height: 'middle', aim: 'you'};
const AIM_PAD = [['front-left', '\u2196'], ['front', '\u2191'], ['front-right', '\u2197'], ['left', '\u2190'], ['you', '\u25cf'],
                 ['right', '\u2192'], ['back-left', '\u2199'], ['back', '\u2193'], ['back-right', '\u2198']];
const AIM_ARROW = Object.fromEntries(AIM_PAD);
// a top-down head and shoulders facing the front (up), with a faint view cone
const PERSON_SVG = '<svg width="44" height="40" viewBox="0 0 44 40" aria-label="you"><polygon points="22,18 6,0 38,0" fill="rgba(255,255,255,.07)"/>'
    + '<rect x="6" y="20" width="32" height="12" rx="6" fill="#6a6a6a"/><ellipse cx="22" cy="20" rx="7" ry="8" fill="#9a9a9a"/><polygon points="19,13 25,13 22,8" fill="#9a9a9a"/></svg>';
const CAMERA_SVG = '<svg width="26" height="20" viewBox="0 0 26 20" aria-label="camera"><rect x="3" y="1" width="20" height="12" rx="3" fill="#888"/><polygon points="9,13 17,13 20,19 6,19" fill="#888"/></svg>';
function renderPosPicker() {
    const box = document.getElementById('lpPos');
    if (!box || !settingsData) return;
    const cur = currentLightPrefs();
    const others = {};
    settingsData.lights.forEach(l => {
        if (cur && l.index === cur.index) return;
        const k = l.side + '/' + (l.depth || 'beside');
        (others[k] = others[k] || []).push(l.customName || l.model);
    });
    const sides = ['left', 'centre', 'right'], depths = ['front', 'beside', 'back'];
    let g = '<div class="pos-grid"><div></div>' + ['Your left', 'Centre', 'Your right'].map(n => '<div class="ph">' + n + '</div>').join('');
    depths.forEach(d => {
        g += '<div class="pr">' + cap(d) + '</div>';
        sides.forEach(sd => {
            const names = others[sd + '/' + d] || [];
            const sel = lpPos.side === sd && lpPos.depth === d;
            let text = '';
            if (sel) text = 'This light' + (names.length ? '\n+ ' + names.length + ' other' + (names.length > 1 ? 's' : '') : '');
            else if (names.length) text = names.slice(0, 2).join('\n') + (names.length > 2 ? '\n+' + (names.length - 2) + ' more' : '');
    
            const you = !text && sd === 'centre' && d === 'beside';
            g += '<button type="button" class="pos-cell' + (sel ? ' sel' : '') + (names.length ? ' has' : '') + '" data-side="' + sd + '" data-depth="' + d
                + '" title="' + esc(names.join(', ')) + '" onclick="lpPos.side=this.dataset.side;lpPos.depth=this.dataset.depth;renderPosPicker()">' + (you ? PERSON_SVG : esc(text)) + '</button>';
        });
    });
    g += '</div><div class="pos-hcol"><div style="color:var(--muted)">Height</div>'
        + ['high', 'middle', 'low'].map(h => '<button type="button" class="pos-h' + (lpPos.height === h ? ' sel' : '') + '" data-height="' + h
        + '" onclick="lpPos.height=this.dataset.height;renderPosPicker()">' + cap(h) + '</button>').join('')
        + '<div style="color:var(--muted);margin-top:6px">Points</div><div class="pos-aim">'
        + AIM_PAD.map(([a, glyph]) => '<button type="button" class="' + (lpPos.aim === a ? 'sel' : '') + '" data-aim="' + a + '" title="'
            + (a === 'you' ? 'At you' : 'Points ' + a.replace('-', ' ')) + '" onclick="lpPos.aim=this.dataset.aim;renderPosPicker()">' + glyph + '</button>').join('')
        + '</div></div>';
    box.innerHTML = g;
}
function resetTempRange() {
    const l = currentLightPrefs();
    if (!l) return;
    document.getElementById('lpTempMin').value = l.defaultTempRange[0];
    document.getElementById('lpTempMax').value = l.defaultTempRange[1];
}
function num(id) { return parseInt(document.getElementById(id).value); }
async function saveLightPrefs() {
    const l = currentLightPrefs();
    if (!l) { logMsg('No light selected', 'err'); return; }
    const settings = {customName: document.getElementById('lpName').value, preferredID: num('lpID'),
        tempRange: [num('lpTempMin'), num('lpTempMax')], cctOnly: document.getElementById('lpCCTOnly').checked,
        role: document.getElementById('lpRole').value, side: lpPos.side, depth: lpPos.depth, height: lpPos.height, aim: lpPos.aim || 'you', order: num('lpOrder'),
        eyeline: document.getElementById('lpEyeline').checked, maxBri: num('lpMaxBri'), minBri: num('lpMinBri'),
        locked: document.getElementById('lpLocked').checked};
    try {
        const d = await settingsPost({action:'set_light', light:l.index, settings:settings});
        if (!d.success) { logMsg('Light preferences not saved: ' + (d.errors || []).join('; '), 'err'); return; }
        applySettings(d);
        logMsg('Saved preferences for light ' + l.id, 'ok');
        loadLights();
    } catch(e) { logMsg('Save failed: ' + e.message, 'err'); }
}
async function saveGlobalPrefs() {
    const settings = {envMaxBri: num('gpEnvMax'), envMinBri: num('gpEnvMin'), seqFrameRate: num('gpSeqFps'),
        effectMaxSeconds: num('gpEffectMax'), globalCCTMin: num('gpCCTMin'), globalCCTMax: num('gpCCTMax'),
        cctFallbackMode: document.getElementById('gpFallback').value, simulatedLights: num('gpSim'),
        simulatedCCTOnly: document.getElementById('gpSimCCT').checked, flashGuardEnabled: document.getElementById('gpFlashGuard').checked,
        cameraPosition: document.getElementById('gpCamera').value, eyelineFlash: document.getElementById('gpEyelineFlash').value,
        handbackFadeMs: num('gpHandback'), fadeInMs: num('gpFadeIn')};
    try {
        const d = await settingsPost({action:'set_global', settings:settings});
        if (!d.success) { logMsg('Global preferences not saved: ' + (d.errors || []).join('; '), 'err'); return; }
        applySettings(d);
        logMsg('Saved global preferences' + (d.note ? ' (' + d.note + ')' : ''), 'ok');
    } catch(e) { logMsg('Save failed: ' + e.message, 'err'); }
}

// ---------------------------------------------------------------------------
// SHARED HELPERS FOR THE EDITORS
async function postJSON(path, body) {
    const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    return r.json();
}
function errText(d) { return ((d && (d.errors || [])).join('; ')) || (d && d.error) || 'unknown error'; }
function showMenu(ev, items) {
    ev.preventDefault();
    const m = document.getElementById('popupMenu');
    m.innerHTML = '';
    items.forEach(it => {
        if (it === '-') { m.appendChild(document.createElement('hr')); return; }
        const d = document.createElement('div');
        d.textContent = it.label;
        if (it.disabled) d.className = 'disabled';
        d.onclick = () => { hideMenu(); it.fn(); };
        m.appendChild(d);
    });
    m.style.display = 'block';
    const w = m.offsetWidth, h = m.offsetHeight;
    m.style.left = Math.min(ev.clientX, window.innerWidth - w - 8) + 'px';
    m.style.top = Math.min(ev.clientY, window.innerHeight - h - 8) + 'px';
}
function hideMenu() { document.getElementById('popupMenu').style.display = 'none'; }
document.addEventListener('mousedown', e => { if (!e.target.closest('#popupMenu')) hideMenu(); });
function lightOptions(current, includeAll) {
    // targets the editors offer: all lights, each light's ID, and anything already stored
    const opts = [];
    if (includeAll) opts.push(['-1', 'All lights (global)']);
    (window._lastLights || []).forEach(l => opts.push([String(l.id), l.id + ' - ' + (l.name || l.model)]));
    if (current != null && !opts.some(o => o[0] === String(current))) opts.push([String(current), String(current)]);
    return opts.map(o => '<option value="' + esc(o[0]) + '"' + (String(current) === o[0] ? ' selected' : '') + '>' + esc(o[1]) + '</option>').join('');
}
const SCENES = ['1: Police', '2: Ambulance', '3: Fire Truck', '4: Fireworks', '5: Party', '6: Candlelight', '7: Lightning', '8: Paparazzi', '9: TV Screen'];
function numInput(cls, val, min, max, step) {
    return '<input type="number" class="' + cls + '" value="' + esc(val) + '" min="' + min + '" max="' + max + '"' + (step ? ' step="' + step + '"' : '') + '>';
}

// ---------------------------------------------------------------------------
// PRESETS: right-click menu and editor (the desktop's preset menu and editor)
function presetMenu(e, idx) {
    const n = (window._lastPresets || []).length;
    showMenu(e, [
        {label: 'Recall', fn: () => usePreset(idx)},
        {label: 'Save current lights here', fn: () => presetAction('snapshot', idx, 'Saved the current lights to preset ' + idx)},
        {label: 'Edit preset...', fn: () => peOpen(idx)},
        {label: 'Rename...', fn: () => presetRename(idx)},
        '-',
        {label: 'Move left', disabled: idx <= 1, fn: () => presetAction('move', idx, 'Moved preset ' + idx, {direction: 'left'})},
        {label: 'Move right', disabled: idx >= n, fn: () => presetAction('move', idx, 'Moved preset ' + idx, {direction: 'right'})},
        '-',
        {label: 'Duplicate', fn: () => presetAction('duplicate', idx, 'Duplicated preset ' + idx)},
        {label: 'Delete', disabled: n <= 1, fn: () => { if (confirm('Delete preset ' + idx + '? Presets after it are renumbered.')) presetAction('delete', idx, 'Deleted preset ' + idx); }},
    ]);
}
async function presetAction(action, idx, okMsg, extra) {
    const d = await postJSON('/NeewerLux/presets', Object.assign({action: action, index: idx}, extra || {}));
    if (!d.success) { logMsg('Preset ' + action + ' failed: ' + errText(d), 'err'); return d; }
    logMsg(okMsg, 'ok');
    refreshAll();
    return d;
}
function presetRename(idx) {
    const p = (window._lastPresets || []).find(x => x.index === idx) || {};
    const name = prompt('Name for preset ' + idx + ' (up to 20 characters, empty to clear):', p.name || '');
    if (name !== null) presetAction('rename', idx, 'Renamed preset ' + idx, {name: name});
}
let pe = null;
async function peOpen(idx) {
    const d = await postJSON('/NeewerLux/presets', {action: 'get', index: idx});
    if (!d.success) { logMsg('Can\'t open preset ' + idx + ': ' + errText(d), 'err'); return; }
    pe = {index: idx, entries: JSON.parse(JSON.stringify(d.preset.entries)), sel: 0};
    document.getElementById('peTitle').textContent = 'Edit preset ' + idx;
    document.getElementById('peName').value = d.preset.name || '';
    document.getElementById('peFade').value = d.preset.fade_ms == null ? -1 : d.preset.fade_ms;
    peRender();
    document.getElementById('presetModal').classList.add('open');
}
function peClose() { document.getElementById('presetModal').classList.remove('open'); pe = null; }
function peValues(e) {
    const m = (e.mode || 'CCT').toUpperCase();
    if (m === 'HSI') return 'Hue ' + numInput('pe-hue', e.hue != null ? e.hue : 240, 0, 360) + ' Sat ' + numInput('pe-sat', e.sat != null ? e.sat : 100, 0, 100) + ' Bri ' + numInput('pe-bri', e.bri != null ? e.bri : 100, 0, 100);
    if (m === 'SCENE') return '<select class="pe-scene">' + SCENES.map((s, i) => '<option value="' + (i + 1) + '"' + ((e.scene || 1) === i + 1 ? ' selected' : '') + '>' + s + '</option>').join('') + '</select> Bri ' + numInput('pe-bri', e.bri != null ? e.bri : 100, 0, 100);
    return 'Temp ' + numInput('pe-temp', (e.temp || 56) * 100, 2700, 8500, 100) + ' K Bri ' + numInput('pe-bri', e.bri != null ? e.bri : 100, 0, 100);
}
function peRender() {
    const rows = document.getElementById('peRows');
    rows.innerHTML = pe.entries.map((e, i) => '<tr data-i="' + i + '"' + (i === pe.sel ? ' class="selected"' : '') + '>'
        + '<td>' + (i + 1) + '</td><td><select class="pe-target">' + lightOptions(e.target, true) + '</select></td>'
        + '<td><select class="pe-mode">' + ['CCT', 'HSI', 'Scene'].map(m => '<option' + ((e.mode || 'CCT') === m ? ' selected' : '') + '>' + m + '</option>').join('') + '</select></td>'
        + '<td>' + peValues(e) + '</td><td>' + (e.off ? '<span title="This light was off when the snapshot was taken" style="color:var(--muted)">off</span>' : '') + '</td></tr>').join('');
    rows.querySelectorAll('tr').forEach(tr => {
        const i = +tr.dataset.i;
        tr.onclick = () => { if (pe.sel !== i) { peRead(); pe.sel = i; rows.querySelectorAll('tr').forEach(r => r.classList.toggle('selected', +r.dataset.i === i)); } };
        tr.querySelectorAll('input,select').forEach(el => el.onchange = () => { peRead(); if (el.classList.contains('pe-mode')) peRender(); });
    });
}
function peRead() {
    // table to entries
    document.querySelectorAll('#peRows tr').forEach(tr => {
        const i = +tr.dataset.i, e = pe.entries[i], q = c => tr.querySelector('.' + c);
        const n = {target: q('pe-target').value, mode: q('pe-mode').value};
        if (e.mode === n.mode || !q('pe-bri')) {
            if (q('pe-bri')) n.bri = +q('pe-bri').value;
            if (n.mode === 'HSI' && q('pe-hue')) { n.hue = +q('pe-hue').value; n.sat = +q('pe-sat').value; }
            if (n.mode === 'CCT' && q('pe-temp')) n.temp = Math.round(+q('pe-temp').value / 100);
            if (n.mode === 'Scene' && q('pe-scene')) n.scene = +q('pe-scene').value;
        } else {
            n.bri = e.bri != null ? e.bri : 100;
        }
        if (e.off) n.off = true;
        pe.entries[i] = n;
    });
}
function peAdd() { peRead(); pe.entries.push({target: '-1', mode: 'CCT', temp: 56, bri: 100}); pe.sel = pe.entries.length - 1; peRender(); }
function peDup() { peRead(); if (!pe.entries.length) return; pe.entries.splice(pe.sel + 1, 0, JSON.parse(JSON.stringify(pe.entries[pe.sel]))); pe.sel++; peRender(); }
function peDel() { peRead(); if (pe.entries.length <= 1) return; pe.entries.splice(pe.sel, 1); pe.sel = Math.max(0, pe.sel - 1); peRender(); }
function peMove(d) {
    peRead();
    const j = pe.sel + d;
    if (j < 0 || j >= pe.entries.length) return;
    [pe.entries[pe.sel], pe.entries[j]] = [pe.entries[j], pe.entries[pe.sel]];
    pe.sel = j;
    peRender();
}
async function peSave() {
    peRead();
    const idx = pe.index;
    const fade = parseInt(document.getElementById('peFade').value, 10);
    const d = await postJSON('/NeewerLux/presets', {action: 'save', index: idx, name: document.getElementById('peName').value, entries: pe.entries,
                                                    fade_ms: isNaN(fade) || fade < 0 ? null : fade});
    if (!d.success) { logMsg('Preset not saved: ' + errText(d), 'err'); return; }
    logMsg('Saved preset ' + idx, 'ok');
    peClose();
    refreshAll();
}

// ---------------------------------------------------------------------------
// ANIMATIONS: New, Edit, Duplicate, Delete, Export, Import, Reload, and the editor
async function animPost(body) { return postJSON('/NeewerLux/animate', body); }
function animNeedSelection() { if (!selectedAnim) { logMsg('No animation selected', 'err'); return true; } return false; }
async function animDuplicate() {
    if (animNeedSelection()) return;
    const d = await animPost({action: 'duplicate', name: selectedAnim});
    if (!d.success) { logMsg('Duplicate failed: ' + errText(d), 'err'); return; }
    selectedAnim = d.animation;
    logMsg('Duplicated as ' + d.animation, 'ok');
    loadAnimations();
}
async function animDelete() {
    if (animNeedSelection()) return;
    if (!confirm('Delete animation "' + selectedAnim + '"?')) return;
    const d = await animPost({action: 'delete', name: selectedAnim});
    if (!d.success) { logMsg('Delete failed: ' + errText(d), 'err'); return; }
    logMsg('Deleted animation ' + selectedAnim, 'ok');
    selectedAnim = '';
    loadAnimations();
}
async function animReload() {
    const d = await animPost({action: 'reload'});
    logMsg('Reloaded ' + d.count + ' animation(s)', 'ok');
    loadAnimations();
}
async function animExport() {
    if (animNeedSelection()) return;
    const d = await animPost({action: 'get', name: selectedAnim});
    if (!d.success) { logMsg('Export failed: ' + errText(d), 'err'); return; }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(d.animation, null, 2)], {type: 'application/json'}));
    a.download = d.animation.name + '.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
async function animImport(input) {
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    let data;
    try { data = JSON.parse(await file.text()); } catch (e) { logMsg('Import failed: not valid JSON (' + e.message + ')', 'err'); return; }
    let d = await animPost({action: 'save', animation: data});
    if (!d.success && /exists/.test(errText(d)) && confirm('An animation named "' + data.name + '" already exists. Replace it?')) {
        d = await animPost({action: 'save', animation: data, overwrite: true});
    }
    if (!d.success) { logMsg('Import failed: ' + errText(d), 'err'); return; }
    logMsg('Imported animation ' + d.animation, 'ok');
    selectedAnim = d.animation;
    loadAnimations();
}

let ae = null;
function animNew() {
    aeOpen({name: 'New Animation', description: '', loop: true,
            keyframes: [{hold_ms: 500, fade_ms: 0, lights: {'*': {mode: 'HSI', hue: 240, sat: 100, bri: 100}}}]}, null);
}
async function animEdit() {
    if (animNeedSelection()) return;
    const d = await animPost({action: 'get', name: selectedAnim});
    if (!d.success) { logMsg('Can\'t open: ' + errText(d), 'err'); return; }
    aeOpen(d.animation, d.animation.name);
}
function aeOpen(anim, original) {
    ae = {anim: JSON.parse(JSON.stringify(anim)), original: original, sel: 0, tab: 'visual', clipboard: ae ? ae.clipboard : null};
    ae.anim.keyframes = ae.anim.keyframes || [];
    document.getElementById('aeTitle').textContent = original ? 'Edit animation' : 'New animation';
    document.getElementById('aeName').value = ae.anim.name || '';
    document.getElementById('aeDesc').value = ae.anim.description || '';
    document.getElementById('aeLoop').checked = !!ae.anim.loop;
    document.getElementById('aeFadeIn').value = ae.anim.fade_in_ms == null ? -1 : ae.anim.fade_in_ms;
    document.getElementById('aeFadeOut').value = ae.anim.handback_fade_ms == null ? -1 : ae.anim.handback_fade_ms;
    aeTab('visual');
    aeRender();
    document.getElementById('animModal').classList.add('open');
}
function aeClose() { document.getElementById('animModal').classList.remove('open'); }
function aeTab(which) {
    if (!ae) return;
    if (which === ae.tab) { document.getElementById('aeVisual').style.display = which === 'visual' ? '' : 'none'; return; }
    if (which === 'json') {
        aeReadLights();
        document.getElementById('aeJsonText').value = JSON.stringify(ae.anim.keyframes, null, 2);
    } else if (!aeReadJson()) {
        return;
    }
    ae.tab = which;
    document.getElementById('aeTabVisual').classList.toggle('active', which === 'visual');
    document.getElementById('aeTabJson').classList.toggle('active', which === 'json');
    document.getElementById('aeVisual').style.display = which === 'visual' ? '' : 'none';
    document.getElementById('aeJson').style.display = which === 'json' ? '' : 'none';
    if (which === 'visual') aeRender();
}
function aeReadJson() {
    try {
        const kf = JSON.parse(document.getElementById('aeJsonText').value);
        if (!Array.isArray(kf)) throw new Error('must be a JSON array of keyframes');
        ae.anim.keyframes = kf;
        ae.sel = Math.min(ae.sel, Math.max(0, kf.length - 1));
        return true;
    } catch (e) { alert('Fix the JSON first: ' + e.message); return false; }
}
function aeLightSummary(lights) {
    return Object.entries(lights || {}).map(([k, p]) => {
        const m = (p.mode || 'HSI').toUpperCase();
        const v = m === 'HSI' ? 'H' + p.hue + ' S' + p.sat + ' ' + p.bri + '%' : m === 'CCT' ? (p.temp || 56) * 100 + 'K ' + p.bri + '%' : (m === 'ANM' || m === 'SCENE') ? 'scene ' + p.scene + ' ' + p.bri + '%' : m;
        return k + ': ' + v;
    }).join(', ');
}
function aeRender() {
    const kfs = ae.anim.keyframes;
    const body = document.getElementById('aeFrames');
    body.innerHTML = kfs.map((k, i) => '<tr data-i="' + i + '"' + (i === ae.sel ? ' class="selected"' : '') + '><td>' + (i + 1) + '</td><td>' + esc(aeLightSummary(k.lights)) + '</td><td>' + (k.hold_ms || 0) + '</td><td>' + (k.fade_ms || 0) + '</td></tr>').join('')
        || '<tr><td colspan="4" style="color:var(--muted)">No frames yet</td></tr>';
    body.querySelectorAll('tr[data-i]').forEach(tr => tr.onclick = () => { aeReadLights(); ae.sel = +tr.dataset.i; aeRender(); });
    const k = kfs[ae.sel];
    document.getElementById('aeFrameTitle').textContent = k ? 'Frame ' + (ae.sel + 1) : 'No frame selected';
    document.getElementById('aeHold').value = k ? (k.hold_ms || 0) : '';
    document.getElementById('aeFade').value = k ? (k.fade_ms || 0) : '';
    const lb = document.getElementById('aeLights');
    lb.innerHTML = k ? Object.entries(k.lights || {}).map(([key, p]) => {
        const m = (p.mode || 'HSI').toUpperCase() === 'SCENE' ? 'ANM' : (p.mode || 'HSI').toUpperCase();
        let vals = '';
        if (m === 'HSI') vals = 'Hue ' + numInput('ae-hue', p.hue != null ? p.hue : 0, 0, 360) + ' Sat ' + numInput('ae-sat', p.sat != null ? p.sat : 100, 0, 100) + ' Bri ' + numInput('ae-bri', p.bri != null ? p.bri : 100, 0, 100);
        else if (m === 'CCT') vals = 'Temp ' + numInput('ae-temp', (p.temp || 56) * 100, 2700, 8500, 100) + ' K Bri ' + numInput('ae-bri', p.bri != null ? p.bri : 100, 0, 100);
        else if (m === 'ANM') vals = '<select class="ae-scene">' + SCENES.map((s, i) => '<option value="' + (i + 1) + '"' + ((p.scene || 1) === i + 1 ? ' selected' : '') + '>' + s + '</option>').join('') + '</select> Bri ' + numInput('ae-bri', p.bri != null ? p.bri : 100, 0, 100);
        return '<tr data-key="' + esc(key) + '"><td><input type="text" class="ae-key" value="' + esc(key) + '" style="width:110px"></td><td><select class="ae-mode">'
            + [['HSI', 'HSI'], ['CCT', 'CCT'], ['ANM', 'Scene'], ['ON', 'On'], ['OFF', 'Off']].map(o => '<option value="' + o[0] + '"' + (m === o[0] ? ' selected' : '') + '>' + o[1] + '</option>').join('')
            + '</select></td><td>' + vals + '</td><td><button class="btn small danger" onclick="aeRemoveLight(this)">Remove</button></td></tr>';
    }).join('') : '';
    lb.querySelectorAll('input,select').forEach(el => el.onchange = () => { aeReadLights(); if (el.classList.contains('ae-mode') || el.classList.contains('ae-key')) aeRender(); else aeRenderFrames(); });
}
function aeRenderFrames() {
    document.querySelectorAll('#aeFrames tr[data-i]').forEach(tr => {
        const k = ae.anim.keyframes[+tr.dataset.i];
        tr.children[1].textContent = aeLightSummary(k.lights);
        tr.children[2].textContent = k.hold_ms || 0;
        tr.children[3].textContent = k.fade_ms || 0;
    });
}
function aeReadLights() {
    // the selected frame's light rows back into the keyframe
    if (!ae || ae.tab !== 'visual') return;
    const k = ae.anim.keyframes[ae.sel];
    if (!k) return;
    const lights = {};
    document.querySelectorAll('#aeLights tr').forEach(tr => {
        const q = c => tr.querySelector('.' + c);
        const key = (q('ae-key').value || '*').trim();
        const mode = q('ae-mode').value;
        const old = (k.lights || {})[tr.dataset.key] || {};
        let p = {mode: mode};
        const oldMode = (old.mode || 'HSI').toUpperCase() === 'SCENE' ? 'ANM' : (old.mode || 'HSI').toUpperCase();
        if (mode === oldMode) {
            if (mode === 'HSI') p = {mode: 'HSI', hue: +q('ae-hue').value, sat: +q('ae-sat').value, bri: +q('ae-bri').value};
            else if (mode === 'CCT') p = {mode: 'CCT', temp: Math.round(+q('ae-temp').value / 100), bri: +q('ae-bri').value};
            else if (mode === 'ANM') p = {mode: 'ANM', scene: +q('ae-scene').value, bri: +q('ae-bri').value};
        } else {
            const bri = old.bri != null ? old.bri : 100;
            if (mode === 'HSI') p = {mode: 'HSI', hue: 240, sat: 100, bri: bri};
            else if (mode === 'CCT') p = {mode: 'CCT', temp: 56, bri: bri};
            else if (mode === 'ANM') p = {mode: 'ANM', scene: 1, bri: bri};
        }
        lights[key] = p;
    });
    k.lights = lights;
}
function aeFrameField() {
    const k = ae.anim.keyframes[ae.sel];
    if (!k) return;
    k.hold_ms = Math.max(0, +document.getElementById('aeHold').value || 0);
    k.fade_ms = Math.max(0, +document.getElementById('aeFade').value || 0);
    aeRenderFrames();
}
function aeAddFrame() {
    aeReadLights();
    const prev = ae.anim.keyframes[ae.sel];
    const k = prev ? JSON.parse(JSON.stringify(prev)) : {hold_ms: 500, fade_ms: 0, lights: {'*': {mode: 'HSI', hue: 240, sat: 100, bri: 100}}};
    ae.anim.keyframes.splice(ae.sel + 1, 0, k);
    ae.sel = Math.min(ae.sel + 1, ae.anim.keyframes.length - 1);
    aeRender();
}
function aeDupFrame() { if (ae.anim.keyframes.length) aeAddFrame(); }
function aeDelFrame() { aeReadLights(); if (ae.anim.keyframes.length <= 1) return; ae.anim.keyframes.splice(ae.sel, 1); ae.sel = Math.max(0, ae.sel - 1); aeRender(); }
function aeMoveFrame(d) {
    aeReadLights();
    const k = ae.anim.keyframes, j = ae.sel + d;
    if (j < 0 || j >= k.length) return;
    [k[ae.sel], k[j]] = [k[j], k[ae.sel]];
    ae.sel = j;
    aeRender();
}
function aeCopyFrame() { aeReadLights(); const k = ae.anim.keyframes[ae.sel]; if (k) { ae.clipboard = JSON.parse(JSON.stringify(k)); logMsg('Copied frame ' + (ae.sel + 1), 'ok'); } }
function aePasteFrame() {
    // pastes the copied frame's lights and timing over the selected frame
    if (!ae.clipboard || !ae.anim.keyframes[ae.sel]) return;
    ae.anim.keyframes[ae.sel] = JSON.parse(JSON.stringify(ae.clipboard));
    aeRender();
}
function aeAddLight() {
    aeReadLights();
    const k = ae.anim.keyframes[ae.sel];
    if (!k) return;
    k.lights = k.lights || {};
    const keys = Object.keys(k.lights);
    let key = '*';
    if (keys.length) {
        if (keys.includes('*')) delete k.lights['*'];  // a frame is either all lights or specific ones
        for (let i = 1; i < 40; i++) if (!(String(i) in k.lights)) { key = String(i); break; }
    }
    k.lights[key] = {mode: 'HSI', hue: 240, sat: 100, bri: 100};
    aeRender();
}
function aeRemoveLight(btn) {
    aeReadLights();
    const k = ae.anim.keyframes[ae.sel];
    const key = btn.closest('tr').querySelector('.ae-key').value;
    delete k.lights[key];
    if (!Object.keys(k.lights).length) k.lights['*'] = {mode: 'HSI', hue: 240, sat: 100, bri: 100};
    aeRender();
}
async function aeSave() {
    if (ae.tab === 'json') { if (!aeReadJson()) return; } else aeReadLights();
    const anim = ae.anim;
    anim.name = document.getElementById('aeName').value.trim();
    anim.description = document.getElementById('aeDesc').value.trim();
    anim.loop = document.getElementById('aeLoop').checked;
    [['fade_in_ms', 'aeFadeIn'], ['handback_fade_ms', 'aeFadeOut']].forEach(([k, id]) => {
        const v = parseInt(document.getElementById(id).value, 10);
        if (isNaN(v) || v < 0) delete anim[k]; else anim[k] = Math.min(10000, v);
    });
    anim.keyframes.forEach(k => {
        // a frame mixing * with specific lights would be ambiguous: specific lights win, as on the desktop
        if (k.lights && Object.keys(k.lights).length > 1 && '*' in k.lights) delete k.lights['*'];
        if (!k.lights || !Object.keys(k.lights).length) k.lights = {'*': {mode: 'HSI', hue: 240, sat: 100, bri: 100}};
    });
    if (!anim.name) { alert('Give the animation a name.'); return; }
    const body = {action: 'save', animation: anim};
    if (ae.original) body.original = ae.original;
    let d = await animPost(body);
    if (!d.success && /exists/.test(errText(d)) && confirm('An animation named "' + anim.name + '" already exists. Replace it?')) {
        body.overwrite = true;
        d = await animPost(body);
    }
    if (!d.success) { logMsg('Animation not saved: ' + errText(d), 'err'); return; }
    logMsg('Saved animation ' + d.animation, 'ok');
    selectedAnim = d.animation;
    aeClose();
    loadAnimations();
}

// ---------------------------------------------------------------------------
// SEQUENCES: Duplicate, Delete, and the timeline editor
async function seqDuplicate() {
    if (!selectedSeq) { logMsg('No sequence selected', 'err'); return; }
    const g = await seqPost({action: 'get', name: selectedSeq});
    if (!g.success) { logMsg('Duplicate failed: ' + errText(g), 'err'); return; }
    const names = seqNames.map(n => n.toLowerCase());
    let name = selectedSeq + ' (copy)', n = 2;
    while (names.includes(name.toLowerCase())) name = selectedSeq + ' (copy ' + (n++) + ')';
    g.sequence.name = name;
    const d = await seqPost({action: 'save', sequence: g.sequence});
    if (!d.success) { logMsg('Duplicate failed: ' + errText(d), 'err'); return; }
    logMsg('Duplicated as ' + name, 'ok');
    selectedSeq = name;
    seqReload();
}
async function seqDelete() {
    if (!selectedSeq) { logMsg('No sequence selected', 'err'); return; }
    if (!confirm('Delete sequence "' + selectedSeq + '"?')) return;
    const d = await seqPost({action: 'delete', name: selectedSeq});
    if (!d.success) { logMsg('Delete failed: ' + errText(d), 'err'); return; }
    logMsg('Deleted sequence ' + selectedSeq, 'ok');
    selectedSeq = '';
    seqReload();
}

const TL_SNAPS = [['No snap', 0], ['10 ms', 10], ['50 ms', 50], ['100 ms', 100], ['250 ms', 250], ['500 ms', 500], ['1 s', 1000], ['Beat', -1], ['Half beat', -2], ['Bar (4 beats)', -4]];
let tl = null;

function tlGridStep(snap, bpm) {
    if (snap > 0) return snap;
    if (snap < 0 && bpm > 0) { const beat = 60000 / bpm; return snap === -2 ? beat / 2 : beat * (-snap); }
    return 0;
}
function tlSnapMs(ms) {
    const snap = +document.getElementById('tlSnap').value, bpm = +document.getElementById('tlBpm').value || 0;
    const step = tlGridStep(snap, bpm);
    if (step <= 0) return Math.max(0, Math.round(ms));
    const base = snap < 0 ? (+document.getElementById('tlBeatOffset').value || 0) : 0;
    return Math.max(0, Math.round(base + Math.round((ms - base) / step) * step));
}
function tlKind(c) { return 'clip' in c ? 'clip' : 'state'; }
function tlClipName(c) { return typeof c.clip === 'string' ? c.clip : (c.clip || {}).name || ''; }
function tlFmt(ms, precise) {
    ms = Math.max(0, Math.round(ms));
    const s = Math.floor(ms / 1000);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0') + (precise ? '.' + String(ms % 1000).padStart(3, '0') : '');
}
function tlDescribe(c) {
    if (tlKind(c) === 'clip') { const fit = typeof c.clip === 'object' && c.clip.fit ? c.clip.fit : 'stretch'; return tlClipName(c) + ' (' + fit + ')'; }
    const st = c.state || {};
    let t = st.mode === 'CCT' ? ((st.temp || 56) * 100) + 'K ' + (st.bri != null ? st.bri : 100) + '%' : 'H' + (st.hue || 0) + ' S' + (st.sat != null ? st.sat : 100) + ' ' + (st.bri != null ? st.bri : 100) + '%';
    if (st.fade_ms) t += ', fade ' + (st.fade_ms / 1000).toFixed(1) + 's';
    return t;
}
function tlKelvinRGB(k) {
    const t = Math.max(1000, Math.min(40000, k)) / 100;
    let r, g, b;
    if (t <= 66) { r = 255; g = 99.47 * Math.log(t) - 161.12; b = t <= 19 ? 0 : 138.52 * Math.log(t - 10) - 305.04; }
    else { r = 329.7 * Math.pow(t - 60, -0.1332); g = 288.12 * Math.pow(t - 60, -0.0755); b = 255; }
    return [r, g, b].map(v => Math.max(0, Math.min(255, v)));
}
function tlCueColour(c) {
    // the cue's colour at a readable brightness (as the desktop editor draws it)
    if (tlKind(c) !== 'state') return null;
    const st = c.state || {}, level = 0.4 + 0.6 * Math.sqrt(Math.max(60, st.bri != null ? st.bri : 100) / 100);
    let rgb;
    if (st.mode === 'CCT') rgb = tlKelvinRGB((st.temp || 56) * 100);
    else {
        const h = ((st.hue || 0) % 360) / 60, s = (st.sat != null ? st.sat : 100) / 100, x = 1 - Math.abs(h % 2 - 1);
        const [r1, g1, b1] = h < 1 ? [1, x, 0] : h < 2 ? [x, 1, 0] : h < 3 ? [0, 1, x] : h < 4 ? [0, x, 1] : h < 5 ? [x, 0, 1] : [1, 0, x];
        rgb = [r1, g1, b1].map(v => 255 * (1 - s + s * v));
    }
    return 'rgb(' + rgb.map(v => Math.round(v * level)).join(',') + ')';
}
function tlSpans(seq, idxs) {
    const cues = seq.cues, dur = +seq.duration_ms || 0;
    const order = idxs.slice().sort((a, b) => ((+cues[a].at_ms || 0) - (+cues[b].at_ms || 0)) || a - b);
    const spans = {};
    order.forEach((i, pos) => {
        const c = cues[i], start = +c.at_ms || 0, d = +c.duration_ms || 0;
        if (tlKind(c) === 'clip' || d > 0) spans[i] = [start, start + Math.max(1, d), false];
        else {
            let nxt = dur;
            for (const j of order.slice(pos + 1)) { if ((+cues[j].at_ms || 0) > start) { nxt = +cues[j].at_ms || 0; break; } }
            spans[i] = [start, Math.max(start + 1, nxt), true];
        }
    });
    return spans;
}
function tlColourAt(changes, t) {
    let lo = 0, hi = changes.length - 1, found = null;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (changes[mid][0] <= t) { found = changes[mid]; lo = mid + 1; } else hi = mid - 1; }
    return found;
}

async function tlOpenSelected() {
    if (!selectedSeq) { logMsg('No sequence selected', 'err'); return; }
    tlOpen(selectedSeq);
}
function tlNewMenu(ev) {
    const starters = seqNames.filter(n => n.startsWith('Starter - ')).sort();
    showMenu(ev, [{label: 'Blank sequence', fn: () => tlOpen(null)}].concat(starters.map(n => ({label: 'From ' + n, fn: () => tlOpen(null, n)}))));
}
async function tlOpen(name, template) {
    let seq, original = null;
    if (!name && template) {
        const g = await seqPost({action: 'get', name: template});
        if (!g.success) { logMsg('Can\'t open: ' + errText(g), 'err'); return; }
        const names = seqNames.map(n => n.toLowerCase()), base = template.replace(/^Starter - /, '');
        let nm = base, n = 2;
        while (names.includes(nm.toLowerCase())) nm = base + ' ' + (n++);
        seq = g.sequence;
        seq.name = nm;
    } else if (name) {
        const g = await seqPost({action: 'get', name: name});
        if (!g.success) { logMsg('Can\'t open: ' + errText(g), 'err'); return; }
        seq = g.sequence;
        original = g.sequence.name;
    } else {
        const names = seqNames.map(n => n.toLowerCase());
        let nm = 'New Sequence', n = 2;
        while (names.includes(nm.toLowerCase())) nm = 'New Sequence ' + (n++);
        seq = {format: 1, name: nm, duration_ms: 30000, cues: [{at_ms: 0, target: '*', state: {mode: 'CCT', temp: 45, bri: 50}}]};
    }
    tl = {seq: JSON.parse(JSON.stringify(seq)), original: original, dirty: false, sel: [], undo: [], redo: [], clipboard: (tl && tl.clipboard) || [],
          playhead: 0, playing: false, playStart: [0, 0], send: false, pxPerSec: 40, offsetMs: 0, tracks: [], cueLights: {},
          info: null, render: null, drag: null, hits: [], renderTimer: null, restartTimer: null};
    tl.seq.cues = tl.seq.cues || [];
    const snapSel = document.getElementById('tlSnap');
    snapSel.innerHTML = TL_SNAPS.map(s => '<option value="' + s[1] + '">' + s[0] + '</option>').join('');
    snapSel.value = '100';
    document.getElementById('tlName').value = tl.seq.name || '';
    document.getElementById('tlDuration').value = ((+tl.seq.duration_ms || 30000) / 1000);
    const tempo = tl.seq.tempo || {};
    document.getElementById('tlBpm').value = tempo.bpm || 0;
    document.getElementById('tlBeatOffset').value = tempo.offset_ms || 0;
    document.getElementById('tlSend').checked = false;
    document.getElementById('tlSettings').style.display = 'none';
    document.getElementById('tlModal').classList.add('open');
    await tlRefreshInfo();
    tlFit();
    tlRerender();
    tlUpdateTitle();
}
async function tlRefreshInfo() {
    const targets = [...new Set(tl.seq.cues.map(c => String(c.target == null ? '*' : c.target)))];
    tl.info = await seqPost({action: 'editor', targets: targets});
    tlRebuildTracks();
}
function tlRebuildTracks() {
    const info = tl.info;
    if (!info) return;
    tl.tracks = info.lights.map(l => ({id: String(l.id), label: l.id + '  ' + l.name, sub: (l.role ? l.role.charAt(0).toUpperCase() + l.role.slice(1) : '') + (l.side ? ', ' + l.side : '') + (l.simulated ? ' (simulated)' : ''), cues: [], target: String(l.id), name: l.name, role: l.role, simulated: l.simulated}));
    const byId = {};
    tl.tracks.forEach(t => byId[t.id] = t);
    const orphans = [];
    tl.cueLights = {};
    tl.seq.cues.forEach((c, i) => {
        const ids = (info.targets[String(c.target == null ? '*' : c.target)] || []).filter(id => byId[id]);
        tl.cueLights[i] = ids;
        if (ids.length) ids.forEach(id => byId[id].cues.push(i)); else orphans.push(i);
    });
    if (orphans.length) tl.tracks.push({id: null, label: 'No matching light', sub: 'cues for lights that aren\'t here', cues: orphans, target: '*'});
    tlResizeCanvas();
}
function tlMetrics() {
    const cv = document.getElementById('tlCanvas');
    const ctx = cv.getContext('2d');
    ctx.font = '13px sans-serif';
    const labelW = Math.min(220, Math.max(110, ...tl.tracks.map(t => ctx.measureText(t.label).width + 18), 80));
    return {rowH: 36, rulerH: 24, labelW: labelW, W: cv.clientWidth};
}
function tlResizeCanvas() {
    const cv = document.getElementById('tlCanvas');
    const m = tlMetrics();
    const h = m.rulerH + m.rowH * Math.max(1, tl.tracks.length) + 14;
    const dpr = window.devicePixelRatio || 1;
    cv.style.height = h + 'px';
    cv.width = Math.max(300, cv.clientWidth) * dpr;
    cv.height = h * dpr;
    tlDraw();
}
window.addEventListener('resize', () => { if (tl && document.getElementById('tlModal').classList.contains('open')) tlResizeCanvas(); });
function tlX(ms) { const m = tlMetrics(); return m.labelW + (ms - tl.offsetMs) * tl.pxPerSec / 1000; }
function tlMs(x) { const m = tlMetrics(); return tl.offsetMs + (x - m.labelW) * 1000 / tl.pxPerSec; }
function tlVisibleMs() { const m = tlMetrics(); return Math.max(1, (m.W - m.labelW) * 1000 / tl.pxPerSec); }
function tlZoom(f, anchorMs) {
    if (anchorMs == null) anchorMs = tl.offsetMs + tlVisibleMs() / 2;
    const ax = tlX(anchorMs), m = tlMetrics();
    tl.pxPerSec = Math.max(2, Math.min(2000, tl.pxPerSec * f));
    tl.offsetMs = Math.max(0, anchorMs - (ax - m.labelW) * 1000 / tl.pxPerSec);
    tlDraw();
}
function tlFit() {
    const m = tlMetrics(), dur = Math.max(1000, +tl.seq.duration_ms || 1000);
    tl.pxPerSec = Math.max(2, (Math.max(300, m.W) - m.labelW - 14) * 1000 / dur);
    tl.offsetMs = 0;
    tlDraw();
}

function tlDraw() {
    if (!tl) return;
    const cv = document.getElementById('tlCanvas');
    const dpr = window.devicePixelRatio || 1;
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const m = tlMetrics(), W = cv.clientWidth, H = cv.height / dpr;
    const {rowH, rulerH, labelW} = m;
    const seq = tl.seq, dur = +seq.duration_ms || 0;
    ctx.fillStyle = '#1a1a1e'; ctx.fillRect(0, 0, W, H);
    ctx.font = '12px sans-serif'; ctx.textBaseline = 'middle';
    tl.hits = [];
    const t0 = tl.offsetMs, t1 = t0 + tlVisibleMs();
    const tick = [100, 250, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000].find(s => s * tl.pxPerSec / 1000 >= 60) || 300000;
    for (let t = Math.floor(t0 / tick) * tick; t <= t1; t += tick) {
        const x = tlX(t);
        if (x < labelW) continue;
        ctx.fillStyle = '#303038'; ctx.fillRect(x, rulerH, 1, H - rulerH);
        ctx.fillStyle = '#aaaab4'; ctx.fillRect(x, rulerH - 6, 1, 6);
        ctx.fillText(tick >= 1000 ? tlFmt(t) : (t / 1000).toFixed(2) + 's', x + 3, rulerH / 2);
    }
    const bpm = +document.getElementById('tlBpm').value || 0;
    if (bpm > 0) {
        const beat = 60000 / bpm, off = +document.getElementById('tlBeatOffset').value || 0;
        if (beat * tl.pxPerSec / 1000 >= 6) {
            let k = Math.floor((t0 - off) / beat);
            for (let bt = off + k * beat; bt <= t1; bt += beat, k++) {
                const x = tlX(bt);
                if (x < labelW) continue;
                ctx.fillStyle = (k % 4 === 0) ? '#5a4682' : '#372d4b';
                ctx.fillRect(x, rulerH, 1, H - rulerH);
            }
        }
    }
    const xEnd = tlX(dur);
    if (xEnd < W) { ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.fillRect(Math.max(labelW, xEnd), rulerH, W - Math.max(labelW, xEnd), H - rulerH); }
    const changesById = (tl.render && tl.render.changes) || {};
    const renderEnd = tl.render ? tl.render.end_ms : dur;
    tl.tracks.forEach((track, row) => {
        const y = rulerH + row * rowH;
        ctx.fillStyle = '#37373e'; ctx.fillRect(0, y + rowH - 1, W, 1);
        const bandH = 6;
        const ch = track.id != null ? (changesById[track.id] || []) : [];
        ch.forEach((c, k) => {
            const end = k + 1 < ch.length ? ch[k + 1][0] : renderEnd;
            const xa = Math.max(labelW, tlX(c[0])), xb = Math.min(W, tlX(end));
            if (xb > xa && c[1]) { ctx.fillStyle = c[1]; ctx.fillRect(xa, y + rowH - bandH - 1, xb - xa, bandH); }
        });
        const spans = tlSpans(seq, track.cues);
        Object.keys(spans).forEach(key => {
            const i = +key, [start, end, hold] = spans[i], c = seq.cues[i];
            const xa = tlX(start), xb = tlX(end);
            if (xb < labelW || xa > W) return;
            const top = y + 3, h = rowH - bandH - 8;
            const base = tlCueColour(c) || 'rgb(70,95,140)';
            const L = Math.max(labelW, xa), R = Math.min(W, xb);
            const fade = tlKind(c) === 'state' ? (+(c.state || {}).fade_ms || 0) : 0;
            const xh = Math.min(xb, Math.max(xa + 8, tlX(start + fade)));
            if (hold) {
                ctx.globalAlpha = 0.28; ctx.fillStyle = base; ctx.fillRect(L, top, Math.max(0, R - L), h); ctx.globalAlpha = 1;
                ctx.fillStyle = base; ctx.fillRect(L, top, Math.max(2, Math.min(W, xh) - L), h);
            } else {
                ctx.fillStyle = base; ctx.fillRect(L, top, Math.max(2, R - L), h);
            }
            if (fade) {
                const xf = tlX(start + fade);
                if (xf > labelW) { ctx.fillStyle = 'rgba(0,0,0,.28)'; ctx.beginPath(); ctx.moveTo(L, top + h); ctx.lineTo(Math.min(W, xf), top); ctx.lineTo(L, top); ctx.fill(); }
            }
            const isSel = tl.sel.includes(i), shared = (tl.cueLights[i] || []).length > 1;
            ctx.setLineDash(shared && !isSel ? [4, 3] : []);
            ctx.lineWidth = isSel ? 2 : 1;
            ctx.strokeStyle = isSel ? '#ffffff' : 'rgba(0,0,0,.65)';
            ctx.strokeRect(L + 0.5, top + 0.5, Math.max(2, R - L) - 1, h - 1);
            ctx.setLineDash([]);
            const label = c.label || tlDescribe(c);
            if (R - L > 30) {
                ctx.save(); ctx.beginPath(); ctx.rect(L + 3, top, R - L - 6, h); ctx.clip();
                const m2 = base.match(/\d+/g) || [0, 0, 0], lum = 0.3 * m2[0] + 0.59 * m2[1] + 0.11 * m2[2];
                ctx.fillStyle = (lum > 140 && !hold) ? '#0a0a0a' : '#ebebeb';
                ctx.fillText(label, L + 5, top + h / 2);
                ctx.restore();
            }
            if (hold) { tl.hits.push([xa, top, Math.max(4, xh - xa), h, i, 'body', row]); tl.hits.push([xh, top, Math.max(0, xb - xh), h, i, 'tail', row]); }
            else { tl.hits.push([xa, top, Math.max(4, xb - xa), h, i, 'body', row]); tl.hits.push([xb - 5, top, 10, h, i, 'end', row]); }
            if (tlKind(c) === 'state') { const xf = tlX(start + fade); tl.hits.push([xf - 4, top, 8, h / 3, i, 'fade', row]); }
        });
        ctx.fillStyle = '#22222a'; ctx.fillRect(0, y, labelW, rowH);
        ctx.save(); ctx.beginPath(); ctx.rect(0, y, labelW - 4, rowH); ctx.clip();
        ctx.fillStyle = track.id != null ? '#e1e1e6' : '#dc9650';
        ctx.font = '13px sans-serif'; ctx.fillText(track.label, 8, y + rowH * 0.36);
        ctx.fillStyle = '#8c8c96'; ctx.font = '11px sans-serif'; ctx.fillText(track.sub, 8, y + rowH * 0.72);
        ctx.restore();
        ctx.font = '12px sans-serif';
    });
    ctx.fillStyle = '#22222a'; ctx.fillRect(0, 0, labelW, rulerH);
    ctx.fillStyle = '#9696a0'; ctx.fillText(tlFmt(dur, true), 8, rulerH / 2);
    const xp = tlX(tl.playhead);
    if (xp >= labelW && xp <= W) {
        ctx.fillStyle = '#ff5050'; ctx.fillRect(xp - 1, 0, 2, H);
        ctx.beginPath(); ctx.moveTo(xp - 6, 0); ctx.lineTo(xp + 6, 0); ctx.lineTo(xp, 8); ctx.fill();
    }
}

function tlHitAt(x, y) {
    let best = null, tail = null;
    for (let k = tl.hits.length - 1; k >= 0; k--) {
        const [hx, hy, hw, hh, i, kind, row] = tl.hits[k];
        if (x >= hx && x <= hx + hw && y >= hy && y <= hy + hh) {
            if (kind === 'end' || kind === 'fade') return {i: i, kind: kind, row: row};
            if (kind === 'body' && !best) best = {i: i, kind: kind, row: row};
            if (kind === 'tail' && !tail) tail = {i: i, kind: kind, row: row};
        }
    }
    return best || tail;
}
function tlTrackAt(y) {
    const m = tlMetrics();
    if (y < m.rulerH) return -1;
    const r = Math.floor((y - m.rulerH) / m.rowH);
    return r >= 0 && r < tl.tracks.length ? r : null;
}
function tlEventPos(ev) { const r = document.getElementById('tlCanvas').getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; }

function tlPushUndo() { tl.undo.push([JSON.stringify(tl.seq), tl.sel.slice()]); if (tl.undo.length > 200) tl.undo.shift(); tl.redo = []; }
function tlUndo() { if (!tl || !tl.undo.length) return; tl.redo.push([JSON.stringify(tl.seq), tl.sel.slice()]); const [s, sel] = tl.undo.pop(); tl.seq = JSON.parse(s); tl.sel = sel.filter(i => i < tl.seq.cues.length); tlAfterReplace(); }
function tlRedo() { if (!tl || !tl.redo.length) return; tl.undo.push([JSON.stringify(tl.seq), tl.sel.slice()]); const [s, sel] = tl.redo.pop(); tl.seq = JSON.parse(s); tl.sel = sel.filter(i => i < tl.seq.cues.length); tlAfterReplace(); }
function tlAfterReplace() {
    document.getElementById('tlName').value = tl.seq.name || '';
    document.getElementById('tlDuration').value = (+tl.seq.duration_ms || 1000) / 1000;
    tlChanged();
    tlProps();
}
function tlChanged(live) {
    tl.dirty = true;
    tlUpdateTitle();
    if (!live) {
        const known = new Set(Object.keys((tl.info && tl.info.targets) || {}));
        const missing = tl.seq.cues.some(c => !known.has(String(c.target == null ? '*' : c.target)));
        if (missing) tlRefreshInfo(); else tlRebuildTracks();
    }
    tlDraw();
    clearTimeout(tl.renderTimer);
    tl.renderTimer = setTimeout(tlRerender, live ? 120 : 40);
    if (tl.send && tl.playing) { clearTimeout(tl.restartTimer); tl.restartTimer = setTimeout(tlRestartOnLights, 300); }
}
async function tlRerender() {
    if (!tl) return;
    const d = await seqPost({action: 'render', sequence: tl.seq});
    if (d.success) {
        tl.render = d;
        const w = (d.warnings || []).slice();
        const fl = d.flashes || {}, rate = Math.max(fl.worst || 0, fl.worstRed || 0);
        if (rate > (fl.limit || 3)) w.unshift('flashes up to ' + rate.toFixed(1) + ' times a second; the flash guard (if on) will hold some back');
        tlStatus(w.length ? 'Warnings: ' + w.join('; ') : '', w.length ? 'warn' : '');
    } else {
        tlStatus('Won\'t play yet: ' + errText(d), 'error');
    }
    tlDraw();
    tlUpdateStage();
}
function tlStatus(text, level) {
    const el = document.getElementById('tlStatus');
    el.style.color = {error: '#e06060', warn: '#d8a040', ok: '#60c070'}[level] || 'var(--muted)';
    el.textContent = text;
}
function tlUpdateTitle() {
    document.querySelector('#tlModal .toolbar').title = (tl.dirty ? 'Unsaved changes' : '');
    document.getElementById('tlName').style.borderColor = tl.dirty ? 'var(--accent)' : '';
}
function tlSetSel(sel) {
    tl.sel = [...new Set(sel)].filter(i => i >= 0 && i < tl.seq.cues.length);
    tlProps();
    tlDraw();
}

// --- mouse and keys
(function tlWire() {
    const cv = document.getElementById('tlCanvas');
    cv.addEventListener('mousedown', ev => {
        if (!tl) return;
        cv.focus();
        const [x, y] = tlEventPos(ev), m = tlMetrics();
        if (ev.button === 2) return;
        const row = tlTrackAt(y);
        if (row === -1 && x >= m.labelW) { tlSetPlayhead(tlMs(x)); tl.drag = {kind: 'scrub'}; return; }
        const hit = tlHitAt(x, y);
        const multi = ev.ctrlKey || ev.metaKey || ev.shiftKey;
        if (!hit) {
            if (!multi) tlSetSel([]);
            if (x >= m.labelW && row != null) tlSetPlayhead(tlMs(x));
            return;
        }
        if (multi) { const s = tl.sel.slice(), k = s.indexOf(hit.i); if (k >= 0) s.splice(k, 1); else s.push(hit.i); tlSetSel(s); }
        else if (!tl.sel.includes(hit.i)) tlSetSel([hit.i]);
        const orig = {};
        tl.sel.forEach(j => { const c = tl.seq.cues[j]; orig[j] = [+c.at_ms || 0, +c.duration_ms || 0, tlKind(c) === 'state' ? (+(c.state || {}).fade_ms || 0) : 0]; });
        tl.drag = {kind: hit.kind === 'tail' ? 'body' : hit.kind, cue: hit.i, x0: x, moved: false, orig: orig};
    });
    window.addEventListener('mousemove', ev => {
        if (!tl || !document.getElementById('tlModal').classList.contains('open')) return;
        const [x, y] = tlEventPos(ev);
        const d = tl.drag;
        if (!d) {
            if (ev.target !== cv) return;
            const hit = tlHitAt(x, y);
            cv.style.cursor = hit ? (hit.kind === 'end' ? 'ew-resize' : hit.kind === 'fade' ? 'col-resize' : 'grab') : 'default';
            cv.title = hit ? tlFmt(tl.seq.cues[hit.i].at_ms || 0, true) + '  ' + (tl.seq.cues[hit.i].target || '*') + '\n' + tlDescribe(tl.seq.cues[hit.i]) : '';
            return;
        }
        if (d.kind === 'scrub') { tlSetPlayhead(tlMs(x)); return; }
        const dms = (x - d.x0) * 1000 / tl.pxPerSec;
        if (!d.moved) { if (Math.abs(x - d.x0) < 3) return; tlPushUndo(); d.moved = true; }
        const cues = tl.seq.cues, [aAt, aDur, aFade] = d.orig[d.cue];
        if (d.kind === 'body') {
            let shift = tlSnapMs(aAt + dms) - aAt;
            shift = Math.max(shift, -Math.min(...Object.values(d.orig).map(o => o[0])));
            Object.entries(d.orig).forEach(([j, o]) => cues[+j].at_ms = o[0] + shift);
        } else if (d.kind === 'end') {
            cues[d.cue].duration_ms = Math.max(10, tlSnapMs(aAt + aDur + dms) - aAt);
        } else if (d.kind === 'fade') {
            (cues[d.cue].state = cues[d.cue].state || {}).fade_ms = Math.max(0, tlSnapMs(aAt + aFade + dms) - aAt);
        }
        tlChanged(true);
    });
    window.addEventListener('mouseup', () => {
        if (!tl || !tl.drag) return;
        const moved = tl.drag.moved;
        tl.drag = null;
        if (moved) { tlChanged(); tlProps(); }
    });
    cv.addEventListener('dblclick', ev => {
        if (!tl) return;
        const [x, y] = tlEventPos(ev), hit = tlHitAt(x, y);
        if (hit && hit.kind !== 'tail') return;
        const row = tlTrackAt(y);
        if (row != null && row >= 0 && x >= tlMetrics().labelW) tlAddCueAt('state', row, tlSnapMs(tlMs(x)));
    });
    cv.addEventListener('wheel', ev => {
        if (!tl) return;
        ev.preventDefault();
        const [x] = tlEventPos(ev);
        if (ev.ctrlKey) tlZoom(ev.deltaY < 0 ? 1.25 : 0.8, tlMs(x));
        else { tl.offsetMs = Math.max(0, tl.offsetMs + (Math.abs(ev.deltaX) > Math.abs(ev.deltaY) ? ev.deltaX : ev.deltaY) / 120 * tlVisibleMs() / 8); tlDraw(); }
    }, {passive: false});
    cv.addEventListener('contextmenu', ev => {
        if (!tl) return;
        const [x, y] = tlEventPos(ev), hit = tlHitAt(x, y), row = tlTrackAt(y), at = tlSnapMs(tlMs(x));
        const items = [];
        if (hit) {
            if (!tl.sel.includes(hit.i)) tlSetSel([hit.i]);
            items.push({label: 'Duplicate', fn: tlDuplicate}, {label: 'Copy', fn: tlCopy}, {label: 'Delete', fn: tlDelete}, '-');
        }
        if (row != null && row >= 0) {
            items.push({label: 'Add colour cue here', fn: () => tlAddCueAt('state', row, at)}, {label: 'Add clip cue here', fn: () => tlAddCueAt('clip', row, at)});
            if (tl.clipboard.length) items.push({label: 'Paste here', fn: () => tlPaste(at)});
        }
        if (items.length) showMenu(ev, items); else ev.preventDefault();
    });
    document.addEventListener('keydown', ev => {
        if (!tl || !document.getElementById('tlModal').classList.contains('open')) return;
        const typing = /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
        const ctrl = ev.ctrlKey || ev.metaKey, k = ev.key.toLowerCase();
        if (ctrl && k === 's') { ev.preventDefault(); tlSave(false); return; }
        if (typing) return;
        if (ctrl && k === 'z' && !ev.shiftKey) { ev.preventDefault(); tlUndo(); }
        else if (ctrl && (k === 'y' || (k === 'z' && ev.shiftKey))) { ev.preventDefault(); tlRedo(); }
        else if (ctrl && k === 'c') { ev.preventDefault(); tlCopy(); }
        else if (ctrl && k === 'v') { ev.preventDefault(); tlPaste(tlSnapMs(tl.playhead)); }
        else if (ctrl && k === 'd') { ev.preventDefault(); tlDuplicate(); }
        else if (ctrl && k === 'a') { ev.preventDefault(); tlSetSel(tl.seq.cues.map((_, i) => i)); }
        else if (k === 'delete' || k === 'backspace') { ev.preventDefault(); tlDelete(); }
        else if (k === ' ') { ev.preventDefault(); tlTogglePlay(); }
        else if (k === 'home') { ev.preventDefault(); tlSetPlayhead(0); }
        else if (k === 'escape') { tlSetSel([]); }
    });
})();

// --- editing actions
function tlSelectedRow() {
    const i = tl.sel[0];
    if (i == null) return null;
    const ids = tl.cueLights[i] || [];
    const r = tl.tracks.findIndex(t => t.id != null && t.id === ids[0]);
    return r >= 0 ? r : null;
}
function tlAddCue(kind) { tlAddCueAt(kind, tlSelectedRow(), tlSnapMs(tl.playhead)); }
function tlAddCueAt(kind, row, at) {
    const track = row != null && row >= 0 ? tl.tracks[row] : null;
    const target = track ? track.target : '*';
    at = Math.max(0, Math.min(Math.round(at), (+tl.seq.duration_ms || 1) - 1));
    let cue;
    if (kind === 'clip') {
        const names = (tl.info && tl.info.animations) || [];
        cue = {at_ms: at, duration_ms: 4000, target: target, clip: {name: names[0] || '', fit: 'stretch'}};
    } else {
        // start from the light's colour at that point, so a new cue is an easy tweak
        let st = {mode: 'HSI', hue: 0, sat: 100, bri: 80};
        if (track) {
            const spans = tlSpans(tl.seq, track.cues);
            const before = Object.keys(spans).map(Number).filter(i => spans[i][0] <= at && tlKind(tl.seq.cues[i]) === 'state');
            if (before.length) {
                const prev = before.reduce((a, b) => (+tl.seq.cues[b].at_ms || 0) >= (+tl.seq.cues[a].at_ms || 0) ? b : a);
                st = JSON.parse(JSON.stringify(tl.seq.cues[prev].state || st));
                delete st.fade_ms;
            }
        }
        cue = {at_ms: at, target: target, state: st};
    }
    tlPushUndo();
    tl.seq.cues.push(cue);
    tl.sel = [tl.seq.cues.length - 1];
    tlChanged();
    tlProps();
}
function tlDelete() {
    if (!tl.sel.length) return;
    tlPushUndo();
    tl.sel.slice().sort((a, b) => b - a).forEach(i => tl.seq.cues.splice(i, 1));
    tl.sel = [];
    tlChanged();
    tlProps();
}
function tlCopy() {
    const cues = tl.sel.slice().sort((a, b) => a - b).map(i => JSON.parse(JSON.stringify(tl.seq.cues[i])));
    if (!cues.length) return;
    const first = Math.min(...cues.map(c => +c.at_ms || 0));
    cues.forEach(c => c.at_ms = (+c.at_ms || 0) - first);
    tl.clipboard = cues;
}
function tlPaste(at) {
    if (!tl.clipboard.length) return;
    tlPushUndo();
    const start = tl.seq.cues.length;
    tl.clipboard.forEach(c => { const n = JSON.parse(JSON.stringify(c)); n.at_ms = Math.round(at) + (+n.at_ms || 0); tl.seq.cues.push(n); });
    tl.sel = tl.seq.cues.map((_, i) => i).slice(start);
    tlChanged();
    tlProps();
}
function tlDuplicate() {
    if (!tl.sel.length) return;
    const cues = tl.sel.map(i => tl.seq.cues[i]);
    const first = Math.min(...cues.map(c => +c.at_ms || 0));
    const span = Math.max(...cues.map(c => (+c.at_ms || 0) + (+c.duration_ms || 0))) - first;
    tlCopy();
    tlPaste(first + Math.max(span, 500));
}

// --- properties panel
function tlProps() {
    const el = document.getElementById('tlProps');
    if (!tl) return;
    const sel = tl.sel.filter(i => i < tl.seq.cues.length);
    if (!sel.length) { el.innerHTML = '<b>No cue selected</b><p style="color:var(--muted)">Select a cue to edit it, or double-click a track to add one.</p>'; return; }
    if (sel.length > 1) {
        el.innerHTML = '<b>' + sel.length + ' cues selected</b><p style="color:var(--muted)">Drag any of them to move them together.</p><div class="btn-row"><button class="btn small" onclick="tlDuplicate()">Duplicate selected</button><button class="btn small danger" onclick="tlDelete()">Delete selected</button></div>';
        return;
    }
    const c = tl.seq.cues[sel[0]], kind = tlKind(c), st = c.state || {};
    const clip = typeof c.clip === 'string' ? {name: c.clip} : (c.clip || {});
    const choices = ((tl.info && tl.info.choices) || []).map(o => '<option value="' + esc(o.target) + '">' + esc(o.label) + '</option>').join('');
    const ids = tl.cueLights[sel[0]] || [];
    const names = ids.map(id => (tl.tracks.find(t => t.id === id) || {}).name || id);
    let html = '<b>Cue at ' + tlFmt(c.at_ms || 0, true) + '</b><div class="form-grid" style="margin-top:8px">'
        + '<label>Start (s)</label><input type="number" id="tpStart" step="0.1" min="0" value="' + ((+c.at_ms || 0) / 1000) + '">'
        + '<label>Lights</label><input type="text" id="tpTarget" list="tpTargets" value="' + esc(c.target == null ? '*' : c.target) + '" title="An ID, a name, @key/@fill/@rim/@background/@practical, @left/@right, @all or *, several joined with ;"><datalist id="tpTargets">' + choices + '</datalist>'
        + '<span></span><span style="color:var(--muted)">' + (ids.length ? 'Drives: ' + esc(names.join(', ')) : 'Matches no light right now') + '</span>'
        + '<label>Type</label><select id="tpKind"><option value="state"' + (kind === 'state' ? ' selected' : '') + '>Colour</option><option value="clip"' + (kind === 'clip' ? ' selected' : '') + '>Clip (animation)</option></select>';
    if (kind === 'state') {
        const mode = st.mode || 'HSI';
        html += '<label>Mode</label><select id="tpMode"><option' + (mode === 'HSI' ? ' selected' : '') + '>HSI</option><option' + (mode === 'CCT' ? ' selected' : '') + '>CCT</option></select>';
        if (mode === 'HSI') html += '<label>Hue</label><input type="number" id="tpHue" min="0" max="360" value="' + (st.hue || 0) + '"><label>Saturation</label><input type="number" id="tpSat" min="0" max="100" value="' + (st.sat != null ? st.sat : 100) + '">';
        else html += '<label>Colour temp (K)</label><input type="number" id="tpTemp" min="3200" max="8500" step="100" value="' + ((st.temp || 56) * 100) + '">';
        html += '<label>Brightness</label><input type="number" id="tpBri" min="0" max="100" value="' + (st.bri != null ? st.bri : 100) + '">'
            + '<label>Fade in (ms)</label><input type="number" id="tpFade" min="0" step="100" value="' + (st.fade_ms || 0) + '">'
            + '<span></span><span style="display:block;height:16px;border:1px solid #555;background:' + tlCueColour(c) + '"></span>'
            + '<label>Length (ms)</label><input type="number" id="tpDur" min="0" step="100" value="' + (+c.duration_ms || 0) + '" title="0 holds until a later cue changes the light; a length ends it and the light goes back">'
            + '<span></span><span style="color:var(--muted)">0 = hold until the next cue</span>';
    } else {
        const anims = (tl.info && tl.info.animations) || [];
        html += '<label>Animation</label><select id="tpClip">' + anims.map(n => '<option' + (n.toLowerCase() === (clip.name || '').toLowerCase() ? ' selected' : '') + '>' + esc(n) + '</option>').join('') + '</select>'
            + '<label>Fit</label><select id="tpFit"><option value="stretch"' + ((clip.fit || 'stretch') === 'stretch' ? ' selected' : '') + '>Stretch to fit</option><option value="loop"' + (clip.fit === 'loop' ? ' selected' : '') + '>Loop</option></select>'
            + '<label>Speed</label><input type="number" id="tpSpeed" min="0.05" max="20" step="0.1" value="' + (clip.speed || 1) + '">'
            + '<label>Brightness</label><input type="number" id="tpClipBri" min="0" max="100" value="' + (clip.brightness != null ? clip.brightness : 100) + '">'
            + '<label>Length (ms)</label><input type="number" id="tpDur" min="1" step="100" value="' + (+c.duration_ms || 4000) + '">';
    }
    html += '<label>Label</label><input type="text" id="tpLabel" placeholder="(optional)" value="' + esc(c.label || '') + '"></div>';
    el.innerHTML = html;
    el.querySelectorAll('input,select').forEach(inp => inp.onchange = tlPropChanged);
}
function tlPropChanged(ev) {
    const i = tl.sel[0];
    if (tl.sel.length !== 1 || i == null) return;
    const g = id => document.getElementById(id);
    const old = JSON.stringify(tl.seq.cues[i]);
    const prev = tl.seq.cues[i];
    const c = {at_ms: Math.max(0, Math.round((+g('tpStart').value || 0) * 1000)), target: (g('tpTarget').value || '*').trim() || '*'};
    const kind = g('tpKind').value;
    const dur = +g('tpDur').value || 0;
    if (kind === 'state') {
        const wasState = tlKind(prev) === 'state';
        const mode = g('tpMode') ? g('tpMode').value : 'HSI';
        const st = {mode: mode, bri: g('tpBri') ? +g('tpBri').value : 100};
        if (mode === 'HSI') { st.hue = g('tpHue') ? +g('tpHue').value : (wasState && prev.state.hue) || 0; st.sat = g('tpSat') ? +g('tpSat').value : 100; }
        else st.temp = g('tpTemp') ? Math.round(+g('tpTemp').value / 100) : 56;
        const fade = g('tpFade') ? +g('tpFade').value : 0;
        if (fade) st.fade_ms = fade;
        c.state = st;
        if (dur && wasState) c.duration_ms = dur;
    } else {
        const anims = (tl.info && tl.info.animations) || [];
        const clip = {name: g('tpClip') ? g('tpClip').value : (anims[0] || ''), fit: g('tpFit') ? g('tpFit').value : 'stretch'};
        const speed = g('tpSpeed') ? +g('tpSpeed').value : 1;
        const bri = g('tpClipBri') ? +g('tpClipBri').value : 100;
        if (speed !== 1) clip.speed = speed;
        if (bri !== 100) clip.brightness = bri;
        c.clip = clip;
        c.duration_ms = Math.max(1, tlKind(prev) === 'clip' ? (dur || 4000) : 4000);
    }
    const label = (g('tpLabel').value || '').trim();
    if (label) c.label = label;
    if (JSON.stringify(c) === old) return;
    tlPushUndo();
    tl.seq.cues[i] = c;
    tlChanged();
    tlProps();
}

// --- top bar fields, settings
function tlNameEdited() { tl.seq.name = document.getElementById('tlName').value.trim(); tl.dirty = true; tlUpdateTitle(); }
function tlDurationEdited() {
    const ms = Math.max(1000, Math.round((+document.getElementById('tlDuration').value || 1) * 1000));
    if (ms === +tl.seq.duration_ms) return;
    tlPushUndo();
    tl.seq.duration_ms = ms;
    tlChanged();
}
function tlTempoEdited() {
    const bpm = +document.getElementById('tlBpm').value || 0;
    if (bpm > 0) tl.seq.tempo = {bpm: bpm, offset_ms: +document.getElementById('tlBeatOffset').value || 0};
    else delete tl.seq.tempo;
    tl.dirty = true;
    tlDraw();
}
function tlSettingsToggle() {
    const box = document.getElementById('tlSettings');
    const open = box.style.display === 'none';
    box.style.display = open ? '' : 'none';
    if (!open) return;
    const s = tl.seq, n = (tl.info && tl.info.presets) || 0;
    document.getElementById('tlEnd').innerHTML = '<option value="revert">Return to the state before the sequence</option><option value="hold">Hold the last frame</option>'
        + Array.from({length: n}, (_, i) => '<option value="preset:' + (i + 1) + '">Recall preset ' + (i + 1) + '</option>').join('');
    document.getElementById('tlFps').value = s.fps || 0;
    document.getElementById('tlEnd').value = s.end || 'revert';
    document.getElementById('tlPause').value = s.pause_mode || 'revert';
    document.getElementById('tlInterrupt').value = s.on_interrupt || 'continue';
    document.getElementById('tlArtist').value = s.artist || '';
    document.getElementById('tlSong').value = s.song || '';
    document.getElementById('tlDesc').value = s.description || '';
    document.getElementById('tlFadeIn').value = s.fade_in_ms == null ? -1 : s.fade_in_ms;
    document.getElementById('tlFadeOut').value = s.handback_fade_ms == null ? -1 : s.handback_fade_ms;
}
function tlSettingsApply() {
    tlPushUndo();
    const s = tl.seq, g = id => document.getElementById(id);
    const fps = +g('tlFps').value || 0;
    if (fps) s.fps = Math.min(30, fps); else delete s.fps;
    [['end', 'tlEnd', 'revert'], ['pause_mode', 'tlPause', 'revert'], ['on_interrupt', 'tlInterrupt', 'continue']].forEach(([k, id, def]) => { if (g(id).value === def) delete s[k]; else s[k] = g(id).value; });
    [['artist', 'tlArtist'], ['song', 'tlSong'], ['description', 'tlDesc']].forEach(([k, id]) => { const v = g(id).value.trim(); if (v) s[k] = v; else delete s[k]; });
    [['fade_in_ms', 'tlFadeIn'], ['handback_fade_ms', 'tlFadeOut']].forEach(([k, id]) => { const v = parseInt(g(id).value, 10); if (isNaN(v) || v < 0) delete s[k]; else s[k] = Math.min(10000, v); });
    document.getElementById('tlSettings').style.display = 'none';
    tlChanged();
}

// --- check, save, close
async function tlValidate() {
    const d = await seqPost({action: 'validate', sequence: tl.seq});
    if (!d.success) { tlStatus('Problems: ' + errText(d), 'error'); return false; }
    const w = d.warnings || [];
    tlStatus(w.length ? 'OK, with warnings: ' + w.join('; ') : 'OK: the sequence is valid.', w.length ? 'warn' : 'ok');
    return true;
}
async function tlSave(saveAs) {
    let original = tl.original;
    if (saveAs) {
        const name = prompt('Save sequence as:', tl.seq.name || '');
        if (name === null || !name.trim()) return false;
        tl.seq.name = name.trim();
        document.getElementById('tlName').value = tl.seq.name;
        original = null;
    }
    const name = (tl.seq.name || '').trim();
    if (!name) { tlStatus('Give the sequence a name first.', 'error'); return false; }
    const body = {action: 'save', sequence: tl.seq};
    if (original) body.original = original;
    let d = await seqPost(body);
    if (!d.success && /exists/.test(errText(d))) {
        if (!confirm('A sequence named "' + name + '" already exists. Replace it?')) return false;
        body.overwrite = true;
        d = await seqPost(body);
    }
    if (!d.success) { tlStatus('Not saved: ' + errText(d), 'error'); return false; }
    tl.original = d.sequence;
    tl.dirty = false;
    tlUpdateTitle();
    const w = d.warnings || [];
    tlStatus('Saved' + (w.length ? ', with warnings: ' + w.join('; ') : '.'), w.length ? 'warn' : 'ok');
    selectedSeq = d.sequence;
    seqReload();
    return true;
}
function tlClose() {
    if (tl && tl.dirty && !confirm('Close without saving your changes?')) return;
    tlPause();
    document.getElementById('tlModal').classList.remove('open');
}

// --- playback and preview
function tlSetPlayhead(ms) {
    const dur = +tl.seq.duration_ms || 0;
    tl.playhead = Math.max(0, Math.min(dur, Math.round(ms)));
    if (tl.playing) { tl.playStart = [performance.now(), tl.playhead]; if (tl.send) { clearTimeout(tl.restartTimer); tl.restartTimer = setTimeout(tlRestartOnLights, 150); } }
    tlUpdateTime();
    tlUpdateStage();
    tlDraw();
}
function tlTogglePlay() { if (tl.playing) tlPause(); else tlPlay(); }
function tlPlay() {
    if (tl.playhead >= (+tl.seq.duration_ms || 0)) tl.playhead = 0;
    tl.playing = true;
    tl.playStart = [performance.now(), tl.playhead];
    document.getElementById('tlPlayBtn').textContent = 'Pause';
    if (tl.send) tlRestartOnLights();
    requestAnimationFrame(tlTick);
}
function tlPause() {
    if (!tl) return;
    const was = tl.playing;
    tl.playing = false;
    document.getElementById('tlPlayBtn').textContent = 'Play';
    if (tl.send && was) seqPost({action: 'stop'});
}
function tlStop() { tlPause(); tlSetPlayhead(0); }
function tlSendToggled() {
    tl.send = document.getElementById('tlSend').checked;
    if (tl.send && tl.playing) tlRestartOnLights();
    else if (!tl.send) seqPost({action: 'stop'});
}
async function tlRestartOnLights() {
    if (!(tl && tl.send && tl.playing)) return;
    const d = await seqPost({action: 'play', sequence: tl.seq, start_ms: tl.playhead});
    if (!d.success) { tlStatus('Can\'t send to lights: ' + errText(d), 'error'); document.getElementById('tlSend').checked = false; tl.send = false; }
    else tl.playStart = [performance.now(), tl.playhead];
}
function tlTick() {
    if (!tl || !tl.playing) return;
    let pos = tl.playStart[1] + (performance.now() - tl.playStart[0]);
    const dur = +tl.seq.duration_ms || 0;
    if (pos >= dur) { tl.playhead = dur; tlPause(); }
    else tl.playhead = Math.round(pos);
    if (tlX(tl.playhead) > tlMetrics().W - 40) tl.offsetMs = Math.max(0, tl.playhead - tlVisibleMs() * 0.2);
    tlUpdateTime();
    tlUpdateStage();
    tlDraw();
    if (tl.playing) requestAnimationFrame(tlTick);
}
function tlUpdateTime() { document.getElementById('tlTime').textContent = tlFmt(tl.playhead, true) + ' / ' + tlFmt(+tl.seq.duration_ms || 0, true); }
function tlUpdateStage() {
    if (!tl || !tl.render) return;
    const meta = {};
    tl.render.lights.forEach(l => meta[l.id] = l);
    const tiles = tl.tracks.filter(t => t.id != null).map(t => {
        const ch = tlColourAt(tl.render.changes[t.id] || [], tl.playhead);
        const mt = meta[t.id] || {};
        return {name: t.name, role: mt.role, color: ch && ch[1] ? ch[1] : null, mode: ch ? ch[3] : null, bri: ch ? ch[2] : null,
                linked: true, simulated: mt.simulated, layer: ch && ch[4] === 'sequence' ? 'show' : 'base',
                side: mt.side, depth: mt.depth, height: mt.height, aim: mt.aim};
    });
    stageLayout(document.getElementById('tlStage'), tiles, settingsData ? settingsData.global.cameraPosition : 'front');
}

// ---------------------------------------------------------------------------
// SOUND MODES
let sndDraft = null, sndName = '', sndEditing = 0;
const SND_SLIDERS = [['sensitivity', 'Sensitivity', 10, 500, '%', 100], ['range_db', 'Range', 6, 30, ' dB', 1],
                     ['floor', 'Floor', 0, 100, '%', 1], ['ceiling', 'Ceiling', 0, 100, '%', 1], ['smoothing', 'Smoothing', 0, 100, '%', 100]];
const SND_DRIVES = [['level', 'Level'], ['low', 'Bass'], ['mid', 'Mids'], ['high', 'Treble'], ['beat', 'Beat']];
const SND_METERS = [['level', 'Level'], ['low', 'Bass'], ['mid', 'Mids'], ['high', 'Treble'], ['centroid', 'Brightness of sound']];
async function sndPost(body) { return postJSON('/NeewerLux/sound', body); }
function sndPlaying() { const s = lastStatus && lastStatus.sound; return s && s.running ? s.mode : null; }
async function sndLoadModes(select) {
    const d = await sndPost({action: 'list'});
    const sel = document.getElementById('sndMode');
    const names = (d.modes || []).map(m => m.name);
    sel.innerHTML = names.map(n => '<option>' + esc(n) + '</option>').join('');
    const want = select || sndName || (lastStatus && lastStatus.sound && lastStatus.sound.lastMode) || names[0];
    sel.value = names.includes(want) ? want : names[0];
    if (sel.value) await sndLoad(sel.value);
}
async function sndLoad(name) {
    const d = await sndPost({action: 'get', name: name});
    if (!d.success) return;
    sndName = name;
    sndDraft = d.mode;
    sndRender();
}
async function sndModeChosen(name) {
    await sndLoad(name);
    if (sndPlaying() && sndPlaying() !== name) sndStart();
}
function sndEditable() {
    const out = {};
    ['sensitivity', 'range_db', 'floor', 'ceiling', 'smoothing', 'palette', 'parts'].forEach(k => { if (sndDraft[k] !== undefined) out[k] = sndDraft[k]; });
    return out;
}
let sndLiveChain = Promise.resolve(), sndLivePending = null;
function sndLive(params) {
    // edits show at once when the mode being edited is the one playing. They go one request at
    // a time (the server could apply concurrent ones out of order), merged while one is out.
    if (!sndDraft || (sndPlaying() || '').toLowerCase() !== String(sndDraft.name).toLowerCase()) return;
    sndLivePending = Object.assign(sndLivePending || {}, JSON.parse(JSON.stringify(params)));
    sndLiveChain = sndLiveChain.then(async () => {
        if (!sndLivePending) return;
        const p = sndLivePending;
        sndLivePending = null;
        const d = await sndPost({action: 'set', params: p});
        if (!d.success) document.getElementById('sndStatus').textContent = 'Not applied: ' + errText(d);
    });
}
function sndRender() {
    const d = sndDraft;
    document.getElementById('sndDesc').textContent = d.description || '';
    const defaults = {sensitivity: 1, range_db: 18, floor: 10, ceiling: 75, smoothing: 0.5};
    document.getElementById('sndSliders').innerHTML = SND_SLIDERS.map(([k, label, lo, hi, unit, scale]) => {
        const v = Math.round((d[k] !== undefined ? d[k] : defaults[k]) * scale);
        return '<div class="snd-row"><label>' + label + '</label><input type="range" id="snd_' + k + '" min="' + lo + '" max="' + hi + '" value="' + v
            + '" oninput="sndSlider(\'' + k + '\', this.value)"><span id="snd_' + k + '_v" style="min-width:48px;text-align:right">' + v + unit + '</span></div>';
    }).join('');
    const pal = d.palette || [{hue: 240, sat: 100}];
    const white = pal.length && pal[0].temp !== undefined;
    document.getElementById('sndPalKind').value = white ? 'cct' : 'hsi';
    document.getElementById('sndPalette').innerHTML = pal.map((e, i) => {
        const sw = '<span class="snd-swatch" style="background:' + sndColour(e) + '"></span>';
        const inputs = white
            ? '<input type="number" min="2700" max="10000" step="100" value="' + e.temp + '" onchange="sndPal(' + i + ',\'temp\',this.value)"> K'
            : 'Hue <input type="number" min="0" max="360" value="' + e.hue + '" onchange="sndPal(' + i + ',\'hue\',this.value)"> Sat <input type="number" min="0" max="100" value="' + e.sat + '" onchange="sndPal(' + i + ',\'sat\',this.value)">';
        return '<div class="snd-row">' + (i + 1) + ' ' + sw + inputs + (pal.length > 1 ? ' <button class="btn small" onclick="sndPalRemove(' + i + ')" title="Remove this colour">x</button>' : '') + '</div>';
    }).join('');
    document.getElementById('sndParts').innerHTML = (d.parts || []).map((p, i) => {
        const colours = pal.map((e, j) => [j, 'Palette ' + (j + 1)]).concat([['centroid', 'Follows the sound'], ['beat', 'Steps on the beat']]);
        return '<div class="snd-row snd-part">'
            + '<input list="sndTargets" value="' + esc(p.target || '') + '" onchange="sndPart(' + i + ',\'target\',this.value)" title="Lights by role (@rim), position (@back.left, @high), number (1;3) or @all, joined with ;">'
            + '<select onchange="sndPart(' + i + ',\'drive\',this.value)">' + SND_DRIVES.map(([v, l]) => '<option value="' + v + '"' + ((p.drive || 'level') === v ? ' selected' : '') + '>' + l + '</option>').join('') + '</select>'
            + '<select onchange="sndPart(' + i + ',\'colour\',this.value)">' + colours.map(([v, l]) => '<option value="' + v + '"' + (String(p.colour === undefined ? 0 : p.colour) === String(v) ? ' selected' : '') + '>' + l + '</option>').join('') + '</select>'
            + '<label title="Step through these lights one at a time on the beat"><input type="checkbox"' + (p.chase ? ' checked' : '') + ' onchange="sndPart(' + i + ',\'chase\',this.checked)"> Chase</label>'
            + '<button class="btn small" onclick="sndPartRemove(' + i + ')" title="Remove these lights">x</button></div>';
    }).join('');
}
function sndColour(e) {
    if (e.temp !== undefined) { const t = Math.max(0, Math.min(1, (e.temp - 2700) / 7300)); return 'rgb(255,' + Math.round(170 + 70 * t) + ',' + Math.round(110 + 145 * t) + ')'; }
    return 'hsl(' + e.hue + ',' + e.sat + '%,' + (100 - e.sat / 2) + '%)';
}
function sndSlider(k, raw) {
    const spec = SND_SLIDERS.find(s => s[0] === k);
    let v = Number(raw);
    document.getElementById('snd_' + k + '_v').textContent = v + spec[4];
    const changes = {};
    changes[k] = spec[5] === 100 ? v / 100 : v;
    if (k === 'floor' && v > (sndDraft.ceiling !== undefined ? sndDraft.ceiling : 75)) { changes.ceiling = v; document.getElementById('snd_ceiling').value = v; document.getElementById('snd_ceiling_v').textContent = v + '%'; }
    if (k === 'ceiling' && v < (sndDraft.floor !== undefined ? sndDraft.floor : 10)) { changes.floor = v; document.getElementById('snd_floor').value = v; document.getElementById('snd_floor_v').textContent = v + '%'; }
    Object.assign(sndDraft, changes);
    sndLive(changes);
}
function sndPal(i, key, v) { sndDraft.palette[i][key] = Number(v); sndRender(); sndLive({palette: sndDraft.palette}); }
function sndPalRemove(i) {
    sndDraft.palette.splice(i, 1);
    (sndDraft.parts || []).forEach(p => { if (typeof p.colour === 'number' && p.colour >= sndDraft.palette.length) p.colour = sndDraft.palette.length - 1; });
    sndRender(); sndLive({palette: sndDraft.palette, parts: sndDraft.parts});
}
function sndPaletteAdd() {
    sndDraft.palette = sndDraft.palette || [];
    sndDraft.palette.push(sndDraft.palette.length && sndDraft.palette[0].temp !== undefined ? {temp: 4000} : {hue: 200, sat: 90});
    sndRender(); sndLive({palette: sndDraft.palette});
}
function sndPaletteKind(kind) {
    sndDraft.palette = kind === 'cct' ? [{temp: 2900}, {temp: 4300}] : [{hue: 265, sat: 85}];
    (sndDraft.parts || []).forEach(p => { if (typeof p.colour === 'number') p.colour = Math.min(p.colour, sndDraft.palette.length - 1); });
    sndRender(); sndLive({palette: sndDraft.palette, parts: sndDraft.parts});
}
function sndPart(i, key, v) {
    const p = sndDraft.parts[i];
    if (key === 'colour') p.colour = /^\d+$/.test(v) ? Number(v) : v; else p[key] = v;
    if (key === 'target') p.target = String(v).trim();
    sndLive({parts: sndDraft.parts});
}
function sndPartAdd() { (sndDraft.parts = sndDraft.parts || []).push({target: '@background', drive: 'level', colour: 0}); sndRender(); sndLive({parts: sndDraft.parts}); }
function sndPartRemove(i) { sndDraft.parts.splice(i, 1); sndRender(); if (sndDraft.parts.length) sndLive({parts: sndDraft.parts}); }
async function sndStart() {
    const d = await sndPost({action: 'start', mode: document.getElementById('sndMode').value, params: sndDraft ? sndEditable() : undefined});
    if (!d.success) document.getElementById('sndStatus').textContent = "Couldn't start: " + errText(d);
    pollStatus();
}
async function sndStop() { await sndPost({action: 'stop'}); pollStatus(); }
async function sndSave() {
    const d = await sndPost({action: 'save', mode: sndDraft, original: sndName, overwrite: true});
    document.getElementById('sndStatus').textContent = d.success ? 'Saved ' + d.mode : 'Not saved: ' + errText(d);
    if (d.success) sndLoadModes(d.mode);
}
async function sndSaveAs() {
    const name = prompt('Save sound mode as', (sndDraft.name || '') + ' copy');
    if (!name || !name.trim()) return;
    const data = Object.assign({}, sndDraft, {name: name.trim()});
    let d = await sndPost({action: 'save', mode: data});
    if (!d.success && errText(d).includes('exists') && confirm('A sound mode named ' + name.trim() + ' exists. Replace it?')) d = await sndPost({action: 'save', mode: data, overwrite: true});
    document.getElementById('sndStatus').textContent = d.success ? 'Saved ' + d.mode : 'Not saved: ' + errText(d);
    if (d.success) sndLoadModes(d.mode);
}
async function sndRevert() { await sndLoad(sndName); if (sndDraft) sndLive(sndEditable()); }
async function sndDelete() {
    if (!sndName || !confirm('Delete the sound mode ' + sndName + '?')) return;
    await sndPost({action: 'delete', name: sndName});
    sndName = '';
    sndLoadModes();
}
async function sndDevices() {
    const sel = document.getElementById('sndDevice');
    const d = await sndPost({action: 'devices'});
    const current = d.device !== undefined ? d.device : ((lastStatus && lastStatus.sound && lastStatus.sound.device) || '');
    const list = d.success ? d.devices : [{id: '', name: 'System output (what the default output plays)'}];
    if (current && !list.some(x => x.id === current)) list.push({id: current, name: '(not connected) ' + current});
    sel.innerHTML = list.map(x => '<option value="' + esc(x.id) + '">' + esc(x.name) + '</option>').join('');
    sel.value = current;
}
async function sndSetDevice(id) { await sndPost({action: 'device', device: id}); }
function renderSoundStatus() {
    const s = lastStatus && lastStatus.sound;
    if (!s) return;
    document.getElementById('sndUnavailable').style.display = s.available ? 'none' : 'block';
    document.getElementById('sndUnavailable').textContent = s.reason || '';
    document.getElementById('sndControls').style.display = s.available ? 'block' : 'none';
    if (!s.available) return;
    if (!sndDraft && !sndEditing) { sndEditing = 1; sndLoadModes().then(() => { sndEditing = 0; }); sndDevices(); }
    const st = document.getElementById('sndStatus');
    let text = s.running ? 'Playing ' + s.mode + (s.deviceName ? ', listening to ' + s.deviceName : ', starting...') : 'Not playing';
    if (s.error) text += ' (device problem, retrying: ' + s.error + ')';
    if (!/^(Saved|Not saved|Couldn't|Not applied)/.test(st.textContent) || s.running !== renderSoundStatus.was) st.textContent = text;
    renderSoundStatus.was = s.running;
    document.getElementById('sndStopBtn').disabled = !s.running;
    if (s.running && sndDraft && s.mode !== sndName && !sndEditing) { document.getElementById('sndMode').value = s.mode; sndLoad(s.mode); }
    const lv = s.levels || {};
    document.getElementById('sndMeters').innerHTML = SND_METERS.map(([k, label]) =>
        '<div class="snd-meter"><span>' + label + '</span><div><div style="width:' + Math.round(100 * (lv[k] || 0)) + '%"></div></div></div>').join('');
    document.getElementById('sndTempo').textContent = lv.bpm ? 'Tempo: ' + Math.round(lv.bpm) + ' BPM' : 'Tempo: -';
}

// INIT
window.addEventListener('load', () => {
    ['stageView', 'tlStageView'].forEach(id => { const el = document.getElementById(id); if (el) el.value = stageView; });
    watchGlobalPrefs();
    refreshAll();
    startAutoRefresh();
    pollStatus();
    setInterval(pollStatus, 500);
});
</script>
<div style="text-align:center;padding:16px 0 8px;font-size:11px;color:var(--muted);">
    NeewerLux {NLVERSION}<br>
    <a href="https://github.com/poizenjam/NeewerLux/" style="color:var(--accent)">github.com/poizenjam/NeewerLux</a><br>
    Based on <a href="https://github.com/taburineagle/NeewerLite-Python/" style="color:var(--accent)">NeewerLite-Python</a> (v0.12d) by Zach Glenwright.
    Originally from <a href="https://github.com/keefo/NeewerLite" style="color:var(--accent)">NeewerLite</a> by Xu Lian
</div>
</body>
</html>"""
