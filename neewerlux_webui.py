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
.stage-detail { color:var(--muted); }
.layer-base { border-color:#5a5a5a; } .layer-show { border-color:#468cff; } .layer-effect { border-color:#ffa028; } .layer-override { border-color:#eb4646; }
.seq-progress { height:8px; background:var(--bg3); border-radius:4px; cursor:pointer; margin:8px 0 4px; }
.seq-progress > div { height:100%; width:0; background:var(--accent); border-radius:4px; }
.form-grid { display:grid; grid-template-columns: 170px 1fr; gap:6px 10px; align-items:center; font-size:13px; }
.form-grid input[type=number] { width:80px; }
.form-grid .hint { grid-column: 2; color:var(--muted); font-size:11px; margin-top:-4px; }
.modal-bg { position:fixed; inset:0; background:rgba(0,0,0,.7); display:none; align-items:center; justify-content:center; z-index:50; }
.modal-bg.open { display:flex; }
.modal { background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:14px; max-width:95vw; max-height:90vh; overflow:auto; }

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
            <div class="stage-grid" id="stageGrid"><div style="color:var(--muted)">Loading...</div></div>
            <div style="color:var(--muted);font-size:11px;margin-top:8px">Approximate colours. Outline: grey = manual/preset, blue = sequence, orange = effect, red = override animation.
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
            </div>
            <div class="btn-row">
                <button class="btn success" onclick="playAnimation()">&#x25B6; Play</button>
                <button class="btn danger" onclick="stopAnimation()">&#x25A0; Stop</button>
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
            <div style="color:var(--muted);font-size:11px;margin-top:8px">Sliders and presets don't interrupt a playing sequence: they become what the lights return to when it ends.</div>
        </div>
    </div>

    <!-- SETTINGS -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="toggleSettings(this)">Settings</div>
        <div class="card-body" id="settingsBody" style="display:none">
            <div class="container" style="padding:0;gap:16px">
                <div>
                    <h3 style="margin-top:0;color:var(--accent)">Light Preferences</h3>
                    <div class="form-grid">
                        <label>Light</label><select id="lpLight" onchange="fillLightPrefs()"></select>
                        <label>Custom name</label><input type="text" id="lpName" maxlength="64" placeholder="(model name)">
                        <label>Preferred ID</label><input type="number" id="lpID" min="0" max="99"><div class="hint">0 = automatic. Used in URLs and batch commands.</div>
                        <label>Colour temperature range</label><span><input type="number" id="lpTempMin" min="1000" max="5600" step="100"> to <input type="number" id="lpTempMax" min="1000" max="10000" step="100"> K <button class="btn" style="padding:2px 8px;font-size:11px" onclick="resetTempRange()">Default</button></span>
                        <label>CCT-only light</label><label style="text-transform:none"><input type="checkbox" id="lpCCTOnly"> Only accepts CCT (older lights)</label>
                        <label>Role</label><select id="lpRole"></select>
                        <label>Side</label><select id="lpSide"></select>
                        <label>Sweep order</label><input type="number" id="lpOrder" min="0" max="99"><div class="hint">0 = automatic (by side).</div>
                        <label>Eye line</label><label style="text-transform:none"><input type="checkbox" id="lpEyeline"> At eye level (@eyeline)</label>
                        <label>Max brightness</label><input type="number" id="lpMaxBri" min="-1" max="100"><div class="hint">-1 = use the global limit.</div>
                        <label>Min brightness</label><input type="number" id="lpMinBri" min="-1" max="100"><div class="hint">-1 = use the global limit.</div>
                        <label>Locked</label><label style="text-transform:none"><input type="checkbox" id="lpLocked"> Ignore sequences and effects</label>
                    </div>
                    <div class="btn-row" style="margin-top:10px"><button class="btn primary" onclick="saveLightPrefs()">Save Light Preferences</button></div>
                </div>
                <div>
                    <h3 style="margin-top:0;color:var(--accent)">Global Preferences</h3>
                    <div class="form-grid">
                        <label>Max brightness</label><input type="number" id="gpEnvMax" min="1" max="100"><div class="hint">Presets, URLs, animations and sequences. Sliders are exempt.</div>
                        <label>Min brightness</label><input type="number" id="gpEnvMin" min="0" max="100">
                        <label>Sequence frame rate</label><input type="number" id="gpSeqFps" min="1" max="30"><div class="hint">Updates per second for sequences without their own.</div>
                        <label>Effect time limit (s)</label><input type="number" id="gpEffectMax" min="1" max="600"><div class="hint">Forever-looping effects stop after this.</div>
                        <label>Global CCT range</label><span><input type="number" id="gpCCTMin" min="2700" max="8500" step="100"> to <input type="number" id="gpCCTMax" min="2700" max="8500" step="100"> K</span>
                        <label>Colour on CCT-only lights</label><select id="gpFallback"><option value="convert">Convert to white</option><option value="ignore">Ignore</option></select>
                        <label>Simulated lights</label><select id="gpSim"></select><div class="hint">Takes effect at the next start.</div>
                        <label>Simulated CCT-only light</label><label style="text-transform:none"><input type="checkbox" id="gpSimCCT"> Add one (takes effect at the next start)</label>
                    </div>
                    <div class="btn-row" style="margin-top:10px"><button class="btn primary" onclick="saveGlobalPrefs()">Save Global Preferences</button></div>
                    <div style="color:var(--muted);font-size:11px;margin-top:8px">Network access, keyboard shortcuts and startup options are only changed in the desktop app.</div>
                </div>
            </div>
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
            <p style="color:var(--muted)">Presets and animations are managed in the desktop
            app. Its Info tab documents them in full.</p>
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
        <canvas id="renderCanvas"></canvas>
        <div id="renderCues" style="font-size:11px;color:var(--muted);max-height:160px;overflow:auto;margin-top:6px;font-family:monospace"></div>
    </div>
</div>

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

    fetch('/NeewerLux/animate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action:'play', name:selectedAnim, speed:parseFloat(speed), rate:parseInt(rate), brightness:parseInt(bri), loop:loop, maxLoops:maxLoops, revert:revert})
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
    loadSequences();
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
    } catch(e) {
        document.getElementById('lightTableBody').innerHTML =
            '<tr><td colspan="9" style="text-align:center;padding:20px;color:var(--muted)">Could not load light data. <a href="#" onclick="refreshAll();return false;">Retry</a></td></tr>';
        logMsg('Load error: ' + e.message, 'err');
    }
}

