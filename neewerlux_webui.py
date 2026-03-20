"""Web Dashboard for NeewerLux HTTP Server.

Generates a modern, responsive control panel that replaces the old
plain-HTML landing page. Provides interactive light control, animation
playback, preset recall, and status monitoring.
"""

def getWebDashboardHTML(serverAddr=""):
    """Return the complete HTML for the web dashboard."""
    return WEB_DASHBOARD_HTML.replace("{{SERVER}}", serverAddr)


WEB_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NeewerLux — Control Panel</title>
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
    border-radius: 12px;
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
    border-radius: 4px;
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
    border-radius: 8px;
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
select, input[type="number"] {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 4px;
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
    border-radius: 4px;
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
    border-radius: 4px;
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
    border-radius: 6px;
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
    border-radius: 4px;
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
    border-radius: 4px;
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
    border-radius: 4px;
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
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }
</style>
</head>
<body>

<div class="header">
    <h1><span>Neewer</span>Lux <small style="color:#888;font-size:12px">1.0.0</small></h1>
    <div class="spacer"></div>
    <span class="status-pill" id="connStatus">Loading...</span>
    <button class="refresh-btn" onclick="scanForLights()" title="Scan for new Bluetooth lights">&#x1F50D; Scan</button>
    <button class="refresh-btn" onclick="linkAllLights()" title="Link to all discovered lights">&#x1F517; Link All</button>
    <button class="refresh-btn" onclick="refreshAll()">&#x21BB; Refresh</button>
</div>

