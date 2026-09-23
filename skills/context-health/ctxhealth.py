#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ctxhealth.py - context health for AI coding agents (cross-agent harness).

Measures how much of the model's context window the current session occupies,
compares it with research-derived per-model degradation bands (models.json next
to this file), and warns through whatever the host agent supports: hooks
(Claude Code, Copilot CLI, VS Code agent hooks, Codex CLI, Gemini CLI, Cursor),
a Claude Code status line, or a plain terminal report.

Zero dependencies. Python 3.8+. `hook` and `statusline` are fail-silent: they
never raise, never block the agent, and print nothing on error
(set CTXHEALTH_DEBUG=1 to log errors to ~/.ctxhealth/debug.log).

  python ctxhealth.py status [--agent auto|claude|copilot|codex|gemini|cursor|vscode] [--file PATH] [--model ID] [--json]
  python ctxhealth.py hook --agent AGENT           stdin: the agent's hook JSON
  python ctxhealth.py statusline                   stdin: Claude Code statusLine JSON
  python ctxhealth.py install --agent all|AGENT [--dry-run] [--no-statusline] [--replace-legacy] [--copy]
  python ctxhealth.py uninstall --agent all|AGENT
  python ctxhealth.py doctor
  python ctxhealth.py models [--model ID]
  python ctxhealth.py config [get KEY | set KEY VALUE]
  python ctxhealth.py sniff FILE
  python ctxhealth.py fresh | checked --m M [--note TEXT]
  python ctxhealth.py pack [--out DIR]
  python ctxhealth.py version
