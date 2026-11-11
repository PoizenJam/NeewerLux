"""Checks animation timelines against a replay of the v1.3.0 engine loop.

The replay is the old animationEngineThread with time.sleep replaced by a virtual
clock and zero send overhead, so it records the schedule the old engine aimed for.
AnimationTimeline(legacy=True) must match it exactly, timing included. The timeline
NeewerLux plays animations with since 1.3.3 (stepped=True: exact durations instead of
v1.3.0's 50 ms rounding) is checked for exact durations, every keyframe shown, and fades
moving in whole rate steps.
Run: python tests/test_timeline.py
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import neewerlux_show as show  # noqa: E402


def interpolateHSI(start, end, t):
    h1, s1, b1 = start
    h2, s2, b2 = end
    diff = (h2 - h1 + 540) % 360 - 180
    return (int((h1 + diff * t) % 360), int(s1 + (s2 - s1) * t), int(b1 + (b2 - b1) * t))


def interpolateCCT(start, end, t):
    t1, b1 = start
    t2, b2 = end
    return (int(t1 + (t2 - t1) * t), int(b1 + (b2 - b1) * t))


def legacyReplay(animation, speedMultiplier=1.0, fps=5, briScale=1.0, loopOverride=None, maxLoops=0, untilMs=20000):
    """v1.3.0 animationEngineThread, verbatim apart from the clock. Returns [(t, [cmds])]."""
    now = [0.0]
    sends = []

    def send(cmds):
        sends.append((now[0], cmds))

    def sleep(sec):
        now[0] += sec * 1000.0

    shouldLoop = loopOverride if loopOverride is not None else animation.get("loop", False)
    keyframes = animation.get("keyframes", [])
    stepInterval = max(33, int(1000 / max(1, fps)))
    completedLoops = 0
    frameIndex = 0
    totalFrames = len(keyframes)
    prevFrameIndex = -1
    while now[0] < untilMs:
        keyframe = keyframes[frameIndex]
        hold_ms = keyframe.get("hold_ms", 200)
        fade_ms = keyframe.get("fade_ms", 0)
        lights = keyframe.get("lights", {})
        hold_ms = max(50, int(hold_ms / speedMultiplier))
        fade_ms = max(0, int(fade_ms / speedMultiplier))
        if frameIndex == 0 and prevFrameIndex == totalFrames - 1 and fade_ms == 0 and shouldLoop:
            lastFade = keyframes[-1].get("fade_ms", 0)
            if lastFade > 0:
                fade_ms = max(0, int(lastFade / speedMultiplier))
        if fade_ms > 0 and prevFrameIndex >= 0:
            prevLights = keyframes[prevFrameIndex].get("lights", {})
            steps = max(1, fade_ms // stepInterval)
            for step in range(steps):
                t = (step + 1) / steps
                frameCommands = []
                for lightKey, targetParams in lights.items():
                    mode = targetParams.get("mode", "HSI").upper()
                    prevParams = prevLights.get(lightKey, targetParams)
                    prevMode = prevParams.get("mode", mode).upper()
                    if mode == prevMode and mode == "HSI":
                        h, s, b = interpolateHSI(
                            (prevParams.get("hue", 0), prevParams.get("sat", 100), prevParams.get("bri", 100)),
                            (targetParams.get("hue", 0), targetParams.get("sat", 100), targetParams.get("bri", 100)), t)
                        frameCommands.append({"light": lightKey, "mode": "HSI", "hue": h, "sat": s, "bri": max(0, min(100, int(b * briScale)))})
                    elif mode == prevMode and mode == "CCT":
                        temp, bri = interpolateCCT(
                            (prevParams.get("temp", 56), prevParams.get("bri", 100)),
                            (targetParams.get("temp", 56), targetParams.get("bri", 100)), t)
                        frameCommands.append({"light": lightKey, "mode": "CCT", "temp": temp, "bri": max(0, min(100, int(bri * briScale)))})
                    else:
                        if step == steps - 1:
                            scaledTarget = dict(targetParams)
                            if "bri" in scaledTarget:
                                scaledTarget["bri"] = max(0, min(100, int(scaledTarget["bri"] * briScale)))
                            frameCommands.append({"light": lightKey, **scaledTarget})
                if frameCommands:
                    send(frameCommands)
                sleep(stepInterval / 1000.0)
        else:
            frameCommands = []
            for lightKey, params in lights.items():
                scaledParams = dict(params)
                if "bri" in scaledParams:
                    scaledParams["bri"] = max(0, min(100, int(scaledParams["bri"] * briScale)))
                frameCommands.append({"light": lightKey, **scaledParams})
            if frameCommands:
                send(frameCommands)
        holdSteps = max(1, hold_ms // 50)
        for _ in range(holdSteps):
            sleep(0.05)
        prevFrameIndex = frameIndex
        frameIndex += 1
        if frameIndex >= totalFrames:
            completedLoops += 1
            if shouldLoop:
                if maxLoops > 0 and completedLoops >= maxLoops:
                    break
                frameIndex = 0
            else:
                break
    return sends, now[0]


def check(anim, **kw):
    sends, endT = legacyReplay(anim, **kw)
    tl = show.AnimationTimeline(anim, speed=kw.get("speedMultiplier", 1.0), fps=kw.get("fps", 5),
                                briScale=kw.get("briScale", 1.0), loop=kw.get("loopOverride"),
                                maxLoops=kw.get("maxLoops", 0), legacy=True)
    problems = []
    for t, cmds in sends:
        state, finished, _ = tl.frameAt(t + 0.001)
        for c in cmds:
            want = {k: v for k, v in c.items() if k != "light"}
            got = state.get(c["light"])
            if got != want:
                problems.append((t, c["light"], want, got))
                break
    # Between two sends nothing may change early
    for (t1, _), (t2, _) in zip(sends, sends[1:]):
        if t2 - t1 > 0.02:
            a, _, _ = tl.frameAt(t1 + 0.001)
            b, _, _ = tl.frameAt(t2 - 0.01)
            if a != b:
                problems.append(("early change", t1, t2))
                break
    dur = tl.duration
    if dur is not None and abs(dur - endT) > 0.01 and endT < 20000:
        problems.append(("duration", dur, endT))
    return problems


def checkExact(anim, **kw):
    """1.3.3 timing (stepped=True): each keyframe holds and fades exactly as long as the file
    says divided by the speed, every keyframe with a hold shows its own colour during it, and
    a fade moves in floor(fade / rate interval) steps (at least one) with no extra writes."""
    speed = kw.get("speedMultiplier", 1.0)
    fps = kw.get("fps", 5)
    tl = show.AnimationTimeline(anim, speed=speed, fps=fps, briScale=kw.get("briScale", 1.0),
                                loop=kw.get("loopOverride"), maxLoops=kw.get("maxLoops", 0), stepped=True)
    kfs = tl.keyframes
    problems = []
    exact = sum(k.get("hold_ms", 200) + (k.get("fade_ms", 0) if i else 0) for i, k in enumerate(kfs)) / speed
    if abs(tl.d0 - exact) > 0.001:
        problems.append(("first pass length", tl.d0, exact))
    stepMs = max(33, int(1000 / max(1, int(fps))))
    for seg in tl.pass0:
        if seg.holdDur > 2:
            state, _, _ = tl.frameAt(seg.start + seg.fadeDur + seg.holdDur / 2.0)
            for key, params in kfs[seg.kf].get("lights", {}).items():
                if state.get(key) != show._scaled(params, tl.briScale):
                    problems.append(("keyframe not shown", seg.kf, key, state.get(key)))
                    break
        if seg.fadeDur > 0:
            want = max(1, int(seg.fadeDur // stepMs))
            if seg.steps != want:
                problems.append(("fade steps", seg.kf, seg.steps, want))
            seen = []
            t = seg.start
            while t < seg.start + seg.fadeDur:
                state, _, _ = tl.frameAt(t)
                if not seen or seen[-1] != state:
                    seen.append(state)
                t += 1.0
            if len(seen) > seg.steps:
                problems.append(("fade wrote more than its steps", seg.kf, len(seen), seg.steps))
    return problems


def main():
    animDir = os.path.join(os.path.dirname(HERE), "light_prefs", "animations")
    files = sorted(glob.glob(os.path.join(animDir, "*.json")))
    bad = 0
    variants = [dict(), dict(speedMultiplier=1.5, fps=10, briScale=0.8), dict(speedMultiplier=0.5, fps=30),
                dict(loopOverride=True, maxLoops=2), dict(loopOverride=False)]
    badValues = 0
    for f in files:
        anim = json.load(open(f, encoding="utf-8"))
        for kw in variants:
            p = check(anim, **kw)
            if p:
                bad += 1
                print("MISMATCH", anim["name"], kw, p[:2])
            p = checkExact(anim, **kw)
            if p:
                badValues += 1
                print("EXACT TIMING", anim["name"], kw, p[:2])
    print("timeline vs v1.3.0 replay:", len(files), "animations x", len(variants), "variants,", bad, "mismatches (legacy timing),",
          badValues, "with problems (1.3.3 exact timing)")
    return 1 if bad or badValues else 0


if __name__ == "__main__":
    sys.exit(main())