<div class="container">
    <!-- LIGHTS -->
    <div class="card full-width">
        <div class="card-header">&#x1F4A1; Lights</div>
        <div class="card-body" style="padding:0">
            <table class="light-table">
                <thead><tr><th>#</th><th>Light Name</th><th>MAC Address</th><th>Status</th><th>Current</th><th>Actions</th></tr></thead>
                <tbody id="lightTableBody"><tr><td colspan="6" style="text-align:center;padding:20px;color:#888">Loading lights...</td></tr></tbody>
            </table>
        </div>
    </div>

    <!-- PRESETS -->
    <div class="card full-width">
        <div class="card-header">&#x1F3B9; Custom Presets</div>
        <div class="card-body">
            <div id="presetGrid" style="display:grid;grid-template-columns:repeat(8,1fr);gap:6px;max-height:140px;overflow-y:auto;">
                <div style="color:#888;grid-column:1/-1;text-align:center;padding:10px;">Loading presets...</div>
            </div>
        </div>
    </div>

    <!-- CONTROL PANEL -->
    <div class="card">
        <div class="card-header">&#x1F3AE; Light Control</div>
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
                <div id="huePreview" style="height:8px;border-radius:4px;margin-bottom:10px;background:hsl(240,100%,50%)"></div>
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
                <button class="btn success" onclick="sendPower('on')">&#x1F7E2; On</button>
                <button class="btn danger" onclick="sendPower('off')">&#x1F534; Off</button>
            </div>
        </div>
    </div>

    <!-- ANIMATIONS -->
    <div class="card">
        <div class="card-header">&#x1F3AC; Animations</div>
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

    <!-- COMMAND LOG (collapsible) -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            &#x1F4CB; Command Log <span style="color:#888;font-size:11px">(click to toggle)</span>
        </div>
        <div class="card-body" style="padding:8px">
            <div class="log" id="commandLog" style="max-height:150px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.6"></div>
        </div>
    </div>

    <!-- INFO (collapsible) -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            &#x2139;&#xFE0F; About NeewerLux <span style="color:#888;font-size:11px">(click to expand)</span>
        </div>
        <div class="card-body" style="display:none">
            <h3 style="color:var(--accent);margin-top:0">NeewerLux 1.0.0</h3>
            <p>Cross-platform Neewer LED light control for streamers and content creators.</p>
            <hr style="border-color:var(--border)">
            <h4>Features</h4>
            <ul style="padding-left:20px;line-height:1.8">
                <li><b>Bluetooth Light Control</b> &mdash; Scan, connect, and control Neewer LED lights via CCT, HSI, and Scene modes</li>
                <li><b>Animation Engine</b> &mdash; Keyframe-based animations with smooth interpolation, parallel BLE writes, and 101 built-in presets</li>
                <li><b>Visual Animation Editor</b> &mdash; Color-coded keyframe table, GradientSlider controls, per-light targeting, copy/paste, and live preview</li>
                <li><b>Preset System</b> &mdash; Unlimited presets with right-click save, left-click recall, middle-click rename, and a visual Preset Editor</li>
                <li><b>Light Aliases &amp; Preferred IDs</b> &mdash; Assign names and IDs for consistent ordering and targeting</li>
                <li><b>Global CCT Range</b> &mdash; Configurable min/max color temperature (2700K&ndash;8500K) with per-light overrides</li>
                <li><b>CCT Clamping</b> &mdash; Software-side enforcement with convert/clamp or ignore/skip modes</li>
                <li><b>WebUI Dashboard</b> &mdash; This page! Live light table, sliders, preset grid, animation browser, and API reference</li>
                <li><b>HTTP API</b> &mdash; RESTful control via GET/POST for automation and integration</li>
            </ul>
            <h4>Helpful Notes</h4>
            <ul style="padding-left:20px;line-height:1.8">
                <li>Preset and animation files are in <code>light_prefs/</code> alongside the application and can be manually edited</li>
                <li>Animations support targeting by alias name, preferred ID, MAC address, or <code>"*"</code> for all lights</li>
                <li>CCT-only lights automatically participate in HSI animations via color temperature mapping</li>
            </ul>
            <h4>Keyboard Shortcuts (Desktop GUI)</h4>
            <table style="width:100%;font-size:12px;border-collapse:collapse">
                <tr><td style="padding:3px 8px"><b>Left-click</b> preset</td><td>Recall preset</td></tr>
                <tr><td style="padding:3px 8px"><b>Right-click</b> preset</td><td>Context menu (save, rename, move, delete)</td></tr>
                <tr><td style="padding:3px 8px"><b>Middle-click</b> preset</td><td>Quick rename</td></tr>
                <tr><td style="padding:3px 8px"><b>Alt+1/2/3/4</b></td><td>Switch to CCT / HSI / Scene / Light Prefs tab</td></tr>
            </table>
            <hr style="border-color:var(--border)">
            <div id="updateCheckArea">
                <button class="btn" onclick="checkForUpdates()">Check for Updates</button>
                <span id="updateResult" style="margin-left:10px;font-size:12px;"></span>
            </div>
            <hr style="border-color:var(--border)">
            <p style="color:var(--muted);font-size:0.9em;">
                <b>Repository:</b> <a href="https://github.com/poizenjam/NeewerLux/" style="color:var(--accent)">github.com/poizenjam/NeewerLux</a><br>
                <b>Releases:</b> <a href="https://github.com/poizenjam/NeewerLux/releases" style="color:var(--accent)">github.com/poizenjam/NeewerLux/releases</a><br><br>
                Based on <a href="https://github.com/taburineagle/NeewerLite-Python/" style="color:var(--accent)">NeewerLite-Python</a> (v0.12d) by Zach Glenwright &mdash;
                Originally from <a href="https://github.com/keefo/NeewerLite" style="color:var(--accent)">NeewerLite</a> by Xu Lian
            </p>
        </div>
    </div>

    <!-- API REFERENCE (collapsible) -->
    <div class="card full-width">
        <div class="card-header" style="cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            &#x1F4D6; API Reference <span style="color:#888;font-size:11px">(click to expand)</span>
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
            </div>
            <div class="api-section">
                <h3>Animations</h3>
                <div class="api-desc">Play by name (GET)</div>
                <div class="api-code">GET /NeewerLux/doAction?animate=Concert%20Sweep</div>
                <div class="api-desc">Play/stop/list (POST JSON)</div>
                <div class="api-code">POST /NeewerLux/animate {"action":"play","name":"Concert Sweep","loop":true}</div>
                <div class="api-code">POST /NeewerLux/animate {"action":"stop"}</div>
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
    apiCall(`${BASE}light=${light}&mode=CCT&temp=${temp * 100}&bri=${bri}&nopage`, `CCT → light=${light} temp=${temp*100}K bri=${bri}%`);
}
function sendHSI() {
    const light = document.getElementById('targetLight').value;
    const hue = document.getElementById('hsiHue').value;
    const sat = document.getElementById('hsiSat').value;
    const bri = document.getElementById('hsiBri').value;
    apiCall(`${BASE}light=${light}&mode=HSI&hue=${hue}&sat=${sat}&bri=${bri}&nopage`, `HSI → light=${light} H:${hue} S:${sat} I:${bri}`);
}
function sendScene(num, btn) {
    const light = document.getElementById('targetLight').value;
    const bri = document.getElementById('sceneBri').value;
    if (activeSceneBtn) activeSceneBtn.classList.remove('active');
    btn.classList.add('active');
    activeSceneBtn = btn;
    apiCall(`${BASE}light=${light}&mode=SCENE&scene=${num}&bri=${bri}&nopage`, `Scene ${num} → light=${light} bri=${bri}%`);
}
function sendPower(state) {
    const light = document.getElementById('targetLight').value;
    if (state === 'on') {
        apiCall(`${BASE}batch=${light}:ON&nopage`, `Power ON → light=${light}`);
    } else {
        apiCall(`${BASE}batch=${light}:OFF&nopage`, `Power OFF → light=${light}`);
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
            '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--muted)">Could not load light data. <a href="#" onclick="refreshAll();return false;">Retry</a></td></tr>';
        logMsg('Load error: ' + e.message, 'err');
    }
}

