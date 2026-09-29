# -*- coding: utf-8 -*-
"""Tests for ctxhealth.py. Run: python -m pytest tests  (or: python tests/test_ctxhealth.py)
Synthetic transcripts follow the shapes documented in RESEARCH.md; the Claude shape is
verified against live files, the Codex/Copilot shapes are from vendor docs and community
dumps (see LEARNINGS.md L-003). Keep fixtures small; they only exercise the parsers."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "skills", "context-health")
sys.path.insert(0, SKILL)
import ctxhealth as ch  # noqa: E402


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln) if not isinstance(ln, str) else ln)
            f.write("\n")


def claude_lines(tokens, model="claude-opus-5", sidechain_tokens=None):
    u = {"input_tokens": 1000, "cache_read_input_tokens": tokens - 3000, "cache_creation_input_tokens": 2000, "output_tokens": 50}
    rows = [
        {"type": "user", "isSidechain": False, "message": {"role": "user", "content": "hi"}, "sessionId": "s1", "parentUuid": None},
        {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "model": model, "usage": u, "content": []}, "sessionId": "s1"},
        {"type": "user", "isSidechain": False, "message": {"role": "user", "content": "more"}, "sessionId": "s1"},
    ]
    if sidechain_tokens:
        rows.append({"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "model": "claude-haiku-4-5", "usage": {"input_tokens": sidechain_tokens}}})
    return rows


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ctxh-")
        os.environ["CTXHEALTH_HOME"] = os.path.join(self.tmp, "home")
        ch.CFG_DIR = os.environ["CTXHEALTH_HOME"]
        ch.CFG_PATH = os.path.join(ch.CFG_DIR, "config.json")
        ch.STATE_DIR = os.path.join(ch.CFG_DIR, "state")
        os.environ["CTXHEALTH_SKILLS_HOME"] = os.path.join(self.tmp, "skillshome")  # never scan the real catalog
        self.models = ch.load_models()
        self.cfg = ch.load_cfg()

    def path(self, name):
        return os.path.join(self.tmp, name)


class TestModels(Base):
    def test_families(self):
        cases = {
            "claude-fable-5-1": ("claude-1m", 1000000), "claude-opus-5-5": ("claude-1m", 1000000), "claude-opus-5[1m]": ("claude-1m", 1000000),
            "anthropic.claude-sonnet-4-5-20250929-v1:0": ("claude-200k", 200000), "claude-haiku-4-5-20251001": ("claude-200k", 200000),
            "opus": ("claude-1m", 1000000), "claude-opus-4-6": ("claude-1m", 1000000), "claude-opus-4-5": ("claude-200k", 200000),
            "gpt-5.5": ("gpt-5.5", 1050000), "gpt-5.5-codex": ("gpt-5.5", 1050000), "gpt-5.4": ("gpt-5.4", 256000),
            "gpt-5.3-codex": ("gpt-5-400k", 400000), "gpt-5.6-sol": ("gpt-5.6", 272000), "gpt-6-astra": ("gpt-6-astra", 1000000), "gpt-6-sol": ("gpt-6-sol-luna", 922000), "gpt-6-luna": ("gpt-6-sol-luna", 922000), "gpt-4.1": ("gpt-4.1", 1047576),
            "o3": ("openai-legacy", 200000), "gemini-3.1-pro-preview": ("gemini-1m", 1048576), "gemini-3-flash-preview": ("gemini-1m", 1048576),
            "grok-code-fast-1": ("grok", 256000), "grok-4.5": ("grok-4.5", 500000), "grok-4.7": ("grok-4.5", 500000), "claude-sonnet-5-5": ("claude-1m", 1000000), "kimi-k3": ("unknown", 200000), "": ("unknown", 200000),
        }
        for mid, (fid, win) in cases.items():
            fam, norm, one_m = ch.find_family(self.models, mid)
            self.assertEqual(fam["id"], fid, mid)
            self.assertEqual(fam["window"], win, mid)
        self.assertTrue(ch.find_family(self.models, "claude-opus-5[1m]")[2])

    def test_profiles_all_classes(self):
        for pname, pf in self.models["profiles"].items():
            if pname.startswith("_"):
                continue
            for cls in ("1m", "400k", "200k"):
                fr = pf[cls]
                self.assertEqual(len(fr), 4)
                self.assertEqual(fr, sorted(fr))
                self.assertTrue(0 < fr[0] and fr[-1] < 1)


class TestEvaluate(Base):
    def test_bands_1m(self):
        for tokens, band in ((50000, "green"), (199999, "green"), (200000, "watch"), (400000, "caution"), (600000, "warning"), (800000, "critical"), (990000, "critical")):
            ev = ch.evaluate(self.models, self.cfg, tokens, "claude-opus-5", "claude")
            self.assertEqual(ev["band_name"], band, tokens)
        self.assertEqual(ev["harness_window"], 1000000)
        self.assertEqual(ev["thresholds"], [200000, 400000, 600000, 800000])

    def test_compaction_pulls_band_up(self):
        # Copilot caps Opus 5 at 200K and compacts at 80%: 150K is Green for degradation but compaction approaches.
        ev = ch.evaluate(self.models, self.cfg, 150000, "claude-opus-5", "copilot")
        self.assertEqual(ev["harness_window"], 200000)
        self.assertEqual(ev["degradation_band"], 0)
        self.assertEqual(ev["compaction"], 2)  # 75% >= 80% - 5%
        self.assertEqual(ev["band_name"], "warning")
        ev = ch.evaluate(self.models, self.cfg, 132000, "claude-opus-5", "copilot")
        self.assertEqual(ev["compaction"], 1)
        self.assertEqual(ev["band_name"], "caution")

    def test_reported_window_wins(self):
        ev = ch.evaluate(self.models, self.cfg, 150000, "claude-opus-5", "claude", window_hint=200000)
        self.assertEqual(ev["harness_window"], 200000)
        self.assertEqual(ev["harness_window_source"], "reported")

    def test_config_window_override(self):
        cfg = dict(self.cfg)
        cfg["windows"] = {"copilot": 1000000}
        ev = ch.evaluate(self.models, cfg, 150000, "claude-opus-5", "copilot")
        self.assertEqual(ev["harness_window"], 1000000)
        self.assertEqual(ev["band_name"], "green")

    def test_profiles(self):
        cfg = dict(self.cfg)
        cfg["profile"] = "conservative"
        self.assertEqual(ch.evaluate(self.models, cfg, 250000, "claude-opus-5", "claude")["band_name"], "caution")
        cfg["profile"] = "relaxed"
        self.assertEqual(ch.evaluate(self.models, cfg, 250000, "claude-opus-5", "claude")["band_name"], "green")

    def test_codex_cap(self):
        ev = ch.evaluate(self.models, self.cfg, 300000, "gpt-5.5", "codex")
        self.assertEqual(ev["harness_window"], 400000)
        self.assertEqual(ev["native_window"], 1050000)
        self.assertEqual(ev["degradation_band"], 1)  # 300K >= 20% of 1.05M
        self.assertEqual(ev["compaction"], 1)  # 75% of 400K, compact at 90%

    def test_codex_sol_default_cap(self):
        # Codex runs GPT-6 Sol at 272K by default (openai/codex#47805), not the model's 922K input window.
        ev = ch.evaluate(self.models, self.cfg, 200000, "gpt-6-sol", "codex")
        self.assertEqual(ev["harness_window"], 272000)
        self.assertEqual(ev["native_window"], 922000)

    def test_cowork_harness(self):
        p = "C:/Users/x/AppData/Roaming/Claude/local-agent-mode-sessions/a/b/local_c/.claude/projects/d/e.jsonl"
        self.assertEqual(ch.evaluate(self.models, self.cfg, 1000, "claude-fable-5-1", "claude", p)["harness"], "cowork")

    def test_unknown_model_conservative(self):
        ev = ch.evaluate(self.models, self.cfg, 100000, "mystery-9000", "claude")
        self.assertTrue(ev["unknown_model"])
        self.assertEqual(ev["native_window"], 200000)
        self.assertEqual(ev["band_name"], "caution")


class TestParsers(Base):
    def test_claude(self):
        p = self.path("sess.jsonl")
        write(p, claude_lines(257000, sidechain_tokens=900000))
        self.assertEqual(ch.detect_kind(p), "claude")
        m = ch.measure_path(p)
        self.assertEqual(m["tokens"], 257000)
        self.assertEqual(m["model"], "claude-opus-5")
        self.assertFalse(m["estimated"])

    def test_claude_tail_window_on_big_file(self):
        p = self.path("big.jsonl")
        rows = [{"type": "user", "message": {"role": "user", "content": "x" * 5000}} for _ in range(600)]
        rows += claude_lines(410000)
        write(p, rows)
        self.assertGreater(os.path.getsize(p), ch.TAIL_BYTES)
        self.assertEqual(ch.measure_path(p)["tokens"], 410000)

    def test_codex(self):
        p = self.path("rollout-2026-09-02T10-00-00-abc.jsonl")
        write(p, [
            {"timestamp": "t", "type": "session_meta", "payload": {"id": "abc", "cwd": "/x", "cli_version": "0.130.0", "model_provider": "openai"}},
            {"timestamp": "t", "type": "turn_context", "payload": {"model": "gpt-5.5", "cwd": "/x"}},
            {"timestamp": "t", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 900000, "cached_input_tokens": 800000, "output_tokens": 5000, "total_tokens": 905000},
                                                                                              "last_token_usage": {"input_tokens": 310000, "cached_input_tokens": 300000, "output_tokens": 200, "total_tokens": 310200},
                                                                                              "model_context_window": 400000}}},
            {"timestamp": "t", "type": "event_msg", "payload": {"type": "agent_message", "message": "done"}},
        ])
        self.assertEqual(ch.detect_kind(p), "codex")
        m = ch.measure_path(p)
        self.assertEqual(m["tokens"], 310000)
        self.assertEqual(m["model"], "gpt-5.5")
        self.assertEqual(m["window_hint"], 400000)
        ev = ch.evaluate(self.models, self.cfg, m["tokens"], m["model"], "codex", p, m["window_hint"])
        self.assertEqual(ev["harness_window_source"], "reported")
        self.assertEqual(ev["band_name"], "caution")  # 77.5% of 400K, compact at 90% -> approaching

    def test_copilot_usage_event(self):
        p = self.path("events.jsonl")
        write(p, [
            {"type": "session.start", "timestamp": "t", "data": {"version": "1.0.80", "cwd": "/x", "model": "claude-opus-5"}},
            {"type": "user.message", "timestamp": "t", "data": {"content": "hello"}},
            {"type": "assistant.usage", "timestamp": "t", "data": {"inputTokens": 120000, "outputTokens": 300, "cacheReadTokens": 20000, "cacheWriteTokens": 5000}},
            {"type": "assistant.turn_end", "timestamp": "t", "data": {}},
        ])
        self.assertEqual(ch.detect_kind(p), "copilot")
        m = ch.measure_path(p)
        self.assertEqual(m["tokens"], 145000)
        self.assertEqual(m["model"], "claude-opus-5")
        self.assertFalse(m["estimated"])

    def test_copilot_estimate_after_compaction(self):
        p = self.path("events.jsonl")
        write(p, [
            {"type": "session.start", "timestamp": "t", "data": {"model": "gpt-5.5"}},
            {"type": "assistant.message", "timestamp": "t", "data": {"content": "a" * 40000}},
            {"type": "session.compaction_complete", "timestamp": "t", "data": {}},
            {"type": "user.message", "timestamp": "t", "data": {"content": "b" * 8000}},
            {"type": "session.shutdown", "timestamp": "t", "data": {"modelMetrics": {"gpt-5.5": {"usage": {"inputTokens": 999999}}}}},
        ])
        m = ch.measure_path(p)
        self.assertTrue(m["estimated"])
        self.assertEqual(m["tokens"], 2000)  # only text after the compaction, /4; shutdown totals ignored

    def test_generic_estimate(self):
        p = self.path("chat.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps([{"role": "user", "parts": [{"text": "z" * 50000}]}]))
        m = ch.measure_path(p)
        self.assertTrue(m["estimated"])
        self.assertEqual(m["kind"], "size-estimate")
        self.assertGreater(m["tokens"], 9000)


class TestHookAndStatusline(Base):
    def run_cli(self, args, stdin_obj):
        env = dict(os.environ)
        env["CTXHEALTH_HOME"] = ch.CFG_DIR
        r = subprocess.run([sys.executable, os.path.join(SKILL, "ctxhealth.py")] + args, input=json.dumps(stdin_obj).encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.decode("utf-8").strip()

    def test_claude_hook_emits_json_and_throttles(self):
        p = self.path("sess.jsonl")
        write(p, claude_lines(450000, model="claude-fable-5-1"))
        data = {"session_id": "abc", "transcript_path": p, "cwd": "/x", "hook_event_name": "UserPromptSubmit", "prompt": "go"}
        out = self.run_cli(["hook", "--agent", "claude"], data)
        obj = json.loads(out)
        self.assertEqual(obj["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("CAUTION", obj["hookSpecificOutput"]["additionalContext"])
        self.assertIn("fable-5-1", obj["hookSpecificOutput"]["additionalContext"])
        self.assertIn("systemMessage", obj)
        # second call within the cooldown, same band: silent
        self.assertEqual(self.run_cli(["hook", "--agent", "claude"], data), "")
        # band rises: emits again
        write(p, claude_lines(650000, model="claude-fable-5-1"))
        self.assertIn("WARNING", self.run_cli(["hook", "--agent", "claude"], data))

    def test_green_is_silent(self):
        p = self.path("sess.jsonl")
        write(p, claude_lines(50000))
        data = {"session_id": "g", "transcript_path": p, "hook_event_name": "UserPromptSubmit"}
        self.assertEqual(self.run_cli(["hook", "--agent", "claude"], data), "")

    def test_sessionstart_resume_uses_context_tokens(self):
        data = {"session_id": "r", "hook_event_name": "SessionStart", "source": "resume", "model": "claude-opus-5", "context_tokens": 620000}
        out = json.loads(self.run_cli(["hook", "--agent", "claude"], data))
        self.assertIn("WARNING", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_copilot_hook_shape(self):
        base = os.path.join(self.tmp, "copilot")
        os.makedirs(os.path.join(base, "session-state", "sid1"))
        write(os.path.join(base, "session-state", "sid1", "events.jsonl"), [
            {"type": "session.start", "data": {"model": "claude-opus-5"}},
            {"type": "assistant.usage", "data": {"inputTokens": 150000, "outputTokens": 10}},
        ])
        os.environ["COPILOT_HOME"] = base
        try:
            out = json.loads(self.run_cli(["hook", "--agent", "copilot"], {"sessionId": "sid1", "timestamp": 1, "cwd": "/x"}))
        finally:
            del os.environ["COPILOT_HOME"]
        self.assertIn("additionalContext", out)
        self.assertIn("WARNING", out["additionalContext"])  # 75% of Copilot's 200K cap -> compaction imminent

    def test_cursor_precompact_shape(self):
        data = {"conversation_id": "c1", "hook_event_name": "preCompact", "model": "claude-opus-5", "context_tokens": 280000, "context_window_size": 300000, "trigger": "auto"}
        out = json.loads(self.run_cli(["hook", "--agent", "cursor"], data))
        self.assertIn("user_message", out)

    def test_hook_never_fails(self):
        self.assertEqual(self.run_cli(["hook", "--agent", "claude"], {"transcript_path": "/nope/missing.jsonl"}), "")
        r = subprocess.run([sys.executable, os.path.join(SKILL, "ctxhealth.py"), "hook"], input=b"not json", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, b"")

    def test_statusline(self):
        data = {"model": {"id": "claude-opus-5", "display_name": "Opus"}, "workspace": {"current_dir": "/home/m/proj"},
                "context_window": {"context_window_size": 1000000, "used_percentage": 42, "current_usage": {"input_tokens": 20000, "cache_creation_input_tokens": 5000, "cache_read_input_tokens": 395000}}}
        out = self.run_cli(["statusline"], data)
        self.assertIn("opus-5", out)
        self.assertIn("420K/1M", out)
        self.assertIn("CAUTION", out)
        self.assertIn("proj", out)
        out = self.run_cli(["statusline"], {"model": {"id": "claude-opus-5"}, "context_window": {"current_usage": None}})
        self.assertIn("ctx -", out)


class TestInstallDryRun(Base):
    def test_install_dry_run_and_uninstall(self):
        home = os.path.join(self.tmp, "fakehome")
        os.makedirs(os.path.join(home, ".claude"))
        os.makedirs(os.path.join(home, ".copilot"))
        os.makedirs(os.path.join(home, ".codex"))
        os.makedirs(os.path.join(home, ".cursor"))
        os.makedirs(os.path.join(home, ".gemini"))
        with open(os.path.join(home, ".claude", "settings.json"), "w") as f:
            json.dump({"model": "opus", "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "powershell -File context-health.ps1"}]}]}}, f)
        old_home = ch.HOME
        old_eg = ch.EVERGREEN_PATH
        ch.HOME = home
        ch.EVERGREEN_PATH = os.path.join(self.tmp, "evergreen.json")  # never touch the real unit state
        json.dump({"source": "x"}, open(ch.EVERGREEN_PATH, "w"))
        try:
            class A:
                agent = "all"; dry_run = True; no_statusline = False; replace_legacy = False; copy = False
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                ch.cmd_install(A())
            finally:
                sys.stdout = old
            text = buf.getvalue()
            self.assertIn("dry run", text)
            for agent in ("claude", "copilot", "codex", "gemini", "cursor"):
                self.assertIn("%s: would write" % agent, text)
            self.assertIn("legacy", text.lower())
            # nothing written
            self.assertEqual(load(os.path.join(home, ".claude", "settings.json"))["model"], "opus")
            self.assertFalse(os.path.exists(os.path.join(home, ".codex", "hooks.json")))
            # real install into the fake home, then uninstall
            A.dry_run = False; A.replace_legacy = True; A.copy = True
            sys.stdout = buf
            try:
                ch.cmd_install(A())
            finally:
                sys.stdout = old
            s = load(os.path.join(home, ".claude", "settings.json"))
            self.assertIn("ctxhealth.py", json.dumps(s["hooks"]["UserPromptSubmit"]))
            self.assertNotIn("context-health.ps1", json.dumps(s["hooks"]))
            self.assertIn("ctxhealth.py", s["statusLine"]["command"])
            self.assertTrue(os.path.exists(os.path.join(home, ".copilot", "hooks", "context-health.json")))
            self.assertIn("SessionStart", load(os.path.join(home, ".codex", "hooks.json"))["hooks"])
            self.assertIn("BeforeAgent", load(os.path.join(home, ".gemini", "settings.json"))["hooks"])
            self.assertIn("preCompact", load(os.path.join(home, ".cursor", "hooks.json"))["hooks"])
            self.assertTrue(os.path.exists(os.path.join(home, ".agents", "skills", "context-health", "SKILL.md")))
            self.assertTrue(os.path.exists(os.path.join(home, ".claude", "skills", "context-health", "SKILL.md")))
            sys.stdout = buf
            try:
                ch.cmd_uninstall(A())
            finally:
                sys.stdout = old
            s = load(os.path.join(home, ".claude", "settings.json"))
            self.assertNotIn("ctxhealth.py", json.dumps(s))
            self.assertFalse(os.path.exists(os.path.join(home, ".copilot", "hooks", "context-health.json")))
            self.assertEqual(load(ch.EVERGREEN_PATH)["source"], "x")  # tracked unit state is never rewritten with a local path
        finally:
            ch.HOME = old_home
            ch.EVERGREEN_PATH = old_eg


class TestFreshAndPack(Base):
    def test_fresh_and_checked_hand_rule(self):
        egp = os.path.join(self.tmp, "evergreen.json")
        old = ch.EVERGREEN_PATH
        oldm = ch.MODELS_PATH
        ch.EVERGREEN_PATH = egp
        ch.MODELS_PATH = os.path.join(self.tmp, "models.json")
        json.dump({"tier": "fast", "interval_days": 14, "last_checked": "2026-01-01", "next_due": "2026-01-15", "history": []}, open(egp, "w"))
        json.dump({"version": "x"}, open(ch.MODELS_PATH, "w"))
        try:
            class A:
                m = 0.0; note = "quiet"
            buf = io.StringIO(); o = sys.stdout; sys.stdout = buf
            try:
                self.assertEqual(ch.cmd_fresh(A()), 1)  # past due
                ch.cmd_checked(A())
            finally:
                sys.stdout = o
            eg = load(egp)
            self.assertEqual(eg["interval_days"], 21)  # 14 * 1.5 = 21, clamped to fast max 21
            self.assertEqual(eg["last_checked"], ch.today())
            A.m = 0.7
            sys.stdout = buf
            try:
                ch.cmd_checked(A())
            finally:
                sys.stdout = o
            self.assertEqual(load(egp)["interval_days"], 5.25)
            self.assertEqual(load(ch.MODELS_PATH)["last_checked"], ch.today())
        finally:
            ch.EVERGREEN_PATH = old
            ch.MODELS_PATH = oldm

    def test_pack(self):
        out = os.path.join(self.tmp, "out")
        class A:
            pass
        A.out = out
        buf = io.StringIO(); o = sys.stdout; sys.stdout = buf
        try:
            self.assertEqual(ch.cmd_pack(A()), 0)
        finally:
            sys.stdout = o
        zips = [f for f in os.listdir(out) if f.endswith(".zip")]
        self.assertEqual(len(zips), 1)
        import zipfile
        names = zipfile.ZipFile(os.path.join(out, zips[0])).namelist()
        self.assertIn("INSTALL.txt", names)
        self.assertTrue(any(n.endswith("skills/context-health/ctxhealth.py") for n in names))
        self.assertTrue(any(n.endswith("skills/context-health/SKILL.md") for n in names))
        for n in names:
            self.assertNotIn(os.path.splitext(n)[1].lower(), ch.MAIL_BLOCKED, n)
            self.assertNotIn("__pycache__", n)


class TestReviewRegressions(Base):
    """Regressions from the 2026-09-02 independent review (see CHANGELOG C-20260902-2)."""

    def test_copilot_compaction_newest_means_empty_context(self):
        p = self.path("events.jsonl")
        write(p, [
            {"type": "session.start", "data": {"model": "gpt-5.5"}},
            {"type": "assistant.message", "data": {"content": "a" * 200000}},
            {"type": "session.compaction_complete", "data": {}},
        ])
        m = ch.measure_path(p)
        self.assertTrue(m["estimated"])
        self.assertLessEqual(m["tokens"], 1)

    def test_throttle_only_escalation_bypasses_cooldown(self):
        cfg = dict(self.cfg)
        emitted = [ch.should_emit("claude", "osc", b, cfg) for b in (2, 1, 2, 1, 2, 3)]
        self.assertEqual(emitted, [True, False, False, False, False, True])

    def test_config_validation(self):
        class A:
            op = "set"; key = "profile"; value = "bogus"
        self.assertEqual(ch.cmd_config(A()), 2)
        A.key = "windows.copilot"; A.value = "abc"
        self.assertEqual(ch.cmd_config(A()), 2)
        A.key = "windows.nowhere"; A.value = "1000"
        self.assertEqual(ch.cmd_config(A()), 2)
        A.key = "profile.sub"; A.value = "3"
        self.assertEqual(ch.cmd_config(A()), 2)
        A.key = "windows.copilot"; A.value = "1000000"
        self.assertEqual(ch.cmd_config(A()), 0)
        A.key = "profile"; A.value = "relaxed"
        self.assertEqual(ch.cmd_config(A()), 0)
        cfg = ch.load_cfg()
        self.assertEqual(cfg["windows"]["copilot"], 1000000)
        self.assertEqual(cfg["profile"], "relaxed")
        # a bad profile smuggled into the file falls back to balanced without crashing
        cfg["profile"] = "bogus"; cfg["windows"] = {"copilot": "abc"}
        ev = ch.evaluate(self.models, cfg, 150000, "claude-opus-5", "copilot")
        self.assertEqual(ev["profile"], "balanced")
        self.assertEqual(ev["harness_window"], 200000)

    def test_install_refuses_unparseable_config(self):
        home = os.path.join(self.tmp, "h")
        os.makedirs(os.path.join(home, ".gemini"))
        raw = '{\n  // comment\n  "theme": "dark", "mcpServers": {"x": {}}\n}\n'
        with open(os.path.join(home, ".gemini", "settings.json"), "w") as f:
            f.write(raw)
        old_home, old_eg = ch.HOME, ch.EVERGREEN_PATH
        ch.HOME = home
        ch.EVERGREEN_PATH = os.path.join(self.tmp, "eg.json")
        try:
            class A:
                agent = "gemini"; dry_run = False; no_statusline = True; replace_legacy = False; copy = True
            buf = io.StringIO(); o = sys.stdout; sys.stdout = buf
            try:
                ch.cmd_install(A())
            finally:
                sys.stdout = o
            self.assertIn("SKIPPED", buf.getvalue())
            with open(os.path.join(home, ".gemini", "settings.json")) as f:
                self.assertEqual(f.read(), raw)
            # uninstall of a single agent must not create files or drop the shared links
            os.makedirs(os.path.join(home, ".agents", "skills", "context-health"), exist_ok=True)
            with open(os.path.join(home, ".agents", "skills", "context-health", "ctxhealth.py"), "w") as f:
                f.write("#")
            class U:
                agent = "cursor"
            sys.stdout = buf
            try:
                ch.cmd_uninstall(U())
            finally:
                sys.stdout = o
            self.assertFalse(os.path.exists(os.path.join(home, ".cursor", "hooks.json")))
            self.assertTrue(os.path.exists(os.path.join(home, ".agents", "skills", "context-health")))
        finally:
            ch.HOME, ch.EVERGREEN_PATH = old_home, old_eg

    def test_link_dir_replaces_stale_copy_but_not_foreign_dir(self):
        src = SKILL
        stale = os.path.join(self.tmp, "stale")
        os.makedirs(stale)
        with open(os.path.join(stale, "ctxhealth.py"), "w") as f:
            f.write("old")
        msg = ch._link_dir(src, stale, copy=True)
        self.assertIn("copied", msg)
        with open(os.path.join(stale, "ctxhealth.py")) as f:
            self.assertNotEqual(f.read(), "old")
        self.assertIn("copied", ch._link_dir(src, stale, copy=True))  # second run must not raise
        foreign = os.path.join(self.tmp, "foreign")
        os.makedirs(foreign)
        with open(os.path.join(foreign, "SKILL.md"), "w") as f:
            f.write("someone else's skill")
        self.assertIn("not ours", ch._link_dir(src, foreign, copy=True))

    def test_hook_harness_follows_transcript_kind(self):
        p = self.path("events.jsonl")
        write(p, [{"type": "session.start", "data": {"model": "claude-opus-5"}},
                  {"type": "assistant.usage", "data": {"inputTokens": 150000}}])
        env = dict(os.environ); env["CTXHEALTH_HOME"] = ch.CFG_DIR
        r = subprocess.run([sys.executable, os.path.join(SKILL, "ctxhealth.py"), "hook", "--agent", "vscode"],
                           input=json.dumps({"session_id": "vs1", "transcript_path": p, "hook_event_name": "UserPromptSubmit"}).encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30)
        out = json.loads(r.stdout.decode())
        self.assertIn("copilot window", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("WARNING", out["hookSpecificOutput"]["additionalContext"])

    def test_sniff_missing_and_small_k(self):
        class A:
            file = os.path.join(self.tmp, "nope.jsonl")
        buf = io.StringIO(); o = sys.stdout; sys.stdout = buf
        try:
            self.assertEqual(ch.cmd_sniff(A()), 1)
        finally:
            sys.stdout = o
        self.assertEqual(ch.k(412), "412")
        self.assertEqual(ch.k(1500), "2K")


class TestBaseline(Base):
    """Startup (initial) context: first-turn measurement, per-platform records, warn/audit policy."""

    def run_cli(self, args, stdin_obj, entrypoint=None):
        env = dict(os.environ)
        env["CTXHEALTH_HOME"] = ch.CFG_DIR
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        if entrypoint:
            env["CLAUDE_CODE_ENTRYPOINT"] = entrypoint
        r = subprocess.run([sys.executable, os.path.join(SKILL, "ctxhealth.py")] + args, input=json.dumps(stdin_obj).encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.decode("utf-8").strip()

    @staticmethod
    def rows(startup, later=None, model="claude-fable-5-1", prompt_chars=4000):
        def usage(t):
            return {"input_tokens": 1000, "cache_read_input_tokens": t - 3000, "cache_creation_input_tokens": 2000, "output_tokens": 50}
        first = startup + prompt_chars // 4
        out = [
            {"type": "user", "isSidechain": False, "message": {"role": "user", "content": "x" * prompt_chars}},
            {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "model": model, "usage": usage(first), "content": []}},
        ]
        if later:
            out += [
                {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [{"type": "text", "text": "more"}]}},
                {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "model": model, "usage": usage(later), "content": []}},
            ]
        return out

    def test_first_turn_subtracts_prompt_and_ignores_later_turns(self):
        p = self.path("s.jsonl")
        write(p, self.rows(60000, later=500000))
        m = ch.measure_first(p, "claude")
        self.assertEqual(m["tokens"], 61000)
        self.assertEqual(m["prompt_tokens_est"], 1000)
        self.assertEqual(m["startup"], 60000)
        self.assertEqual(ch.parse_claude(p)["tokens"], 500000)  # live measurement still reads the tail
        write(self.path("u.jsonl"), [{"type": "user", "message": {"role": "user", "content": "hi"}}])
        self.assertIsNone(ch.measure_first(self.path("u.jsonl"), "claude"))  # no assistant turn yet

    def test_platform_detection(self):
        old = os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)
        try:
            self.assertEqual(ch.platform_for("claude", "/h/.claude/projects/x/a.jsonl", "claude-jsonl"), "claude-cli")
            os.environ["CLAUDE_CODE_ENTRYPOINT"] = "claude-vscode"
            self.assertEqual(ch.platform_for("claude", "/h/.claude/projects/x/a.jsonl", "claude-jsonl"), "claude-vscode")
            self.assertEqual(ch.platform_for("claude", "C:/u/AppData/Roaming/Claude/local-agent-mode-sessions/w/s/local_1/.claude/projects/p/a.jsonl"), "cowork")
            self.assertEqual(ch.platform_for("copilot", None, "copilot-events"), "copilot-cli")
            self.assertEqual(ch.platform_for("claude", "/x/events.jsonl", "copilot-events"), "copilot-vscode")
            self.assertEqual(ch.platform_for("vscode", "/x/rollout.jsonl", "codex-jsonl"), "codex")
            self.assertEqual(ch.platform_for("cursor"), "cursor")
        finally:
            os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)
            if old is not None:
                os.environ["CLAUDE_CODE_ENTRYPOINT"] = old

    def test_bands(self):
        def band(startup, model, harness="claude"):
            return ch.evaluate_baseline(self.models, self.cfg, startup, model, harness)["band_name"]
        self.assertEqual(band(50000, "claude-fable-5-1"), "ok")
        self.assertEqual(band(150000, "claude-fable-5-1"), "notable")
        self.assertEqual(band(250000, "claude-fable-5-1"), "high")
        self.assertEqual(band(350000, "claude-fable-5-1"), "excessive")
        self.assertEqual(band(20000, "claude-haiku-4-5"), "ok")
        self.assertEqual(band(30000, "claude-haiku-4-5"), "notable")
        self.assertEqual(band(45000, "claude-haiku-4-5"), "high")
        self.assertEqual(band(150000, "claude-fable-5-1", "copilot"), "excessive")  # 200K copilot cap
        ev = ch.evaluate_baseline(self.models, self.cfg, 45000, "claude-fable-5-1", "claude", prior=[30000, 31000, 29000])
        self.assertTrue(ev["grew"])
        ev = ch.evaluate_baseline(self.models, self.cfg, 33000, "claude-fable-5-1", "claude", prior=[30000, 31000, 29000])
        self.assertFalse(ev["grew"])

    def test_hook_records_warns_and_audits_on_high(self):
        p = self.path("s.jsonl")
        write(p, self.rows(250000))
        data = {"session_id": "b1", "transcript_path": p, "cwd": "/proj", "hook_event_name": "UserPromptSubmit"}
        out = json.loads(self.run_cli(["hook", "--agent", "claude"], data))
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[context-health baseline]", ctx)
        self.assertIn("HIGH", ctx)
        self.assertIn("baseline audit", ctx)
        self.assertIn("INVENTORY-claude-cli.md", ctx)
        self.assertIn("startup context", out["systemMessage"])
        hist = ch.baseline_history("claude-cli")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["band"], "high")
        self.assertEqual(hist[0]["startup"], 250000)
        self.assertTrue(hist[0]["audited"] and hist[0]["warned"])
        meta = load(ch._bl_paths("claude-cli")[1])
        self.assertEqual(meta["sessions"], 1)
        self.assertEqual(meta["last_audit_session"], 1)
        # same session again: live WATCH line is in cooldown and the baseline is done -> silent
        self.assertEqual(self.run_cli(["hook", "--agent", "claude"], data), "")
        self.assertEqual(len(ch.baseline_history("claude-cli")), 1)
        # platform follows the entrypoint env var
        write(self.path("v.jsonl"), self.rows(30000))
        self.run_cli(["hook", "--agent", "claude"], {"session_id": "v1", "transcript_path": self.path("v.jsonl"), "cwd": "/proj", "hook_event_name": "UserPromptSubmit"}, entrypoint="claude-vscode")
        self.assertEqual(len(ch.baseline_history("claude-vscode")), 1)

    def test_audit_every_n_is_otherwise_silent(self):
        ch.write_json(ch.CFG_PATH, {"baseline": {"audit_every": 3}})
        outs = []
        for i in range(4):
            p = self.path("s%d.jsonl" % i)
            write(p, self.rows(30000))
            outs.append(self.run_cli(["hook", "--agent", "claude"], {"session_id": "n%d" % i, "transcript_path": p, "cwd": "/proj", "hook_event_name": "UserPromptSubmit"}))
        self.assertEqual(outs[0], "")
        self.assertEqual(outs[1], "")
        obj = json.loads(outs[2])
        self.assertIn("baseline audit, session 3 of every 3", obj["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Do not mention this to the user", obj["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("systemMessage", obj)
        self.assertEqual(outs[3], "")
        meta = load(ch._bl_paths("claude-cli")[1])
        self.assertEqual((meta["sessions"], meta["last_audit_session"]), (4, 3))
        self.assertEqual(len(ch.baseline_history("claude-cli")), 4)

    def test_growth_against_project_median_warns(self):
        for i in range(4):
            ch.baseline_record("claude-cli", {"date": "2026-09-01", "session": "old%d" % i, "project": "/proj", "platform": "claude-cli", "startup": 30000, "band": "ok"})
        ch.baseline_record("claude-cli", {"date": "2026-09-01", "session": "other", "project": "/other", "platform": "claude-cli", "startup": 90000, "band": "ok"})
        p = self.path("s.jsonl")
        write(p, self.rows(45000))
        out = json.loads(self.run_cli(["hook", "--agent", "claude"], {"session_id": "g1", "transcript_path": p, "cwd": "/proj", "hook_event_name": "UserPromptSubmit"}))
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("up from a median of ~30K", ctx)
        self.assertIn("up from ~30K", out["systemMessage"])
        self.assertNotIn("baseline audit", ctx)  # grew but band OK: warn, no audit
        # a session already in the history is not recorded twice
        out2 = self.run_cli(["hook", "--agent", "claude"], {"session_id": "old1", "transcript_path": p, "cwd": "/proj", "hook_event_name": "UserPromptSubmit"})
        self.assertEqual(out2, "")
        self.assertEqual(len(ch.baseline_history("claude-cli")), 6)

    def test_state_keeps_baseline_done_across_live_emits(self):
        sp = ch.state_path("claude", "keep")
        ch.write_json(sp, {"band": 0, "t": 0, "n": 0, "baseline_done": True})
        self.assertTrue(ch.should_emit("claude", "keep", 2, self.cfg))
        self.assertTrue(load(sp)["baseline_done"])

    def test_disabled_and_config_keys(self):
        ch.write_json(ch.CFG_PATH, {"baseline": {"enabled": False}})
        p = self.path("s.jsonl")
        write(p, self.rows(250000))
        out = json.loads(self.run_cli(["hook", "--agent", "claude"], {"session_id": "d1", "transcript_path": p, "cwd": "/proj", "hook_event_name": "UserPromptSubmit"}))
        self.assertNotIn("baseline", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(ch.baseline_history("claude-cli"), [])

        class A:
            op = "set"
            key = value = None
        buf = io.StringIO(); o = sys.stdout; sys.stdout = buf
        try:
            for key, val, rc in (("baseline.audit_every", "0", 2), ("baseline.min_band", "watch", 2), ("baseline.min_band", "high", 0),
                                 ("baseline.audit_every", "5", 0), ("baseline.jump", "0.5", 0), ("baseline.enabled", "true", 0), ("baseline.nope", "1", 2)):
                A.key, A.value = key, val
                self.assertEqual(ch.cmd_config(A()), rc, (key, val, buf.getvalue()))
        finally:
            sys.stdout = o
        cfg = load(ch.CFG_PATH)
        self.assertEqual((cfg["baseline"]["min_band"], cfg["baseline"]["audit_every"], cfg["baseline"]["jump"], cfg["baseline"]["enabled"]), ("high", 5, 0.5, True))

    def test_baseline_command_and_status_line(self):
        p = self.path("s.jsonl")
        write(p, self.rows(120000, later=300000))

        class A:
            file = p; agent = "auto"; model = None; platform = None; history = 0; json = False
        buf = io.StringIO(); o = sys.stdout; sys.stdout = buf
        try:
            self.assertEqual(ch.cmd_baseline(A()), 0)
            A.file = None
            self.assertEqual(ch.cmd_baseline(A()), 0)

            class S:
                file = p; agent = "claude"; model = None; json = False
            self.assertEqual(ch.cmd_status(S()), 0)
        finally:
            sys.stdout = o
        text = buf.getvalue()
        self.assertIn("startup: ~120K tokens before the first prompt", text)
        self.assertIn("NOTABLE", text)
        self.assertIn("no startup baselines recorded yet", text)
        self.assertIn("context: ~300K", text)


def skill(root, name, desc):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: %s\ndescription: %s\n---\n# %s\n" % (name, desc, name))


SCAN = "Collect articles from news feeds about databases and storage engines, summarise each article into notes, tag topics, track trends and harvest reader comments"


class TestSelection(Base):
    def setUp(self):
        Base.setUp(self)
        self.sh = os.environ["CTXHEALTH_SKILLS_HOME"]
        self.user = os.path.join(self.sh, ".claude", "skills")
        self.agents = os.path.join(self.sh, ".agents", "skills")

    def run_hook(self, sid, cwd="/proj"):
        p = self.path("%s.jsonl" % sid)
        write(p, claude_lines(30000))
        r = subprocess.run([sys.executable, os.path.join(SKILL, "ctxhealth.py"), "hook", "--agent", "claude"],
                           input=json.dumps({"session_id": sid, "transcript_path": p, "cwd": cwd, "hook_event_name": "UserPromptSubmit"}).encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ), timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.decode("utf-8").strip()

    def test_overlap_mirror_clash_and_family(self):
        skill(self.user, "feed-scan", SCAN)
        skill(self.user, "radar-sweep", SCAN + " daily")
        skill(self.user, "feed-ask", SCAN + " and ask")  # a sibling: same-family pairs are the documented risk, so they count
        skill(self.user, "painter", "Generate images, sprites and textures with a local diffusion server for game assets")
        skill(self.agents, "painter", "Generate images, sprites and textures with a local diffusion server for game assets")  # mirror
        skill(self.agents, "feed-scan", "An older, different description of the scanner")  # clash
        ev = ch.evaluate_selection(self.models, self.cfg, None)
        self.assertEqual(ev["count"], 5)
        self.assertEqual(ev["clashes"], ["feed-scan"])
        pairs = [(a, b) for _, a, b in ev["overlaps"]]
        self.assertIn(("feed-scan", "radar-sweep"), pairs)
        self.assertIn(("feed-ask", "radar-sweep"), pairs)
        self.assertIn(("feed-ask", "feed-scan"), pairs)
        self.assertTrue(all(sc >= 0.65 for sc, _, _ in ev["near_duplicates"]) and ev["near_duplicates"])
        self.assertFalse(any("painter" in p for p in pairs))
        claude = ch.evaluate_selection(self.models, self.cfg, None, agent="claude")  # Claude Code skips ~/.agents
        self.assertEqual((claude["count"], claude["clashes"]), (4, []))
        text = "\n".join(ch.describe_selection(self.models, self.cfg, ev))
        self.assertIn("similar descriptions", text)
        self.assertIn("same name, different descriptions", text)
        skill(self.user, "tiny", "Helps with documents")
        skill(self.user, "huge", "Handles ledgers. " * 70)
        ev = ch.evaluate_selection(self.models, self.cfg, None, agent="claude")
        self.assertEqual((ev["vague"], ev["over_spec"]), (["tiny"], ["huge"]))

    def test_installed_plugins_scope_and_disable(self):
        cache = os.path.join(self.sh, ".claude", "plugins", "cache", "mk")
        for plug in ("alpha", "beta", "gamma"):
            skill(os.path.join(cache, plug, "1.0", "skills"), plug + "-one", "Does %s things" % plug)
        ch.write_json(os.path.join(self.sh, ".claude", "plugins", "installed_plugins.json"), {"version": 2, "plugins": {
            "alpha@mk": [{"scope": "user", "installPath": os.path.join(cache, "alpha", "1.0")}],
            "beta@mk": [{"scope": "project", "projectPath": self.path("proj"), "installPath": os.path.join(cache, "beta", "1.0")}],
            "gamma@mk": [{"scope": "user", "installPath": os.path.join(cache, "gamma", "1.0")}]}})
        ch.write_json(os.path.join(self.sh, ".claude", "settings.json"), {"enabledPlugins": {"gamma@mk": False}})

        def names(proj):
            return sorted(s["name"] for s in ch.scan_skills(proj, "claude"))
        self.assertEqual(names(None), ["alpha-one"])
        self.assertEqual(names(os.path.join(self.path("proj"), "sub")), ["alpha-one", "beta-one"])
        self.assertEqual(ch.scan_skills(None, "claude")[0]["plugin"], "alpha")

    def test_hook_checks_every_n_sessions_and_does_not_repeat(self):
        ch.write_json(ch.CFG_PATH, {"selection": {"check_every": 3}})
        skill(self.user, "feed-scan", SCAN)
        skill(self.user, "radar-sweep", SCAN + " daily")
        outs = [self.run_hook("q%d" % i) for i in range(5)]
        obj = json.loads(outs[0])  # the first session checks
        self.assertIn("[context-health selection]", obj["hookSpecificOutput"]["additionalContext"])
        self.assertIn("feed-scan ~ radar-sweep", obj["hookSpecificOutput"]["additionalContext"])
        self.assertIn("near-duplicate", obj["hookSpecificOutput"]["additionalContext"])
        self.assertIn("skill catalog check", obj["systemMessage"])
        self.assertEqual(outs[1:3], ["", ""])  # not due
        self.assertEqual(outs[3], "")  # due, but the same findings were already reported this week
        self.assertEqual(outs[4], "")
        meta = load(os.path.join(ch.CFG_DIR, "selection.json"))
        self.assertEqual((meta["sessions"], meta["last_check_session"]), (5, 4))
        self.assertEqual(self.run_hook("q0"), "")  # same session again: done
        skill(self.user, "radar-report", SCAN + " weekly")  # new findings surface at the next due session
        outs = [self.run_hook("r%d" % i) for i in range(2)]  # sessions 6 and 7; 7 is due (last check 4, every 3)
        self.assertEqual(outs[0], "")
        self.assertIn("radar-report", json.loads(outs[1])["hookSpecificOutput"]["additionalContext"])

    def test_clean_catalog_and_disabled_are_silent(self):
        skill(self.user, "painter", "Generate images, sprites and textures with a local diffusion server for game assets")
        self.assertEqual(self.run_hook("c1"), "")
        self.assertEqual(load(os.path.join(ch.CFG_DIR, "selection.json"))["last_check_session"], 1)
        ch.write_json(ch.CFG_PATH, {"selection": {"enabled": False}})
        skill(self.user, "feed-scan", SCAN)
        skill(self.user, "radar-sweep", SCAN + " daily")
        self.assertEqual(self.run_hook("c2"), "")

        class A:
            op = "set"
            key = value = None
        buf = io.StringIO(); o = sys.stdout; sys.stdout = buf
        try:
            for key, val, rc in (("selection.check_every", "0", 2), ("selection.overlap", "1.5", 2), ("selection.overlap", "0.25", 0),
                                 ("selection.check_every", "4", 0), ("selection.nope", "1", 2)):
                A.key, A.value = key, val
                self.assertEqual(ch.cmd_config(A()), rc, (key, val, buf.getvalue()))
        finally:
            sys.stdout = o


if __name__ == "__main__":
    unittest.main(verbosity=2)