"""
import argparse
import datetime as _dt
import fnmatch
import glob
import json
import os
import re
import shutil
import sys
import time
import zipfile

VERSION = "1.3.1"
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = HERE
MODELS_PATH = os.path.join(HERE, "models.json")
EVERGREEN_PATH = os.path.join(HERE, "evergreen.json")
HOME = os.path.expanduser("~")
NL = chr(10)
CFG_DIR = os.environ.get("CTXHEALTH_HOME") or os.path.join(HOME, ".ctxhealth")
CFG_PATH = os.path.join(CFG_DIR, "config.json")
STATE_DIR = os.path.join(CFG_DIR, "state")
DEBUG = os.environ.get("CTXHEALTH_DEBUG") == "1"
BANDS = ["green", "watch", "caution", "warning", "critical"]
BASELINE_BANDS = ["ok", "notable", "high", "excessive"]
PLATFORMS = ["claude-cli", "claude-vscode", "cowork", "copilot-cli", "copilot-vscode", "codex", "gemini", "cursor"]
AGENTS = ["claude", "copilot", "codex", "gemini", "cursor", "vscode"]
TAIL_BYTES = 2 * 1024 * 1024
HEAD_BYTES = 64 * 1024
HEAD_SCAN_CAP = 32 * 1024 * 1024  # baseline scan stops here if no assistant turn was found
MARK = "ctxhealth.py"  # identifies our entries in agent config files
LEGACY_MARK = "context-health.ps1"
COOLDOWN_MIN = {1: 20, 2: 10, 3: 5, 4: 2}  # minutes between repeats per band
# Extensions Gmail (and most corporate mail) reject even inside a zip. pack refuses them.
MAIL_BLOCKED = {".ade", ".adp", ".apk", ".appx", ".bat", ".cab", ".chm", ".cmd", ".com", ".cpl", ".dll",
                ".dmg", ".exe", ".hta", ".ins", ".isp", ".iso", ".jar", ".js", ".jse", ".lib", ".lnk",
                ".mde", ".msc", ".msi", ".msix", ".msp", ".mst", ".nsh", ".pif", ".ps1", ".scr", ".sct",
                ".shb", ".sys", ".vb", ".vbe", ".vbs", ".vxd", ".wsc", ".wsf", ".wsh"}


# ----------------------------------------------------------------------------- utilities

def dbg(msg):
    if not DEBUG:
        return
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(os.path.join(CFG_DIR, "debug.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (_dt.datetime.now().isoformat(timespec="seconds"), msg))
    except Exception:
        pass


def winpath(path):
    """Long-path-safe form on Windows (transcript paths exceed 260 chars)."""
    if os.name == "nt" and len(path) > 240 and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(path)
    return path


def read_json(path, default=None):
    try:
        with open(winpath(path), "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


class ConfigError(Exception):
    pass


def load_config_file(path):
    """(obj, existed). Raises ConfigError when the file exists but is not strict JSON
    (Gemini allows // comments, people hand-edit): never overwrite what we cannot parse."""
    if not os.path.exists(path):
        return {}, False
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            obj = json.load(f)
    except Exception as e:
        raise ConfigError("%s is not strict JSON (%s); edit it by hand, nothing was written" % (path, e))
    if not isinstance(obj, dict):
        raise ConfigError("%s does not hold a JSON object; nothing was written" % path)
    return obj, True


def write_config_file(path, obj):
    """Write an agent config with a one-off backup of the previous version."""
    if os.path.exists(path):
        try:
            shutil.copyfile(path, path + ".bak-ctxhealth")
        except Exception as e:
            dbg("backup failed: %r" % e)
    write_json(path, obj)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def tail_text(path, nbytes=TAIL_BYTES):
    p = winpath(path)
    size = os.path.getsize(p)
    with open(p, "rb") as f:
        if size > nbytes:
            f.seek(size - nbytes)
        data = f.read()
    return data.decode("utf-8", errors="replace")


def head_text(path, nbytes=HEAD_BYTES):
    with open(winpath(path), "rb") as f:
        return f.read(nbytes).decode("utf-8", errors="replace")


def tail_lines(path, nbytes=TAIL_BYTES):
    lines = tail_text(path, nbytes).splitlines()
    if len(lines) > 1 and os.path.getsize(winpath(path)) > nbytes:
        lines = lines[1:]  # first line may be cut mid-way
    return lines


def k(n):
    if n is None:
        return "?"
    n = int(n)
    if n < 1000:
        return "%d" % n
    if n >= 1000000:
        v = n / 1000000.0
        return ("%.2f" % v).rstrip("0").rstrip(".") + "M"
    return "%dK" % round(n / 1000.0)


def today():
    return _dt.date.today().isoformat()


def load_models():
    m = read_json(MODELS_PATH)
    if not m:
        raise RuntimeError("models.json missing or unreadable at %s" % MODELS_PATH)
    return m


def load_cfg():
    cfg = read_json(CFG_PATH, {}) or {}
    cfg.setdefault("profile", "balanced")
    cfg.setdefault("min_band", "watch")
    cfg.setdefault("windows", {})
    cfg.setdefault("cooldown_scale", 1.0)
    cfg.setdefault("baseline", {})
    return cfg


def python_cmd():
    """Command prefix that runs this script from any shell the host agent may use
    (Git Bash, PowerShell, cmd, sh). Avoids quoting the executable: a quoted first
    token breaks PowerShell, so prefer an unquoted path with no spaces."""
    script = os.path.abspath(__file__).replace("\\", "/")
    if os.name == "nt":
        py = shutil.which("py")
        if py and " " not in py:
            return "%s -3 \"%s\"" % (py.replace("\\", "/").lower(), script)
        exe = sys.executable.replace("\\", "/")
        if " " not in exe:
            return "%s \"%s\"" % (exe, script)
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(512)
            if ctypes.windll.kernel32.GetShortPathNameW(sys.executable, buf, 512):
                short = buf.value.replace("\\", "/")
                if " " not in short:
                    return "%s \"%s\"" % (short, script)
        except Exception:
            pass
        return "python \"%s\"" % script  # relies on PATH; noted by doctor
    exe = sys.executable
    if " " in exe:
        exe = "python3"
    return "%s \"%s\"" % (exe, script)


# ----------------------------------------------------------------------------- model lookup

def norm_model(mid):
    s = (mid or "").strip().lower().replace("_", "-")
    for _ in range(2):
        s = re.sub(r"^(anthropic|openai|google|xai|us|eu|apac|global|models|publishers/[a-z]+/models)[./]", "", s)
    one_m = "[1m]" in s
    s = s.replace("[1m]", "")
    s = re.sub(r"-v\d+(:\d+)?$", "", s)
    s = re.sub(r"@\d{8}$", "", s)
    s = re.sub(r"-20\d{6}$", "", s)
    return s, one_m


def find_family(models, mid):
    s, one_m = norm_model(mid)
    if s:
        for fam in models.get("families", []):
            for pat in fam.get("match", []):
                if fnmatch.fnmatchcase(s, pat):
                    return fam, s, one_m
    unk = dict(models.get("unknown_model", {}))
    unk.setdefault("id", "unknown")
    unk.setdefault("label", "unknown model")
    unk.setdefault("window", 200000)
    unk.setdefault("class", "200k")
    unk["unknown"] = True
    return unk, s, one_m


def short_label(mid):
    s, _ = norm_model(mid)
    return s.replace("claude-", "") if s else "unknown-model"


def harness_for(agent, path=None):
    if agent == "claude" and path and ("local-agent-mode-sessions" in path or "/mnt/.claude/" in path.replace("\\", "/")):
        return "cowork"
    return agent or "claude"


def harness_window(models, cfg, harness, fam, one_m=False):
    """Effective window imposed by the harness (None means native)."""
    user = (cfg.get("windows") or {}).get(harness)
    if user:
        try:
            if int(user) > 0:
                return int(user), "config"
        except (TypeError, ValueError):
            dbg("ignoring non-numeric windows.%s in config" % harness)
    h = (models.get("harnesses") or {}).get(harness) or {}
    byfam = h.get("by_family") or {}
    if fam.get("id") in byfam:
        return int(byfam[fam["id"]]), "harness"
    if h.get("window"):
        return int(h["window"]), "harness"
    if harness in ("claude", "cowork") and os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT") == "1" and not one_m:
        return min(200000, int(fam["window"])), "env"
    return int(fam["window"]), "native"


def compaction_fraction(models, harness, hw):
    h = (models.get("harnesses") or {}).get(harness) or {}
    if h.get("compact_reserve_tokens") and hw:
        return max(0.5, 1.0 - float(h["compact_reserve_tokens"]) / float(hw))
    if h.get("compact_at"):
        return float(h["compact_at"])
    return None


def evaluate(models, cfg, tokens, model_id, agent, path=None, window_hint=None, one_m_hint=False):
    fam, norm, one_m = find_family(models, model_id)
    one_m = one_m or one_m_hint
    native = int(fam["window"])
    harness = harness_for(agent, path)
    if window_hint:
        hw, hw_src = int(window_hint), "reported"
    else:
        hw, hw_src = harness_window(models, cfg, harness, fam, one_m)
    profile = cfg.get("profile", "balanced")
    if not isinstance((models.get("profiles") or {}).get(profile), dict):
        profile = "balanced"
    fr = models["profiles"][profile]
    fracs = fr.get(fam.get("class"), fr.get("200k"))
    thresholds = [int(round(f * native)) for f in fracs]
    deg = sum(1 for t in thresholds if tokens >= t)
    cf = compaction_fraction(models, harness, hw)
    comp = 0
    frac_h = float(tokens) / float(hw) if hw else 0.0
    if cf is not None:
        if frac_h >= cf - 0.05:
            comp = 2
        elif frac_h >= cf - 0.15:
            comp = 1
    band = max(deg, {0: 0, 1: 2, 2: 3}[comp])
    return {
        "tokens": int(tokens), "model": model_id, "model_label": short_label(model_id) if model_id else fam.get("label"),
        "family": fam.get("id"), "family_label": fam.get("label"), "unknown_model": bool(fam.get("unknown")),
        "native_window": native, "harness": harness, "harness_window": hw, "harness_window_source": hw_src,
        "pct_native": round(100.0 * tokens / native), "pct_harness": round(100.0 * frac_h),
        "profile": profile, "thresholds": thresholds, "degradation_band": deg, "compaction": comp,
        "compaction_fraction": cf, "band": band, "band_name": BANDS[band],
    }


# ----------------------------------------------------------------------------- transcript parsers

def detect_kind(path):
    base = os.path.basename(path).lower()
    try:
        head = head_text(path)
        head += tail_text(path, HEAD_BYTES)  # long sessions may start with lines that carry no markers
    except Exception:
        return "unknown"
    if base.startswith("rollout-") or '"session_meta"' in head or ('"event_msg"' in head and '"payload"' in head):
        return "codex"
    if '"parentUuid"' in head or '"cache_read_input_tokens"' in head or '"isSidechain"' in head:
        return "claude"
    if base == "events.jsonl" or '"session.start"' in head or '"assistant.turn_start"' in head:
        return "copilot"
    return "unknown"


def parse_claude(path):
    for line in reversed(tail_lines(path)):
        if '"usage"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("isSidechain"):
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        u = msg.get("usage") or {}
        tokens = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
        if tokens <= 0:
            continue
        return {"tokens": tokens, "model": msg.get("model"), "estimated": False, "kind": "claude-jsonl"}
    return None


def _payload(line):
    try:
        obj = json.loads(line)
    except Exception:
        return None, None
    return obj, (obj.get("payload") if isinstance(obj.get("payload"), dict) else {})


def parse_codex(path):
    tokens = None
    model = None
    window = None
    for line in reversed(tail_lines(path)):
        if tokens is None and '"token_count"' in line:
            _, p = _payload(line)
            if p and p.get("type") == "token_count":
                info = p.get("info") or {}
                last = info.get("last_token_usage") or info.get("total_token_usage") or {}
                inp = int(last.get("input_tokens") or 0)
                cached = int(last.get("cached_input_tokens") or 0)
                t = inp if inp >= cached else inp + cached  # input_tokens normally includes cached
                if t > 0:
                    tokens = t
                    window = info.get("model_context_window")
        if model is None and ('"turn_context"' in line or '"session_meta"' in line):
            _, p = _payload(line)
            if p and p.get("model"):
                model = p.get("model")
        if tokens is not None and model is not None:
            break
    if model is None:
        for line in head_text(path).splitlines():
            if '"session_meta"' in line or '"turn_context"' in line:
                _, p = _payload(line)
                if p and p.get("model"):
                    model = p["model"]
                    break
    if tokens is None:
        return None
    return {"tokens": tokens, "model": model, "estimated": False, "kind": "codex-jsonl", "window_hint": window}


def parse_copilot(path):
    """Copilot CLI events.jsonl. The usage-bearing event is not a stable public API
    (github/copilot-cli#3551), so look for any per-request usage record and fall back
    to estimating from message text since the last compaction."""
    lines = tail_lines(path)
    model = None
    tokens = None
    chars = 0
    counting = True  # becomes False at the newest compaction: earlier text is no longer in context
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t = obj.get("type") or ""
        d = obj.get("data") if isinstance(obj.get("data"), dict) else {}
        if model is None:
            if t == "session.model_change":
                model = d.get("newModel") or d.get("model") or d.get("to")
            elif t == "session.start":
                model = d.get("model")
        if tokens is None and t != "session.shutdown" and "modelMetrics" not in d:
            u = d.get("usage") if isinstance(d.get("usage"), dict) else d
            if isinstance(u, dict) and ("inputTokens" in u or "input_tokens" in u):
                v = int(u.get("inputTokens") or u.get("input_tokens") or 0)
                v += int(u.get("cacheReadTokens") or u.get("cachedInputTokens") or u.get("cache_read_tokens") or 0)
                v += int(u.get("cacheWriteTokens") or u.get("cache_write_tokens") or 0)
                if v > 0:
                    tokens = v
        if tokens is None and counting:
            if t in ("session.compaction_complete", "session.compaction_start"):
                counting = False
            elif t in ("user.message", "assistant.message", "tool.execution_complete"):
                for key in ("content", "text", "message", "result", "output"):
                    val = d.get(key)
                    if isinstance(val, str):
                        chars += len(val)
        if tokens is not None and model is not None:
            break
    if tokens is None:
        if chars <= 0 and counting:
            return None
        return {"tokens": max(1, chars // 4), "model": model, "estimated": True, "kind": "copilot-events-estimate"}
    return {"tokens": tokens, "model": model, "estimated": False, "kind": "copilot-events"}


def estimate_generic(path):
    try:
        size = os.path.getsize(winpath(path))
    except Exception:
        return None
    if size <= 0:
        return None
    return {"tokens": max(1, size // 5), "model": None, "estimated": True, "kind": "size-estimate"}


def measure_path(path, agent=None):
    kind = detect_kind(path)
    m = None
    try:
        if kind == "claude":
            m = parse_claude(path)
        elif kind == "codex":
            m = parse_codex(path)
        elif kind == "copilot":
            m = parse_copilot(path)
    except Exception as e:
        dbg("parse %s failed: %r" % (path, e))
    if m is None:
        m = estimate_generic(path)
    if m is None:
        return None
    m["path"] = path
    try:
        m["age_s"] = max(0.0, time.time() - os.path.getmtime(winpath(path)))
    except Exception:
        m["age_s"] = None
    return m


# ----------------------------------------------------------------------------- session discovery

def _appdata_roots():
    roots = []
    ad = os.environ.get("APPDATA")
    if ad:
        roots.append(os.path.join(ad, "Claude", "local-agent-mode-sessions"))
    roots.append(os.path.join(HOME, "Library", "Application Support", "Claude", "local-agent-mode-sessions"))
    roots.append(os.path.join(HOME, ".config", "Claude", "local-agent-mode-sessions"))
    return roots


def candidate_globs(agent):
    g = []
    if agent == "claude":
        g.append(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl"))
        g.append(os.path.join(HOME, "mnt", ".claude", "projects", "*", "*.jsonl"))  # Cowork sandbox
        for r in _appdata_roots():
            g.append(os.path.join(r, "*", "*", "*", ".claude", "projects", "*", "*.jsonl"))
    elif agent == "copilot":
        base = os.environ.get("COPILOT_HOME") or os.path.join(HOME, ".copilot")
        g.append(os.path.join(base, "session-state", "*", "events.jsonl"))
    elif agent == "codex":
        base = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
        g.append(os.path.join(base, "sessions", "*", "*", "*", "rollout-*.jsonl"))
    elif agent == "gemini":
        g.append(os.path.join(HOME, ".gemini", "tmp", "*", "chats", "*.json"))
        g.append(os.path.join(HOME, ".gemini", "tmp", "*", "checkpoints", "*.json"))
    elif agent == "cursor":
        g.append(os.path.join(HOME, ".cursor", "projects", "*", "agent-transcripts", "*"))
    return g


def _is_subagent(path):
    p = path.replace("\\", "/")
    return "/subagents/" in p or os.path.basename(p).startswith("agent-")


def newest_session(agent="auto"):
    agents = [a for a in AGENTS if a != "vscode"] if agent in (None, "auto") else [agent]
    best = None
    for a in agents:
        for pat in candidate_globs(a):
            for f in glob.glob(pat):
                if _is_subagent(f) or os.path.isdir(f):
                    continue
                try:
                    mt = os.path.getmtime(f)
                except Exception:
                    continue
                if best is None or mt > best[0]:
                    best = (mt, f, a)
    return (best[1], best[2]) if best else (None, None)


def detected_agents():
    found = []
    if os.path.isdir(os.path.join(HOME, ".claude")):
        found.append("claude")
    if os.path.isdir(os.environ.get("COPILOT_HOME") or os.path.join(HOME, ".copilot")):
        found.append("copilot")
    if os.path.isdir(os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")):
        found.append("codex")
    if os.path.isdir(os.path.join(HOME, ".gemini")):
        found.append("gemini")
    if os.path.isdir(os.path.join(HOME, ".cursor")):
        found.append("cursor")
    return found


# ----------------------------------------------------------------------------- messages

def band_text(models, name):
    return (models.get("band_text") or {}).get(name) or {"label": name.upper(), "effects": "", "advice": ""}


def message_for_model(models, ev, estimated):
    bt = band_text(models, ev["band_name"])
    approx = "roughly " if estimated else "~"
    parts = ["[context-health] %s%s tokens in context (%d%% of the %s %s window)" % (
        approx, k(ev["tokens"]), ev["pct_harness"], k(ev["harness_window"]), ev["harness"])]
    if ev["band"] == 0:
        parts.append("- GREEN for %s." % ev["model_label"])
        return " ".join(parts)
    parts.append("- %s for %s: %s." % (bt["label"], ev["model_label"], bt["effects"]))
    if ev["compaction"] == 2:
        parts.append("Auto-compaction is imminent; it will summarize earlier history.")
    elif ev["compaction"] == 1:
        parts.append("Auto-compaction is approaching.")
    if ev.get("unknown_model"):
        parts.append("(Model id not in models.json; assuming a 200K window.)")
    parts.append("Recommendation: %s." % bt["advice"])
    parts.append("Tell the user in one line with that recommendation, once; do not repeat every turn.")
    return " ".join(parts)


def message_for_user(models, ev, estimated):
    bt = band_text(models, ev["band_name"])
    approx = "est. " if estimated else "~"
    s = "context-health: %s%s tokens (%d%% of %s) %s for %s - %s" % (
        approx, k(ev["tokens"]), ev["pct_harness"], k(ev["harness_window"]), bt["label"], ev["model_label"], bt["advice"])
    return s[0].upper() + s[1:]


# ----------------------------------------------------------------------------- baseline (initial context)
# The first assistant turn's input is the session's startup context: system prompt, tool and MCP
# schemas, project instruction files, memory, skills catalog, plus the user's first prompt (estimated
# and subtracted where the transcript shows it). Measured once per session from the head of the
# transcript, recorded per platform in ~/.ctxhealth/baseline/<platform>.jsonl. The model is only asked
# to look at its own startup context (the inventory doc) every baseline.audit_every sessions, or when
# the size is relevant: over a band or grown against this project's recent median.

def baseline_dir():
    return os.path.join(CFG_DIR, "baseline")


def baseline_cfg(cfg):
    out = {"enabled": True, "audit_every": 10, "min_band": "notable", "jump": 0.25, "warn_days": 7}
    b = cfg.get("baseline") if isinstance(cfg.get("baseline"), dict) else {}
    for key in out:
        if key in b:
            out[key] = b[key]
    return out


def platform_for(agent, path=None, kind=None):
    """One of PLATFORMS. The Claude Code CLI and the VS Code extension share hooks, transcripts and
    settings; the extension sets CLAUDE_CODE_ENTRYPOINT=claude-vscode in the hook's environment."""
    if agent == "copilot":
        return "copilot-cli"
    if agent in ("codex", "gemini", "cursor"):
        return agent
    if kind in ("copilot-events", "copilot-events-estimate"):
        return "copilot-vscode"
    if kind == "codex-jsonl":
        return "codex"
    if harness_for("claude", path) == "cowork":
        return "cowork"
    entry = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
    if agent == "vscode" or entry.startswith("claude-vscode"):
        return "claude-vscode"
    return "claude-cli"


def _iter_head_lines(path, cap=HEAD_SCAN_CAP):
    read = 0
    with open(winpath(path), "rb") as f:
        for raw in f:
            read += len(raw)
            yield raw.decode("utf-8", errors="replace")
            if read >= cap:
                return


def _text_len(content):
    if isinstance(content, str):
        return len(content)
    n = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                n += len(block["text"])
            elif isinstance(block, str):
                n += len(block)
    return n


def first_claude(path):
    prompt_chars = 0
    for line in _iter_head_lines(path):
        if '"role"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("isSidechain"):
            continue
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "user":
            prompt_chars += _text_len(msg.get("content"))
            continue
        if msg.get("role") != "assistant":
            continue
        u = msg.get("usage") or {}
        tokens = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
        if tokens <= 0:
            continue
        return {"tokens": tokens, "prompt_tokens_est": prompt_chars // 4, "model": msg.get("model"), "estimated": False, "kind": "claude-jsonl"}
    return None


def first_codex(path):
    model = None
    for line in _iter_head_lines(path):
        if '"session_meta"' in line or '"turn_context"' in line:
            _, p = _payload(line)
            if p and p.get("model") and model is None:
                model = p["model"]
        if '"token_count"' in line:
            _, p = _payload(line)
            if p and p.get("type") == "token_count":
                info = p.get("info") or {}
                last = info.get("last_token_usage") or info.get("total_token_usage") or {}
                inp = int(last.get("input_tokens") or 0)
                cached = int(last.get("cached_input_tokens") or 0)
                t = inp if inp >= cached else inp + cached
                if t > 0:
                    return {"tokens": t, "prompt_tokens_est": 0, "model": model, "estimated": False, "kind": "codex-jsonl", "window_hint": info.get("model_context_window")}
    return None


def first_copilot(path):
    model = None
    for line in _iter_head_lines(path):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t = obj.get("type") or ""
        d = obj.get("data") if isinstance(obj.get("data"), dict) else {}
        if t == "session.start" and model is None:
            model = d.get("model")
        if t != "session.shutdown" and "modelMetrics" not in d:
            u = d.get("usage") if isinstance(d.get("usage"), dict) else d
            if isinstance(u, dict) and ("inputTokens" in u or "input_tokens" in u):
                v = int(u.get("inputTokens") or u.get("input_tokens") or 0)
                v += int(u.get("cacheReadTokens") or u.get("cachedInputTokens") or u.get("cache_read_tokens") or 0)
                v += int(u.get("cacheWriteTokens") or u.get("cache_write_tokens") or 0)
                if v > 0:
                    return {"tokens": v, "prompt_tokens_est": 0, "model": model, "estimated": False, "kind": "copilot-events"}
    return None


def measure_first(path, agent=None):
    """Input size of the first assistant turn (the startup context plus the first prompt). None when the
    transcript has no assistant turn yet or its format carries no counts (no estimate: a size estimate
    of a fresh file says nothing about the system prompt)."""
    kind = detect_kind(path)
    m = None
    try:
        if kind == "claude":
            m = first_claude(path)
        elif kind == "codex":
            m = first_codex(path)
        elif kind == "copilot":
            m = first_copilot(path)
    except Exception as e:
        dbg("first-turn parse %s failed: %r" % (path, e))
    if not m:
        return None
    m["path"] = path
    m.setdefault("prompt_tokens_est", 0)
    m["startup"] = max(0, int(m["tokens"]) - int(m["prompt_tokens_est"]))
    return m


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def evaluate_baseline(models, cfg, startup, model_id, harness, path=None, window_hint=None, prior=None):
    ev = evaluate(models, cfg, startup, model_id, harness, path, window_hint)
    fam, _, _ = find_family(models, model_id)
    b = models.get("baseline") or {}
    fr = b.get("fractions") or {}
    fracs = fr.get(fam.get("class")) or fr.get("200k") or [0.1, 0.2, 0.3]
    hw = ev["harness_window"]
    thresholds = [int(round(f * hw)) for f in fracs]
    band = sum(1 for t in thresholds if startup >= t)
    bc = baseline_cfg(cfg)
    med = _median(prior) if prior and len(prior) >= 3 else None
    try:
        jump = float(bc.get("jump", 0.25))
    except (TypeError, ValueError):
        jump = 0.25
    grew = bool(med is not None and startup >= med * (1.0 + jump) and startup - med >= 5000)
    floor = ((models.get("harnesses") or {}).get(harness) or {}).get("base_context_tokens")
    return {
        "startup": int(startup), "model": model_id, "model_label": ev["model_label"], "family_label": ev["family_label"],
        "harness": harness, "harness_window": hw, "pct": round(100.0 * startup / hw) if hw else 0,
        "thresholds": thresholds, "band": band, "band_name": BASELINE_BANDS[band], "median": med, "grew": grew,
        "floor": floor, "unknown_model": ev["unknown_model"],
    }


def baseline_band_text(models, name):
    bt = ((models.get("baseline") or {}).get("band_text") or {}).get(name)
    return bt or {"label": name.upper(), "effects": "", "advice": ""}


def _bl_paths(platform):
    d = baseline_dir()
    return os.path.join(d, platform + ".jsonl"), os.path.join(d, platform + ".meta.json"), os.path.join(d, "INVENTORY-" + platform + ".md")


def baseline_history(platform, project=None, limit=None):
    p, _, _ = _bl_paths(platform)
    rows = []
    if os.path.exists(p):
        for line in tail_lines(p, 512 * 1024):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if project is None or r.get("project") == project:
                rows.append(r)
    return rows[-limit:] if limit else rows


def baseline_record(platform, row):
    p, _, _ = _bl_paths(platform)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def baseline_message_for_model(models, bev, m, platform, prior, audit, warn, inv_path, n, every):
    bt = baseline_band_text(models, bev["band_name"])
    head = "[context-health baseline] Startup context on %s: ~%s tokens before the first prompt (%d%% of the %s window; first turn ~%s incl. ~%s of prompt) - %s for %s" % (
        platform, k(bev["startup"]), bev["pct"], k(bev["harness_window"]), k(m["tokens"]), k(m.get("prompt_tokens_est", 0)), bt["label"], bev["model_label"])
    if bt.get("effects"):
        head += ": %s" % bt["effects"]
    parts = [head + "."]
    if bev["grew"]:
        parts.append("That is up from a median of ~%s over the last %d sessions in this project: something new is loading at startup." % (k(int(bev["median"])), len(prior)))
    elif bev["median"] is not None:
        parts.append("Recent median for this project: ~%s." % k(int(bev["median"])))
    if bev.get("floor") and platform == "cowork":
        parts.append("(A fresh Cowork session always carries ~%s of tool and skill catalog.)" % k(bev["floor"]))
    if bev.get("unknown_model"):
        parts.append("(Model id not in models.json; assuming a 200K window.)")
    if bt.get("advice"):
        parts.append("Recommendation: %s." % bt["advice"])
    if audit:
        parts.append("[baseline audit, session %d of every %d] After the user's task: in at most 8 lines list the largest blocks of your initial context with rough token sizes and the total (system prompt sections, tool/MCP schemas with a count, project instruction files and their imports, memory files, the skills catalog), note what changed against the previous entry if the file has one, and append it under the heading '## %s · %s · ~%s' to %s (create the file if missing; append with a shell heredoc, do not read or rewrite the whole file)." % (
            n, every, today(), platform, k(bev["startup"]), inv_path))
        if warn:
            parts.append("Also run the `selection` subcommand and fold its result into the inventory: the visible skill count, its band, and any near-duplicate families - catalog size costs selection accuracy separately from tokens.")
            parts.append("Then tell the user in one line: the startup size, the band, and the single biggest lever. Once this session.")
        else:
            parts.append("Do not mention this to the user unless a block looks wrong; the band is %s." % bt["label"])
    elif warn:
        parts.append("Tell the user in one line with that recommendation, once; do not repeat it this session.")
    return " ".join(parts)


def baseline_message_for_user(models, bev, platform):
    bt = baseline_band_text(models, bev["band_name"])
    grew = " (up from ~%s)" % k(int(bev["median"])) if bev["grew"] else ""
    s = "context-health: startup context ~%s (%d%% of %s) %s%s on %s for %s - %s" % (
        k(bev["startup"]), bev["pct"], k(bev["harness_window"]), bt["label"], grew, platform, bev["model_label"], bt["advice"] or "no action needed")
    return s[0].upper() + s[1:]


def baseline_step(models, cfg, agent, harness, session_id, path, data, kind=None, model=None, window_hint=None):
    """Once per session, after the first assistant turn exists: record the startup size for this platform
    and decide whether the model should hear about it. Returns (model_text, user_text); both None when
    nothing is due. Cost: one head scan of the transcript and two small files."""
    bc = baseline_cfg(cfg)
    if not bc.get("enabled", True) or not path:
        return None, None
    sp = state_path(agent, session_id)
    st = read_json(sp, {}) or {}
    if st.get("baseline_done"):
        return None, None
    m = measure_first(path, agent)
    if not m:
        return None, None  # no assistant turn yet; try on the next prompt
    platform = platform_for(agent, path, kind or m.get("kind"))
    project = str(data.get("cwd") or "")
    hist = baseline_history(platform)

    def done():
        st["baseline_done"] = True
        try:
            write_json(sp, st)
        except Exception as e:
            dbg("state write failed: %r" % e)

    if any(r.get("session") == session_id for r in hist):
        done()
        return None, None
    prior = [int(r["startup"]) for r in hist if r.get("project") == project and isinstance(r.get("startup"), int)][-5:]
    model = model or m.get("model")
    bev = evaluate_baseline(models, cfg, m["startup"], model, harness, path, window_hint or m.get("window_hint"), prior)
    row = {"date": today(), "session": session_id, "project": project, "platform": platform, "model": model,
           "startup": m["startup"], "first_turn": m["tokens"], "prompt_est": m.get("prompt_tokens_est", 0),
           "window": bev["harness_window"], "band": bev["band_name"], "grew": bev["grew"], "estimated": bool(m.get("estimated"))}
    _, mp, inv = _bl_paths(platform)
    meta = read_json(mp, {}) or {}
    n = int(meta.get("sessions", 0)) + 1
    meta["sessions"] = n
    try:
        every = max(1, int(bc.get("audit_every") or 10))
    except (TypeError, ValueError):
        every = 10
    due_audit = n - int(meta.get("last_audit_session", 0)) >= every
    min_band = BASELINE_BANDS.index(bc["min_band"]) if bc.get("min_band") in BASELINE_BANDS else 1
    relevant = bev["band"] >= max(1, min_band) or bev["grew"]
    warned = (meta.get("warned") or {}).get(project) or {}
    warn = False
    if relevant:
        try:
            warn_days = float(bc.get("warn_days", 7))
        except (TypeError, ValueError):
            warn_days = 7.0
        if bev["grew"] or bev["band"] > int(warned.get("band", -1)) or time.time() - float(warned.get("t", 0)) >= warn_days * 86400:
            warn = True
    audit = due_audit or (warn and bev["band"] >= 2)
    if warn:
        meta.setdefault("warned", {})[project] = {"band": bev["band"], "t": time.time(), "startup": m["startup"]}
    if audit:
        meta["last_audit_session"] = n
        meta["last_audit_date"] = today()
    row["warned"] = warn
    row["audited"] = audit
    try:
        baseline_record(platform, row)
        write_json(mp, meta)
    except Exception as e:
        dbg("baseline record failed: %r" % e)
    done()
    if not (warn or audit):
        return None, None
    return (baseline_message_for_model(models, bev, m, platform, prior, audit, warn, inv, n, every),
            baseline_message_for_user(models, bev, platform) if warn else None)


def describe_baseline(models, cfg, m, path, agent, harness, model=None):
    """Lines for `status`: the startup context of this transcript."""
    if not m:
        return ["startup: unknown (no assistant turn yet, or this transcript carries no token counts)"]
    platform = platform_for(agent, path, m.get("kind"))
    bev = evaluate_baseline(models, cfg, m["startup"], model or m.get("model"), harness, path, m.get("window_hint"))
    bt = baseline_band_text(models, bev["band_name"])
    th = bev["thresholds"]
    lines = ["startup: ~%s tokens before the first prompt (%d%% of the %s window; first turn ~%s) - %s%s [platform %s]" % (
        k(bev["startup"]), bev["pct"], k(bev["harness_window"]), k(m["tokens"]), bt["label"], (": " + bt["effects"]) if bt.get("effects") else "", platform)]
    lines.append("startup bands: notable %s | high %s | excessive %s; history: %s" % (k(th[0]), k(th[1]), k(th[2]), _bl_paths(platform)[0]))
    return lines


# ----------------------------------------------------------------------------- selection noise (catalog size)
# A second startup problem, independent of token size: how many skills compete for the model's choice.
# The model picks a skill by matching the prompt against every visible description, so accuracy falls as the
# catalog grows and as entries become near-duplicates of each other (models.json "selection" carries the
# evidence). Counted from disk, because the catalog is not recoverable from a transcript.

SKILL_GLOBS = [
    os.path.join(HOME, ".claude", "skills", "*", "SKILL.md"),
    os.path.join(HOME, ".claude", "plugins", "*", "skills", "*", "SKILL.md"),
    os.path.join(HOME, ".claude", "plugins", "*", "*", "skills", "*", "SKILL.md"),
    os.path.join(HOME, ".agents", "skills", "*", "SKILL.md"),
]


def _skill_desc(path):
    """(name, description) from a SKILL.md front matter, cheaply and defensively."""
    name = os.path.basename(os.path.dirname(path))
    desc = ""
    try:
        head = head_text(path, 8192)
    except Exception:
        return name, desc
    for line in head.splitlines()[:40]:
        s = line.strip().lstrip("﻿")
        if s.startswith("description:"):
            desc = s.split(":", 1)[1].strip().strip("'\"")
        elif s.startswith("name:"):
            name = s.split(":", 1)[1].strip().strip("'\"") or name
    return name, desc


def scan_skills(project=None):
    """Every skill visible to a session here: user root, plugin roots, and this project's .claude/skills."""
    globs = list(SKILL_GLOBS)
    if project:
        globs.append(os.path.join(project, ".claude", "skills", "*", "SKILL.md"))
    seen, out = set(), []
    for g in globs:
        for f in glob.glob(g):
            rp = os.path.realpath(f)
            if rp in seen:
                continue
            seen.add(rp)
            name, desc = _skill_desc(f)
            out.append({"name": name, "desc": desc, "chars": len(name) + len(desc), "path": f})
    out.sort(key=lambda s: s["name"])
    return out


def _clusters(skills, cluster_min):
    """Near-duplicate families by shared name stem - the distractor case the retrieval work flags."""
    groups = {}
    for s in skills:
        stem = re.split(r"[-_]", s["name"])[0].lower()
        groups.setdefault(stem, []).append(s["name"])
    return sorted([(stem, names) for stem, names in groups.items() if len(names) >= cluster_min],
                  key=lambda kv: -len(kv[1]))


def evaluate_selection(models, cfg, project=None, skills=None):
    sel = models.get("selection") or {}
    counts = sel.get("counts") or [25, 40, 60]
    over = int((cfg.get("selection") or {}).get("counts_override") or 0)
    if over:
        counts = [over, int(over * 1.6), int(over * 2.4)]
    skills = scan_skills(project) if skills is None else skills
    n = len(skills)
    band = sum(1 for t in counts if n >= t)
    name = ["ok", "notable", "high", "excessive"][band]
    chars = sum(s["chars"] for s in skills)
    cap = int(sel.get("desc_chars_max") or 1536)
    return {
        "count": n, "band_name": name, "thresholds": counts,
        "catalog_tokens": int(chars / 4), "catalog_chars": chars,
        "over_cap": [s["name"] for s in skills if s["chars"] > cap],
        "clusters": _clusters(skills, int(sel.get("cluster_min") or 3)),
        "listing_budget_fraction": sel.get("listing_budget_fraction"),
    }


def selection_band_text(models, name):
    bt = ((models.get("selection") or {}).get("band_text") or {}).get(name)
    return bt or {"label": name.upper(), "effects": "", "advice": ""}


def describe_selection(models, cfg, ev, budget_tokens=None):
    bt = selection_band_text(models, ev["band_name"])
    th = ev["thresholds"]
    lines = ["selection: %d skills visible, ~%s tokens of catalog - %s%s" % (
        ev["count"], k(ev["catalog_tokens"]), bt["label"], (": " + bt["effects"]) if bt.get("effects") else "")]
    lines.append("selection bands: notable %d | high %d | excessive %d skills" % (th[0], th[1], th[2]))
    if ev["clusters"]:
        lines.append("near-duplicate families (compete for the same prompts): " + "; ".join(
            "%s x%d" % (stem, len(names)) for stem, names in ev["clusters"][:4]))
    if ev["over_cap"]:
        lines.append("descriptions over the %d-char listing cap (truncated in the catalog): %s" % (
            int((models.get("selection") or {}).get("desc_chars_max") or 1536), ", ".join(ev["over_cap"][:5])))
    if budget_tokens and ev["catalog_tokens"] > budget_tokens:
        lines.append("catalog ~%s exceeds Claude Code's listing budget ~%s (skillListingBudgetFraction %.2f): "
                     "least-invoked descriptions are dropped whole and cannot be selected." % (
                         k(ev["catalog_tokens"]), k(int(budget_tokens)), ev["listing_budget_fraction"] or 0.01))
    if bt.get("advice"):
        lines.append("recommendation: " + bt["advice"])
    return lines


def cmd_selection(a):
    models = load_models()
    cfg = load_cfg()
    project = a.project or os.getcwd()
    skills = scan_skills(project)
    ev = evaluate_selection(models, cfg, project, skills)
    if a.json:
        ev["skills"] = [{"name": s["name"], "chars": s["chars"], "path": s["path"]} for s in skills]
        print(json.dumps(ev, indent=2))
        return 0
    print(NL.join(describe_selection(models, cfg, ev)))
    if a.list:
        for s in skills:
            print("  %-42s %5d chars  %s" % (s["name"], s["chars"], s["path"]))
    return 0


def cmd_baseline(a):
    models = load_models()
    cfg = load_cfg()
    if a.file:
        agent = a.agent if a.agent and a.agent != "auto" else {"claude": "claude", "codex": "codex", "copilot": "copilot"}.get(detect_kind(a.file), "claude")
        m = measure_first(a.file, agent)
        if not m:
            print("could not measure the first turn of %s" % a.file)
            return 1
        harness = {"codex-jsonl": "codex", "copilot-events": "copilot"}.get(m.get("kind"), harness_for(agent, a.file))
        if a.json:
            bev = evaluate_baseline(models, cfg, m["startup"], a.model or m.get("model"), harness, a.file, m.get("window_hint"))
            bev.update({"path": a.file, "platform": platform_for(agent, a.file, m.get("kind")), "first_turn": m["tokens"], "prompt_est": m.get("prompt_tokens_est", 0)})
            print(json.dumps(bev, indent=2))
        else:
            print("\n".join(describe_baseline(models, cfg, m, a.file, agent, harness, a.model)))
        return 0
    bc = baseline_cfg(cfg)
    plats = [a.platform] if a.platform else [p for p in PLATFORMS if os.path.exists(_bl_paths(p)[0])]
    if not plats:
        print("no startup baselines recorded yet (%s). The hook records one per session once the first assistant turn exists." % baseline_dir())
        return 0
    out = {}
    for p in plats:
        hp, mp, inv = _bl_paths(p)
        meta = read_json(mp, {}) or {}
        rows = baseline_history(p)
        out[p] = {"sessions": meta.get("sessions", len(rows)), "last_audit_session": meta.get("last_audit_session"), "last_audit_date": meta.get("last_audit_date"),
                  "inventory": inv if os.path.exists(inv) else None, "history": rows[-(a.history or 5):]}
        if a.json:
            continue
        print("%s: %s sessions recorded, audit every %s (last at session %s, %s), inventory %s" % (
            p, meta.get("sessions", len(rows)), bc["audit_every"], meta.get("last_audit_session") or "-", meta.get("last_audit_date") or "never", inv if os.path.exists(inv) else "not written yet"))
        by_proj = {}
        for r in rows:
            by_proj.setdefault(r.get("project") or "", []).append(r)
        for proj, rs in by_proj.items():
            med = _median([int(r["startup"]) for r in rs[-5:] if isinstance(r.get("startup"), int)])
            last = rs[-1]
            print("   %s: latest ~%s %s (%s, %s), median of last %d ~%s" % (
                os.path.basename(proj.rstrip("/\\")) or "(no project)", k(int(last.get("startup", 0))), str(last.get("band", "")).upper(), last.get("date"), short_label(last.get("model") or ""), min(5, len(rs)), k(int(med)) if med is not None else "-"))
        if a.history:
            for r in rows[-a.history:]:
                print("   %s  %-9s ~%-6s first turn ~%-6s prompt ~%-5s %s  %s%s" % (
                    r.get("date"), str(r.get("band", "")).upper(), k(int(r.get("startup", 0))), k(int(r.get("first_turn", 0))), k(int(r.get("prompt_est", 0))), short_label(r.get("model") or ""),
                    os.path.basename(str(r.get("project", "")).rstrip("/\\")), " (grew)" if r.get("grew") else ""))
    if a.json:
        print(json.dumps(out, indent=2))
    return 0


# ----------------------------------------------------------------------------- emission policy

def state_path(agent, session_id):
    sid = re.sub(r"[^A-Za-z0-9._-]", "_", str(session_id or "nosession"))[:80]
    return os.path.join(STATE_DIR, "%s-%s.json" % (agent, sid))


def should_emit(agent, session_id, band, cfg):
    min_band = BANDS.index(cfg.get("min_band", "watch")) if cfg.get("min_band") in BANDS else 1
    now = time.time()
    p = state_path(agent, session_id)
    st = read_json(p, {}) or {}
    emit = False
    if band >= max(1, min_band):
        last_band = int(st.get("band", 0))
        last_t = float(st.get("t", 0))
        try:
            scale = float(cfg.get("cooldown_scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        cooldown = COOLDOWN_MIN.get(band, 10) * 60 * scale
        if band > last_band or now - last_t >= cooldown:  # only escalation bypasses the cooldown
            emit = True
    if emit:
        try:
            st.update({"band": band, "t": now, "n": int(st.get("n", 0)) + 1})
            write_json(p, st)
        except Exception as e:
            dbg("state write failed: %r" % e)
        prune_state()
    elif not st:
        try:
            write_json(p, {"band": band, "t": 0, "n": 0})
        except Exception:
            pass
    return emit


def prune_state(max_age_days=7):
    try:
        cutoff = time.time() - max_age_days * 86400
        for f in glob.glob(os.path.join(STATE_DIR, "*.json")):
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
    except Exception:
        pass


# ----------------------------------------------------------------------------- commands

def read_stdin_json():
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        raw = raw.strip()
        return json.loads(raw) if raw else {}
    except Exception as e:
        dbg("stdin json: %r" % e)
        return {}


def guess_agent(data):
    if "conversation_id" in data or "cursor_version" in data:
        return "cursor"
    if "hook_event_name" in data:
        ev = str(data.get("hook_event_name"))
        if ev in ("BeforeAgent", "AfterAgent", "BeforeTool", "AfterTool", "PreCompress"):
            return "gemini"
        return "claude"
    if "sessionId" in data and "hookEventName" not in data:
        return "copilot"
    return "claude"


def cmd_hook(a):
    try:
        models = load_models()
        cfg = load_cfg()
        data = read_stdin_json()
        agent = a.agent or guess_agent(data)
        event = data.get("hook_event_name") or data.get("hookEventName") or data.get("event") or ""
        session_id = data.get("session_id") or data.get("sessionId") or data.get("conversation_id") or ""
        path = data.get("transcript_path")
        if agent == "copilot" and not path and session_id:
            base = os.environ.get("COPILOT_HOME") or os.path.join(HOME, ".copilot")
            path = os.path.join(base, "session-state", str(session_id), "events.jsonl")
        tokens = None
        model = data.get("model") or data.get("model_id")
        if isinstance(model, dict):
            model = model.get("id")
        window_hint = data.get("context_window_size")
        estimated = False
        harness = agent
        kind = None
        if data.get("context_tokens"):  # Claude SessionStart(resume), Cursor preCompact
            tokens = int(data["context_tokens"])
        elif path and os.path.exists(winpath(path)):
            m = measure_path(path, agent)
            if m:
                kind = m.get("kind")
                tokens = m["tokens"]
                model = model or m.get("model")
                window_hint = window_hint or m.get("window_hint")
                estimated = bool(m.get("estimated"))
                # VS Code (and any Claude-style hook) may hand us another harness's transcript:
                # the transcript format says which harness, and therefore which cap, applies.
                harness = {"codex-jsonl": "codex", "copilot-events": "copilot", "copilot-events-estimate": "copilot"}.get(m.get("kind"), agent)
        if tokens is None:
            return 0
        if harness == "vscode":
            harness = "claude"
        if not session_id:
            session_id = os.path.basename(path or "") or "nosession"
        ev = evaluate(models, cfg, tokens, model, harness, path, window_hint)
        live = should_emit(agent, session_id, ev["band"], cfg)
        b_model, b_user = (None, None)
        if path and os.path.exists(winpath(path)):
            b_model, b_user = baseline_step(models, cfg, agent, harness, session_id, path, data, kind, model, window_hint)
        if not live and not b_model:
            return 0
        m_parts = []
        u_parts = []
        if live:
            m_parts.append(message_for_model(models, ev, estimated))
            if ev["band"] >= 2:
                u_parts.append(message_for_user(models, ev, estimated))
        if b_model:
            m_parts.append(b_model)
        if b_user:
            u_parts.append(b_user)
        m_text = "\n".join(m_parts)
        u_text = "\n".join(u_parts)
        if agent == "copilot":
            out = {"additionalContext": m_text}
        elif agent == "cursor":
            out = {"user_message": u_text or m_text} if event == "preCompact" else {"additional_context": m_text}
        else:  # claude, vscode, codex, gemini: Claude-style hook JSON
            out = {"hookSpecificOutput": {"hookEventName": event or "UserPromptSubmit", "additionalContext": m_text}}
            if u_text:
                out["systemMessage"] = u_text
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    except Exception as e:
        dbg("hook failed: %r" % e)
    return 0


ANSI = {0: "\033[32m", 1: "\033[36m", 2: "\033[33m", 3: "\033[35m", 4: "\033[1;31m"}


def cmd_statusline(a):
    try:
        models = load_models()
        cfg = load_cfg()
        data = read_stdin_json()
        model = (data.get("model") or {}).get("id") or ""
        label = short_label(model) if model else ((data.get("model") or {}).get("display_name") or "?")
        cw = data.get("context_window") or {}
        cu = cw.get("current_usage") or {}
        cwd = os.path.basename((data.get("workspace") or {}).get("current_dir") or data.get("cwd") or "")
        if not cu:
            sys.stdout.write("%s | ctx - | %s\n" % (label, cwd))
            return 0
        tokens = int(cu.get("input_tokens") or 0) + int(cu.get("cache_creation_input_tokens") or 0) + int(cu.get("cache_read_input_tokens") or 0)
        hw = cw.get("context_window_size")
        ev = evaluate(models, cfg, tokens, model, "claude", data.get("transcript_path"), hw)
        bt = band_text(models, ev["band_name"])
        col = ANSI.get(ev["band"], "")
        tag = bt["label"] if ev["band"] else "ok"
        comp = " compact soon" if ev["compaction"] == 2 else (" compact near" if ev["compaction"] == 1 else "")
        sys.stdout.write("%s | ctx %s/%s %d%% %s%s%s\033[0m | %s\n" % (
            label, k(tokens), k(ev["harness_window"]), ev["pct_harness"], col, tag, comp, cwd))
    except Exception as e:
        dbg("statusline failed: %r" % e)
    return 0


def describe(models, m, ev, agent):
    bt = band_text(models, ev["band_name"])
    age = ""
    if m.get("age_s") is not None:
        s = int(m["age_s"])
        age = " (%s ago)" % ("%ds" % s if s < 90 else "%dm" % (s // 60) if s < 5400 else "%dh" % (s // 3600))
    lines = []
    lines.append("context-health %s | agent: %s | model: %s%s" % (
        VERSION, ev["harness"], ev["model"] or "unknown", " (not in models.json, assuming 200K)" if ev["unknown_model"] else ""))
    lines.append("source: %s%s [%s]" % (m.get("path") or "-", age, m.get("kind")))
    est = "roughly " if m.get("estimated") else "~"
    lines.append("context: %s%s tokens = %d%% of the %s %s window (native %s, %s)" % (
        est, k(ev["tokens"]), ev["pct_harness"], k(ev["harness_window"]), ev["harness"], k(ev["native_window"]), ev["family_label"]))
    raised = " (raised by compaction proximity, not degradation)" if ev["band"] > ev["degradation_band"] else ""
    lines.append("band: %s - %s%s" % (bt["label"], bt["effects"] or "no measurable effect", raised))
    base = ((models.get("harnesses") or {}).get(ev["harness"]) or {}).get("base_context_tokens")
    if base:
        lines.append("note: a fresh %s session already carries ~%s of tool and skill catalog; growth above that is the signal" % (ev["harness"], k(base)))
    th = ev["thresholds"]
    lines.append("bands (%s profile): watch %s | caution %s | warning %s | critical %s" % (ev["profile"], k(th[0]), k(th[1]), k(th[2]), k(th[3])))
    if ev["compaction_fraction"]:
        state = {0: "not near", 1: "approaching", 2: "imminent"}[ev["compaction"]]
        lines.append("compaction: %s (harness compacts near %d%% of its window)" % (state, round(100 * ev["compaction_fraction"])))
    lines.append("recommendation: %s" % (bt["advice"] or "continue"))
    if m.get("kind", "").endswith("estimate"):
        lines.append("note: this agent's transcript carries no token counts; the figure is a size estimate. Prefer the agent's own meter (/context, /status, /stats) when available.")
    return "\n".join(lines)


def cmd_status(a):
    models = load_models()
    cfg = load_cfg()
    path = a.file
    agent = a.agent or "auto"
    if not path:
        path, found_agent = newest_session(agent)
        if not path:
            print("no session transcript found for agent=%s (searched: %s)" % (agent, "; ".join(candidate_globs(agent) if agent != "auto" else [g for x in AGENTS if x != "vscode" for g in candidate_globs(x)])))
            return 1
        agent = found_agent
    elif agent == "auto":
        agent = {"claude": "claude", "codex": "codex", "copilot": "copilot"}.get(detect_kind(path), "claude")
    m = measure_path(path, agent)
    if not m:
        print("could not measure %s" % path)
        return 1
    ev = evaluate(models, cfg, m["tokens"], a.model or m.get("model"), agent, path, m.get("window_hint"))
    first = measure_first(path, agent)
    if a.json:
        out = dict(ev)
        out.update({"path": path, "kind": m.get("kind"), "estimated": bool(m.get("estimated")), "age_s": m.get("age_s")})
        if first:
            out["startup"] = evaluate_baseline(models, cfg, first["startup"], a.model or first.get("model"), ev["harness"], path, first.get("window_hint"))
            out["startup"].update({"platform": platform_for(agent, path, first.get("kind")), "first_turn": first["tokens"], "prompt_est": first.get("prompt_tokens_est", 0)})
        out["selection"] = evaluate_selection(models, cfg, os.getcwd())
        print(json.dumps(out, indent=2))
    else:
        print(describe(models, m, ev, agent))
        print("\n".join(describe_baseline(models, cfg, first, path, agent, ev["harness"], a.model)))
        sev = evaluate_selection(models, cfg, os.getcwd())
        budget = (ev.get("harness_window") or 0) * (((models.get("selection") or {}).get("listing_budget_fraction")) or 0.01)
        print("\n".join(describe_selection(models, cfg, sev, budget)))
    return 0


def cmd_models(a):
    models = load_models()
    cfg = load_cfg()
    if a.model is not None:
        fam, norm, one_m = find_family(models, a.model)
        print("model %s -> normalized %s -> family %s (%s), native window %s, class %s%s" % (
            a.model, norm, fam.get("id"), fam.get("label"), k(fam.get("window")), fam.get("class"), " [1m]" if one_m else ""))
        for pname, pf in models["profiles"].items():
            if pname.startswith("_"):
                continue
            fr = pf.get(fam.get("class"), pf.get("200k"))
            th = [k(int(round(f * fam["window"]))) for f in fr]
            print("  %-12s watch %s | caution %s | warning %s | critical %s%s" % (pname, th[0], th[1], th[2], th[3], "  (active)" if pname == cfg.get("profile") else ""))
        if fam.get("note"):
            print("  note: %s" % fam["note"])
        return 0
    print("models.json %s (last checked %s), active profile: %s" % (models.get("version"), models.get("last_checked"), cfg.get("profile")))
    for fam in models["families"]:
        print("  %-18s %-30s window %-6s class %-5s match %s" % (fam["id"], fam.get("label", ""), k(fam["window"]), fam.get("class"), ", ".join(fam.get("match", [])[:4]) + (" ..." if len(fam.get("match", [])) > 4 else "")))
    print("harness caps:")
    for hname, h in (models.get("harnesses") or {}).items():
        if hname.startswith("_"):
            continue
        print("  %-8s window %-6s %s" % (hname, k(h.get("window")) if h.get("window") else "native", (h.get("note") or "")[:110]))
    return 0


def cmd_config(a):
    cfg = load_cfg()
    if a.op == "set" and a.key:
        val = a.value
        if val is None:
            print("usage: config set KEY VALUE")
            return 2
        if re.fullmatch(r"-?\d+", val):
            val = int(val)
        elif re.fullmatch(r"-?\d+\.\d+", val):
            val = float(val)
        elif val.lower() in ("true", "false"):
            val = val.lower() == "true"
        keys = a.key.split(".")
        models = load_models()
        profiles = [p for p in models["profiles"] if not p.startswith("_")]
        harnesses = [h for h in (models.get("harnesses") or {}) if not h.startswith("_")]
        if keys == ["profile"] and val not in profiles:
            print("profile must be one of: %s" % ", ".join(profiles))
            return 2
        if keys == ["min_band"] and val not in BANDS[1:]:
            print("min_band must be one of: %s" % ", ".join(BANDS[1:]))
            return 2
        if keys[0] == "windows" and (len(keys) != 2 or keys[1] not in harnesses or not isinstance(val, int) or val <= 0):
            print("usage: config set windows.<harness> <tokens>; harnesses: %s" % ", ".join(harnesses))
            return 2
        if keys == ["cooldown_scale"] and (not isinstance(val, (int, float)) or val <= 0):
            print("cooldown_scale must be a positive number")
            return 2
        if keys[0] == "baseline":
            ok = len(keys) == 2 and (
                (keys[1] == "enabled" and isinstance(val, bool))
                or (keys[1] == "audit_every" and isinstance(val, int) and not isinstance(val, bool) and val > 0)
                or (keys[1] == "min_band" and val in BASELINE_BANDS[1:])
                or (keys[1] == "jump" and isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0)
                or (keys[1] == "warn_days" and isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0))
            if not ok:
                print("usage: config set baseline.enabled true|false | baseline.audit_every <n> | baseline.min_band %s | baseline.jump <fraction> | baseline.warn_days <days>" % "|".join(BASELINE_BANDS[1:]))
                return 2
        elif keys[0] not in ("profile", "min_band", "windows", "cooldown_scale") or (keys[0] != "windows" and len(keys) != 1):
            print("unknown key %s; keys: profile, min_band, windows.<harness>, cooldown_scale, baseline.<enabled|audit_every|min_band|jump|warn_days>" % a.key)
            return 2
        node = cfg
        for kk in keys[:-1]:
            if not isinstance(node.get(kk), dict):
                node[kk] = {}
            node = node[kk]
        node[keys[-1]] = val
        write_json(CFG_PATH, cfg)
        print("set %s = %r (%s)" % (a.key, val, CFG_PATH))
        return 0
    if a.op == "get" and a.key:
        node = cfg
        for kk in a.key.split("."):
            node = node.get(kk) if isinstance(node, dict) else None
        print(json.dumps(node))
        return 0
    print(json.dumps(cfg, indent=2))
    print("keys: profile (balanced|conservative|relaxed), min_band (watch|caution|warning), windows.<harness> (token cap, e.g. windows.copilot 1000000), cooldown_scale, baseline.enabled, baseline.audit_every (default 10), baseline.min_band (notable|high|excessive), baseline.jump (default 0.25), baseline.warn_days (default 7)")
    return 0


def cmd_sniff(a):
    path = a.file
    if not os.path.exists(winpath(path)):
        print("no such file: %s" % path)
        return 1
    kind = detect_kind(path)
    print("file: %s\nsize: %d bytes\ndetected kind: %s" % (path, os.path.getsize(winpath(path)), kind))
    lines = tail_lines(path)
    types = {}
    usage_lines = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t = obj.get("type") or (obj.get("message") or {}).get("role") if isinstance(obj, dict) else None
        p = obj.get("payload") if isinstance(obj, dict) else None
        if isinstance(p, dict) and p.get("type"):
            t = "%s/%s" % (t, p.get("type"))
        types[t] = types.get(t, 0) + 1
        if re.search(r"[Tt]oken|usage", line):
            usage_lines.append(line)
    print("record types (tail %s):" % k(min(os.path.getsize(winpath(path)), TAIL_BYTES)))
    for t, n in sorted(types.items(), key=lambda x: -x[1])[:25]:
        print("  %5d  %s" % (n, t))
    print("last usage-like records:")
    for line in usage_lines[-3:]:
        print("  " + (line[:400] + ("..." if len(line) > 400 else "")))
    m = measure_path(path)
    print("measure_path ->", json.dumps({kk: v for kk, v in (m or {}).items() if kk != "path"}))
    return 0


# ----------------------------------------------------------------------------- freshness (evergreen Step 0 without the plugin)

TIER_BOUNDS = {"live": (0.25, 3), "fast": (3, 21), "moderate": (14, 90), "slow": (60, 365), "glacial": (270, 900), "code": (7, 90)}


def cmd_fresh(a):
    eg = read_json(EVERGREEN_PATH)
    if not eg:
        print("no evergreen.json next to ctxhealth.py; research freshness unknown")
        return 1
    due = eg.get("next_due")
    if eg.get("contradiction"):
        print("CONTRADICTION flagged: %s -> refresh research (see MAINTENANCE.md)" % eg["contradiction"])
        return 1
    if not due:
        print("no next_due set (verify_at_use=%s)" % eg.get("verify_at_use"))
        return 0
    d = (_dt.date.fromisoformat(due) - _dt.date.today()).days
    if d < 0:
        print("DUE: research is %d days past due (last checked %s). Refresh after the current task (MAINTENANCE.md, Refresh)." % (-d, eg.get("last_checked")))
        return 1
    print("fresh: last checked %s, next due %s (%d days)" % (eg.get("last_checked"), due, d))
    return 0


def cmd_checked(a):
    """Apply the evergreen hand rule (INTERVALS.md) and record the check."""
    eg = read_json(EVERGREEN_PATH) or {}
    tier = eg.get("tier", "fast")
    lo, hi = tuple(eg.get("bounds_days") or TIER_BOUNDS.get(tier, (3, 21)))
    interval = float(eg.get("interval_days") or 14)
    m = a.m
    if m is None:
        eg.setdefault("history", []).append({"date": today(), "m": None, "interval_after": interval, "note": a.note or "refresh failed; retry next use"})
        write_json(EVERGREEN_PATH, eg)
        print("recorded failed refresh; next_due unchanged (%s)" % eg.get("next_due"))
        return 0
    if eg.get("contradiction"):
        interval = lo
    elif m >= 0.6:
        interval = interval / 4.0
    elif m >= 0.3:
        interval = interval / 2.0
    elif m == 0:
        interval = interval * 1.5
    interval = max(lo, min(hi, interval))
    nd = _dt.date.today() + _dt.timedelta(days=interval)
    for e in eg.get("events") or []:
        try:
            ed = _dt.date.fromisoformat(e["date"]) + _dt.timedelta(days=int(e.get("settle_days", 0)))
            if ed > _dt.date.today() and ed < nd:
                nd = ed
        except Exception:
            pass
    eg["interval_days"] = round(interval, 2)
    eg["last_checked"] = today()
    eg["next_due"] = nd.isoformat()
    eg["contradiction"] = None
    eg.setdefault("history", []).append({"date": today(), "m": m, "interval_after": round(interval, 2), "note": a.note or ""})
    write_json(EVERGREEN_PATH, eg)
    models = read_json(MODELS_PATH)
    if models:
        models["last_checked"] = today()
        write_json(MODELS_PATH, models)
    print("checked %s: m=%s, interval %s days, next due %s" % (today(), m, round(interval, 1), nd.isoformat()))
    return 0


# ----------------------------------------------------------------------------- install / uninstall

def _has_mark(obj, mark):
    try:
        return mark in json.dumps(obj)
    except Exception:
        return False


def _is_link(path):
    """True for symlinks and Windows junctions (os.path.islink misses junctions)."""
    if os.path.islink(path):
        return True
    if os.name == "nt":
        try:
            os.readlink(path)
            return True
        except OSError:
            return False
    return False


def _remove_link_or_dir(path):
    if _is_link(path):
        if os.name == "nt" and os.path.isdir(path):
            os.rmdir(path)  # removes the junction, not its target
        else:
            os.unlink(path)
    else:
        shutil.rmtree(path)


def _link_dir(src, dst, copy=False):
    """Make dst point at src (junction on Windows, symlink elsewhere); copy on failure or when asked.
    A pre-existing real folder at dst is replaced only when it is an earlier copy of this skill."""
    src = os.path.abspath(src)
    if os.path.lexists(dst):
        try:
            if os.path.exists(dst) and os.path.samefile(dst, src):
                return "already linked"
        except OSError:
            pass
        if not _is_link(dst) and not os.path.exists(os.path.join(dst, "ctxhealth.py")):
            return "exists and is not ours (left untouched): %s" % dst
        _remove_link_or_dir(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not copy:
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(src, dst)
            else:
                os.symlink(src, dst)
            return "linked -> %s" % src
        except Exception as e:
            dbg("link failed, copying: %r" % e)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
    return "copied (edits belong in %s)" % src


def install_claude(cmd, dry, statusline=True, replace_legacy=False):
    path = os.path.join(HOME, ".claude", "settings.json")
    s, _ = load_config_file(path)
    hooks = s.setdefault("hooks", {})
    notes = []
    for evname in ("UserPromptSubmit", "SessionStart"):
        arr = hooks.setdefault(evname, [])
        arr[:] = [g for g in arr if not _has_mark(g, MARK)]
        legacy = [g for g in arr if _has_mark(g, LEGACY_MARK)]
        if legacy:
            if replace_legacy:
                arr[:] = [g for g in arr if not _has_mark(g, LEGACY_MARK)]
                notes.append("removed legacy %s hook from %s" % (LEGACY_MARK, evname))
            else:
                notes.append("NOTE: legacy %s hook still present in %s (rerun with --replace-legacy to remove; both would fire)" % (LEGACY_MARK, evname))
        arr.append({"hooks": [{"type": "command", "command": "%s hook --agent claude" % cmd, "timeout": 10}]})
    if statusline:
        cur = s.get("statusLine")
        if not cur or _has_mark(cur, MARK):
            s["statusLine"] = {"type": "command", "command": "%s statusline" % cmd, "padding": 0}
            notes.append("statusLine set")
        else:
            notes.append("statusLine left as is (already customized); add manually: %s statusline" % cmd)
    if not dry:
        write_config_file(path, s)
    return path, notes


def install_copilot(cmd, dry):
    base = os.environ.get("COPILOT_HOME") or os.path.join(HOME, ".copilot")
    path = os.path.join(base, "hooks", "context-health.json")
    entry = {"type": "command", "bash": "%s hook --agent copilot" % cmd, "powershell": "%s hook --agent copilot" % cmd, "timeoutSec": 10}
    obj = {"version": 1, "hooks": {"sessionStart": [entry], "postToolUse": [dict(entry)]}}
    if not dry:
        write_json(path, obj)
    return path, ["events: sessionStart, postToolUse (userPromptSubmitted cannot inject context)"]


def _merge_claude_style(path, cmd, agent, events, extra=None, timeout=10):
    s, _ = load_config_file(path)
    hooks = s.setdefault("hooks", {})
    for evname in events:
        arr = hooks.setdefault(evname, [])
        arr[:] = [g for g in arr if not _has_mark(g, MARK)]
        h = {"type": "command", "command": "%s hook --agent %s" % (cmd, agent), "timeout": timeout}
        if extra:
            h.update(extra)
        arr.append({"hooks": [h]})
    return s


def install_codex(cmd, dry):
    base = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
    path = os.path.join(base, "hooks.json")
    s = _merge_claude_style(path, cmd, "codex", ("SessionStart", "UserPromptSubmit"))
    if not dry:
        write_config_file(path, s)
    return path, ["events: SessionStart, UserPromptSubmit (Codex token_count events give exact numbers)"]


def install_gemini(cmd, dry):
    path = os.path.join(HOME, ".gemini", "settings.json")
    s = _merge_claude_style(path, cmd, "gemini", ("SessionStart", "BeforeAgent"), extra={"name": "context-health"}, timeout=10000)
    if not dry:
        write_config_file(path, s)
    return path, ["events: SessionStart, BeforeAgent (experimental: Gemini transcripts carry no token counts, size estimate only; the footer % is authoritative)"]


def install_cursor(cmd, dry):
    path = os.path.join(HOME, ".cursor", "hooks.json")
    s, _ = load_config_file(path)
    s.setdefault("version", 1)
    hooks = s.setdefault("hooks", {})
    for evname in ("sessionStart", "postToolUse", "preCompact"):
        arr = hooks.setdefault(evname, [])
        arr[:] = [g for g in arr if not _has_mark(g, MARK)]
        arr.append({"command": "%s hook --agent cursor" % cmd})
    if not dry:
        write_config_file(path, s)
    return path, ["events: sessionStart, postToolUse, preCompact (experimental; preCompact supplies exact context_tokens)"]


def cmd_install(a):
    cmd = python_cmd()
    dry = a.dry_run
    want = detected_agents() if a.agent in ("all", None) else [a.agent]
    print("context-health %s install%s\ncommand prefix: %s" % (VERSION, " (dry run)" if dry else "", cmd))
    if a.agent in ("all", None):
        print("detected agents: %s" % (", ".join(want) or "none (use --agent NAME to force)"))
    # shared skill location for Copilot CLI, Codex, Cursor, Gemini (+ Claude Code's own dir)
    shared = os.path.join(HOME, ".agents", "skills", "context-health")
    targets = [shared]
    if "claude" in want or "vscode" in want:
        targets.append(os.path.join(HOME, ".claude", "skills", "context-health"))
    for t in targets:
        if os.path.abspath(t) == os.path.abspath(SKILL_DIR):
            print("skill: %s is the source itself" % t)
            continue
        if dry:
            print("skill: would link %s -> %s" % (t, SKILL_DIR))
        else:
            print("skill: %s %s" % (t, _link_dir(SKILL_DIR, t, copy=a.copy)))
    for agent in want:
        try:
            if agent in ("claude", "vscode"):
                path, notes = install_claude(cmd, dry, statusline=not a.no_statusline, replace_legacy=a.replace_legacy)
                notes.append("VS Code agent hooks read ~/.claude/settings.json too (chat.hookFilesLocations default)")
            elif agent == "copilot":
                path, notes = install_copilot(cmd, dry)
            elif agent == "codex":
                path, notes = install_codex(cmd, dry)
            elif agent == "gemini":
                path, notes = install_gemini(cmd, dry)
            elif agent == "cursor":
                path, notes = install_cursor(cmd, dry)
            else:
                print("%s: unknown agent" % agent)
                continue
            print("%s: %s %s" % (agent, "would write" if dry else "wrote", path))
            for n in notes:
                print("   - %s" % n)
        except ConfigError as e:
            print("%s: SKIPPED - %s" % (agent, e))
        except Exception as e:
            print("%s: FAILED %r" % (agent, e))
    # evergreen.json is tracked in the repository and stays free of local absolute paths;
    # `doctor` prints the skill dir instead.
    print("done. Restart the agent(s); run `%s doctor` to verify." % cmd)
    return 0


def _strip_hooks(path, hooks_key="hooks"):
    """Remove our entries from a hooks-style config; returns True when something was written."""
    s, existed = load_config_file(path)
    if not existed:
        return False
    for evname, arr in list((s.get(hooks_key) or {}).items()):
        if isinstance(arr, list):
            arr[:] = [g for g in arr if not _has_mark(g, MARK)]
            if not arr:
                del s[hooks_key][evname]
    if _has_mark(s.get("statusLine"), MARK):
        del s["statusLine"]
    write_config_file(path, s)
    return True


def cmd_uninstall(a):
    everything = a.agent in ("all", None)
    want = detected_agents() if everything else [a.agent]
    for agent in want:
        try:
            if agent in ("claude", "vscode"):
                path = os.path.join(HOME, ".claude", "settings.json")
                done = _strip_hooks(path)
            elif agent == "copilot":
                base = os.environ.get("COPILOT_HOME") or os.path.join(HOME, ".copilot")
                path = os.path.join(base, "hooks", "context-health.json")
                done = os.path.exists(path)
                if done:
                    os.remove(path)
            elif agent in ("codex", "gemini", "cursor"):
                path = {"codex": os.path.join(os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex"), "hooks.json"),
                        "gemini": os.path.join(HOME, ".gemini", "settings.json"),
                        "cursor": os.path.join(HOME, ".cursor", "hooks.json")}[agent]
                done = _strip_hooks(path)
            else:
                print("%s: unknown agent" % agent)
                continue
            print("%s: %s %s" % (agent, "removed context-health entries from" if done else "nothing to remove in", path))
        except ConfigError as e:
            print("%s: SKIPPED - %s" % (agent, e))
    if everything:  # the shared skill links serve every agent; drop them only on a full uninstall
        for t in (os.path.join(HOME, ".agents", "skills", "context-health"), os.path.join(HOME, ".claude", "skills", "context-health")):
            if os.path.lexists(t) and os.path.abspath(t) != os.path.abspath(SKILL_DIR):
                if not _is_link(t) and not os.path.exists(os.path.join(t, "ctxhealth.py")):
                    print("left %s (not ours)" % t)
                    continue
                _remove_link_or_dir(t)
                print("removed %s" % t)
    return 0


def cmd_doctor(a):
    models = load_models()
    cfg = load_cfg()
    print("context-health %s | python %s | %s | skill dir %s" % (VERSION, sys.version.split()[0], sys.platform, SKILL_DIR))
    print("command prefix: %s" % python_cmd())
    print("config: %s (profile %s, min_band %s, windows %s)" % (CFG_PATH, cfg.get("profile"), cfg.get("min_band"), json.dumps(cfg.get("windows"))))
    print("models.json: %s, last checked %s" % (models.get("version"), models.get("last_checked")))
    class A:  # fresh() wants an args object
        pass
    cmd_fresh(A())
    for t in (os.path.join(HOME, ".agents", "skills", "context-health"), os.path.join(HOME, ".claude", "skills", "context-health")):
        print("skill path %s: %s" % (t, "ok" if os.path.exists(os.path.join(t, "SKILL.md")) else "missing"))
    found = detected_agents()
    print("detected agents: %s" % (", ".join(found) or "none"))
    checks = {
        "claude": os.path.join(HOME, ".claude", "settings.json"),
        "copilot": os.path.join(os.environ.get("COPILOT_HOME") or os.path.join(HOME, ".copilot"), "hooks", "context-health.json"),
        "codex": os.path.join(os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex"), "hooks.json"),
        "gemini": os.path.join(HOME, ".gemini", "settings.json"),
        "cursor": os.path.join(HOME, ".cursor", "hooks.json"),
    }
    for agent in found:
        p = checks[agent]
        s = read_json(p, {}) or {}
        installed = _has_mark(s, MARK)
        extra = ""
        if agent == "claude":
            extra = ", statusline %s" % ("ours" if _has_mark(s.get("statusLine"), MARK) else ("other" if s.get("statusLine") else "none"))
            if _has_mark(s.get("hooks"), LEGACY_MARK):
                extra += ", LEGACY context-health.ps1 hook present"
        print("%s: hooks %s%s (%s)" % (agent, "installed" if installed else "NOT installed", extra, p))
        path, _ = newest_session(agent)
        if path:
            m = measure_path(path, agent)
            if m:
                ev = evaluate(models, cfg, m["tokens"], m.get("model"), agent, path, m.get("window_hint"))
                print("   newest session: %s%s tokens, %s, %s [%s]" % ("est. " if m.get("estimated") else "~", k(m["tokens"]), ev["band_name"].upper(), ev["model_label"], m.get("kind")))
            else:
                print("   newest session: %s (could not measure; run `sniff` on it and adapt the parser)" % path)
        else:
            print("   no sessions found on disk")
    if "claude" in found:
        print("vscode: agent hooks read ~/.claude/settings.json; Copilot/Claude/Codex harness sessions are measured by sniffing transcript_path")
    bc = baseline_cfg(cfg)
    recorded = [p for p in PLATFORMS if os.path.exists(_bl_paths(p)[0])]
    if not recorded:
        print("startup baselines: none recorded yet (%s; audit every %s sessions)" % (baseline_dir(), bc["audit_every"]))
    for p in recorded:
        meta = read_json(_bl_paths(p)[1], {}) or {}
        rows = baseline_history(p, limit=1)
        last = rows[-1] if rows else {}
        print("startup baseline %s: %s sessions, latest ~%s %s (%s), last audit session %s" % (
            p, meta.get("sessions", "?"), k(int(last.get("startup", 0))), str(last.get("band", "?")).upper(), last.get("date", "-"), meta.get("last_audit_session") or "never"))
    return 0


# ----------------------------------------------------------------------------- pack

def plugin_root():
    up2 = os.path.abspath(os.path.join(SKILL_DIR, "..", ".."))
    if os.path.exists(os.path.join(up2, ".claude-plugin", "plugin.json")):
        return up2
    return SKILL_DIR


def cmd_pack(a):
    root = plugin_root()
    name = os.path.basename(root)
    manifest = read_json(os.path.join(root, ".claude-plugin", "plugin.json"), {}) or {}
    ver = manifest.get("version") or VERSION
    out = a.out or os.path.dirname(root)
    os.makedirs(out, exist_ok=True)
    skip_dirs = {".git", ".github", "__pycache__", ".pytest_cache", "node_modules", "_host", "ai-docs", "dist"}
    skip_files = ("*.pyc", "*.zip", "*.plugin", ".DS_Store", "*.tmp")
    files = []
    blocked = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in skip_dirs]
        for fn in fns:
            if any(fnmatch.fnmatch(fn, p) for p in skip_files):
                continue
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if os.path.splitext(fn)[1].lower() in MAIL_BLOCKED:
                blocked.append(rel)
            files.append((full, rel))
    if blocked:
        print("refusing to pack: mail-blocked file types present: %s" % ", ".join(blocked))
        return 1
    install_txt = (
        "context-health %s - cross-agent context health (warns when a session is big enough to degrade the model)\n\n"
        "1. Unzip anywhere permanent, e.g. D:\\tools\\context-health (the hooks point at this folder).\n"
        "2. Run:  python context-health/skills/context-health/ctxhealth.py install --agent all\n"
        "   (needs Python 3.8+; installs hooks for every detected agent, a Claude Code status line,\n"
        "    and links the skill into ~/.agents/skills and ~/.claude/skills)\n"
        "3. Restart the agents. Verify:  python .../ctxhealth.py doctor\n"
        "Details and per-agent notes: context-health/README.md. Nothing in this zip is executable mail-wise (no .ps1/.js/.cmd).\n" % ver)
    zpath = os.path.join(out, "%s-%s.zip" % (name, ver))
    ppath = os.path.join(out, "%s.plugin" % name)
    for p in (zpath, ppath):
        if os.path.exists(p):
            os.remove(p)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("INSTALL.txt", install_txt)
        for full, rel in files:
            z.write(full, "%s/%s" % (name, rel))
    with zipfile.ZipFile(ppath, "w", zipfile.ZIP_DEFLATED) as z:
        for full, rel in files:
            z.write(full, rel)
    for p in (zpath, ppath):
        print("wrote %s (%d KB)" % (p, os.path.getsize(p) // 1024))
    return 0


# ----------------------------------------------------------------------------- main

def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="ctxhealth", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd")
    s = sp.add_parser("status", help="report the newest session (or --file) against the model's bands")
    s.add_argument("--agent", default="auto", choices=["auto"] + AGENTS)
    s.add_argument("--file")
    s.add_argument("--model", help="override the model id")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sp.add_parser("hook", help="agent hook entry point (reads the hook JSON on stdin)")
    s.add_argument("--agent", choices=AGENTS)
    s.set_defaults(fn=cmd_hook)
    s = sp.add_parser("statusline", help="Claude Code statusLine command (reads its JSON on stdin)")
    s.set_defaults(fn=cmd_statusline)
    s = sp.add_parser("install", help="write hooks/statusline/skill links for detected agents")
    s.add_argument("--agent", default="all", choices=["all"] + AGENTS)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--no-statusline", action="store_true")
    s.add_argument("--replace-legacy", action="store_true", help="remove the old context-health.ps1 hook")
    s.add_argument("--copy", action="store_true", help="copy the skill instead of linking")
    s.set_defaults(fn=cmd_install)
    s = sp.add_parser("uninstall")
    s.add_argument("--agent", default="all", choices=["all"] + AGENTS)
    s.set_defaults(fn=cmd_uninstall)
    s = sp.add_parser("doctor", help="what is installed, what can be measured, is the research fresh")
    s.set_defaults(fn=cmd_doctor)
    s = sp.add_parser("baseline", help="startup (initial) context: recorded sizes per platform, or measure one transcript with --file")
    s.add_argument("--file", help="measure the first turn of this transcript")
    s.add_argument("--agent", default="auto", choices=["auto"] + AGENTS)
    s.add_argument("--model", help="override the model id")
    s.add_argument("--platform", choices=PLATFORMS)
    s.add_argument("--history", type=int, default=0, help="also list the last N recorded sessions")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_baseline)
    s = sp.add_parser("selection", help="selection noise: how many skills compete for the model's choice")
    s.add_argument("--project", help="project root whose .claude/skills also counts (default: cwd)")
    s.add_argument("--list", action="store_true", help="list every visible skill with its description size")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_selection)

    s = sp.add_parser("models", help="list model families or resolve one id")
    s.add_argument("--model")
    s.set_defaults(fn=cmd_models)
    s = sp.add_parser("config", help="show or change ~/.ctxhealth/config.json")
    s.add_argument("op", nargs="?", choices=["get", "set"])
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.set_defaults(fn=cmd_config)
    s = sp.add_parser("sniff", help="inspect a transcript file: format, record types, usage records")
    s.add_argument("file")
    s.set_defaults(fn=cmd_sniff)
    s = sp.add_parser("fresh", help="is the research past due? (exit 1 when due)")
    s.set_defaults(fn=cmd_fresh)
    s = sp.add_parser("checked", help="record a research refresh and reschedule (hand rule)")
    s.add_argument("--m", type=float, default=None, help="change magnitude 0..1; omit for a failed refresh")
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_checked)
    s = sp.add_parser("pack", help="build context-health-<ver>.zip (mail-safe) and context-health.plugin")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_pack)
    s = sp.add_parser("version")
    s.set_defaults(fn=lambda a: print(VERSION) or 0)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