function renderLightsJSON(data) {
    const lights = data.lights || [];
    const select = document.getElementById('targetLight');
    select.innerHTML = '<option value="*">All Lights</option>';

    if (lights.length === 0) {
        document.getElementById('lightTableBody').innerHTML =
            '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--muted)">No lights discovered. <a href="#" onclick="scanForLights();return false;">Click to Scan</a></td></tr>';
        document.getElementById('connStatus').textContent = '0 lights';
        return;
    }

    let html2 = '', linkedCount = 0;
    lights.forEach(l => {
        if (l.linked) linkedCount++;
        const displayName = l.name || l.model || l.mac;
        select.innerHTML += `<option value="${l.id}">${l.id} - ${displayName}</option>`;
        html2 += `<tr>
            <td class="light-id">${l.id}</td>
            <td>${displayName}${l.model && l.name !== l.model ? ' <span style="color:var(--muted);font-size:11px">(' + l.model + ')</span>' : ''}</td>
            <td style="font-family:monospace;font-size:11px">${l.mac}</td>
            <td class="${l.linked ? 'linked' : 'not-linked'}">${l.linked ? '● LINKED' : '○ Not linked'}</td>
            <td style="font-size:11px">${l.status}</td>
            <td>${l.linked
                ? '<button class="btn" style="padding:3px 8px;font-size:11px" onclick="apiCall(\''+BASE+'light='+l.id+'&mode=CCT&temp=5600&bri=100&nopage\',\'Send → light '+l.id+'\')">Send</button>'
                : '<button class="btn success" style="padding:3px 8px;font-size:11px" onclick="apiCall(\''+BASE+'link='+l.id+'&nopage\',\'Link → light '+l.id+'\');setTimeout(refreshAll,3000)">Link</button>'
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
        const local = '1.0.0';
        if (tag && tag !== local) {
            const rv = tag.split('.').map(Number);
            const lv = local.split('.').map(Number);
            const newer = rv[0] > lv[0] || (rv[0] === lv[0] && rv[1] > lv[1]) || (rv[0] === lv[0] && rv[1] === lv[1] && rv[2] > lv[2]);
            if (newer) {
                el.innerHTML = '<span style="color:var(--green)"><b>Update available: v' + tag + '</b></span> &mdash; <a href="' + url + '" target="_blank" style="color:var(--accent)">Download</a>';
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

// INIT
window.addEventListener('load', () => {
    refreshAll();
    startAutoRefresh();
});
</script>
<div style="text-align:center;padding:16px 0 8px;font-size:11px;color:var(--muted);">
    NeewerLux 1.0.0 &mdash;
    <a href="https://github.com/poizenjam/NeewerLux/" style="color:var(--accent)">github.com/poizenjam/NeewerLux</a><br>
    Based on <a href="https://github.com/taburineagle/NeewerLite-Python/" style="color:var(--accent)">NeewerLite-Python</a> (v0.12d) by Zach Glenwright &mdash;
    Originally from <a href="https://github.com/keefo/NeewerLite" style="color:var(--accent)">NeewerLite</a> by Xu Lian
</div>
</body>
</html>"""