function renderLightsJSON(data) {
    const lights = data.lights || [];
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
    const grid = document.getElementById('presetGrid');
    if (presets.length === 0) {
        grid.innerHTML = '<div style="color:#888;grid-column:1/-1;text-align:center;padding:10px;">No presets configured</div>';
        return;
    }
    let html = '';
    presets.forEach(p => {
        const cls = p.custom ? 'preset-btn custom-global' : (p.name ? 'preset-btn custom-snap' : 'preset-btn');
        const label = p.name || (p.custom ? 'CUSTOM' : 'PRESET');
        html += '<button class="' + cls + '" onclick="usePreset(' + p.index + ')" oncontextmenu="presetMenu(event,' + p.index + ')" title="Click: recall | Right-click: options">'
            + '<span class="preset-num">' + p.index + '</span>'
            + '<span>' + label + '</span></button>';
    });
    // Add "+" button
    html += '<button class="preset-btn" onclick="addPreset()" title="Add a new preset" style="opacity:0.6"><span class="preset-num">+</span><span>NEW</span></button>';
    html += '<div style="grid-column:1/-1;font-size:11px;color:var(--muted);text-align:center;padding:4px 0;">Click to recall &bull; Right-click for options</div>';
    grid.innerHTML = html;
}

function presetMenu(e, idx) {
    e.preventDefault();
    const action = prompt('Preset ' + idx + ':\\n1 = Save snapshot here\\n2 = Delete this preset\\n\\nEnter 1 or 2:', '1');
    if (action === '1') {
        if (confirm('Save a snapshot of all lights to Preset ' + idx + '?')) {
            apiCall(BASE + 'save_preset=' + idx + '&nopage', 'Saved preset ' + idx);
            setTimeout(refreshAll, 500);
        }
    } else if (action === '2') {
        if (confirm('Delete Preset ' + idx + '? Remaining presets will be renumbered.')) {
            apiCall(BASE + 'delete_preset=' + idx + '&nopage', 'Deleted preset ' + idx);
            setTimeout(refreshAll, 500);
        }
    }
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
    } catch(e) { return; }
    renderStage();
    renderSeqStatus();
    renderAnimStatus();
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

function renderStage() {
    if (!stageVisible || !lastStatus) return;
    const lights = lastStatus.lights || [];
    const grid = document.getElementById('stageGrid');
    if (!lights.length) { grid.innerHTML = '<div style="color:var(--muted)">No lights yet</div>'; return; }
    let html = '';
    lights.forEach(l => {
        let fill = l.color || '#373737';
        let detail = cap(l.role);
        if (l.mode) detail += '  ' + l.mode + (l.mode === 'OFF' || l.bri == null ? '' : ' ' + l.bri + '%');
        html += '<div class="stage-tile" title="' + esc(l.name) + '">'
            + '<div class="stage-box layer-' + esc(l.layer || 'base') + '" style="background:' + fill + ';' + (l.linked ? '' : 'filter:brightness(.4);') + '">'
            + (l.simulated ? '<span class="sim">SIM</span>' : '')
            + (l.color ? '' : '<span class="unknown">?</span>') + '</div>'
            + '<div class="stage-name">' + esc(l.name) + '</div>'
            + '<div class="stage-detail">' + esc(detail) + '</div>'
            + '<div class="stage-detail">' + esc(l.linked ? (l.layer || 'base') : 'not linked') + '</div></div>';
    });
    if (grid._last !== html) { grid.innerHTML = html; grid._last = html; }
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
        item.innerHTML = '<strong>' + esc(s.name) + '</strong> <span style="float:right;color:var(--muted);font-size:11px">' + fmtMs(s.duration_ms) + ', ' + s.cues + ' cues</span>'
            + (s.description ? '<br><span style="color:var(--muted);font-size:11px">' + esc(s.description) + '</span>' : '');
        item.onclick = () => {
            div.querySelectorAll('.anim-item').forEach(i => i.classList.remove('selected'));
            item.classList.add('selected');
            selectedSeq = s.name;
        };
        div.appendChild(item);
    });
}
async function loadSequences() {
    try { const d = await seqPost({action:'list'}); if (d.success) renderSeqList(d.sequences); } catch(e) {}
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
    fillSelect('lpRole', d.roles);
    fillSelect('lpSide', d.sides);
    fillSelect('gpSim', d.simulatedRigs.map((_, i) => i), d.simulatedRigs.map((r, i) => i ? i + ' (' + r + ')' : r));
    fillSelect('lpLight', d.lights.map(l => l.index), d.lights.map(l => l.id + ' - ' + (l.customName || l.model) + (l.simulated ? ' (simulated)' : '')));
    fillLightPrefs();
    const g = d.global;
    document.getElementById('gpEnvMax').value = g.envMaxBri;
    document.getElementById('gpEnvMin').value = g.envMinBri;
    document.getElementById('gpSeqFps').value = g.seqFrameRate;
    document.getElementById('gpEffectMax').value = g.effectMaxSeconds;
    document.getElementById('gpCCTMin').value = g.globalCCTMin;
    document.getElementById('gpCCTMax').value = g.globalCCTMax;
    document.getElementById('gpFallback').value = g.cctFallbackMode;
    document.getElementById('gpSim').value = g.simulatedLights;
    document.getElementById('gpSimCCT').checked = !!g.simulatedCCTOnly;
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
    document.getElementById('lpSide').value = l.side;
    document.getElementById('lpOrder').value = l.order;
    document.getElementById('lpEyeline').checked = !!l.eyeline;
    document.getElementById('lpMaxBri').value = l.maxBri;
    document.getElementById('lpMinBri').value = l.minBri;
    document.getElementById('lpLocked').checked = !!l.locked;
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
        role: document.getElementById('lpRole').value, side: document.getElementById('lpSide').value, order: num('lpOrder'),
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
        simulatedCCTOnly: document.getElementById('gpSimCCT').checked};
    try {
        const d = await settingsPost({action:'set_global', settings:settings});
        if (!d.success) { logMsg('Global preferences not saved: ' + (d.errors || []).join('; '), 'err'); return; }
        applySettings(d);
        logMsg('Saved global preferences' + (d.note ? ' (' + d.note + ')' : ''), 'ok');
    } catch(e) { logMsg('Save failed: ' + e.message, 'err'); }
}

// INIT
window.addEventListener('load', () => {
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
