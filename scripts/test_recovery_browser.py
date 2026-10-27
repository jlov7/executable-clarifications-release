"""HTTP regressions for supplied-example onboarding and local review recovery."""
import argparse
import copy
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from executable_clarifications.session import Session, render_contract


def run(only=None):
    root = Path(__file__).resolve().parents[1]
    out = Path(os.environ.get("BROWSER_EVIDENCE_DIR", root / ".release-scratch/recovery-browser"))
    out.mkdir(parents=True, exist_ok=True)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(root / "web")))
    def lifecycle(event):
        with (out / "servers.jsonl").open("a") as stream:
            stream.write(json.dumps({"event": event, "pid": os.getpid(), "host": "127.0.0.1",
                                         "port": server.server_port, "script": Path(__file__).name}) + "\n")
    lifecycle("bound")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors, external, checks = [], [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("CHROMIUM_PATH"))
            try:
                for width, height in [(1280, 900), (390, 844)]:
                    context = browser.new_context(accept_downloads=True, viewport={"width": width, "height": height})
                    prefix = f"http://127.0.0.1:{server.server_port}/"
                    context.route("**/*", lambda r, _request, prefix=prefix: r.continue_() if r.request.url.startswith(prefix)
                                  else (external.append(r.request.url), r.abort()))
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
                    def upload(data, page=page):
                        page.set_input_files("#policy-file", {"name": "saved.json", "mimeType": "application/json",
                                                                 "buffer": json.dumps(data).encode()})
                    def record(page=page):
                        return json.loads(page.locator("#record").text_content())
                    def download(selector, name, page=page, width=width):
                        with page.expect_download() as event:
                            page.click(selector)
                        path = out / f"{width}-{name}"
                        event.value.save_as(path)
                        return path.read_text()
                    def cancel_reload(page=page):
                        seen = []
                        def dismiss(dialog):
                            seen.append(dialog.type)
                            dialog.dismiss()
                        page.once("dialog", dismiss)
                        with page.expect_event("dialog", timeout=2500):
                            page.evaluate("location.reload()")
                        assert seen == ["beforeunload"]
                    try:
                        page.goto(prefix + "session.html")
                        assert page.title() == "Executable Clarifications: adaptive sessions"
                        assert page.locator("h1").is_visible()
                        if only in (None, "builtin"):
                            page.click("#answer-true")
                            original = record()
                            saved = download("#download-record", "builtin.json")
                            page.reload()
                            upload(json.loads(saved))
                            expect(page.locator("#import-status")).to_contain_text("Imported locally:")
                            assert record() == original
                            assert download("#download-test", "builtin.py") == render_contract(Session.from_record(original), "implementation:decide")
                            # All trusted finite snapshots, including neither and empty roots.
                            snapshots = page.evaluate("window.CLARIFICATION_CASES.flatMap(c=>Object.values(c.nodes).map(n=>n.record))")
                            for snapshot in snapshots:
                                upload(snapshot)
                                page.wait_for_function("expected=>window.PolicyEngine.canonical(JSON.parse(document.querySelector('#record').textContent))===window.PolicyEngine.canonical(expected)", arg=snapshot)
                                expect(page.locator("#import-status")).to_contain_text("Imported locally:")
                                assert record() == snapshot
                            last = record()
                            changed = copy.deepcopy(last);changed["scope"] = "invented"
                            upload(changed)
                            expect(page.locator("#import-status")).to_contain_text("Import rejected:")
                            assert record() == last
                            unknown = copy.deepcopy(snapshots[0]);unknown["domain"] = [1234]
                            upload(unknown)
                            expect(page.locator("#import-status")).to_contain_text("CLI")
                            assert record() == last
                            # Undo must restore the prior imported tree node, not another scenario.
                            upload(original)
                            page.click("#undo")
                            assert record()["decisions"] == []
                            download("#download-record", "builtin-undone.json")
                            checks.append(f"{width}: all 30 built-in snapshots resume; exact contract, undo, tamper/unsupported-grid recovery")
                        if only in (None, "unsaved"):
                            page.goto(prefix + "session.html")
                            page.click("#open-editor")
                            page.click("#add-candidate")
                            assert page.evaluate("() => {const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}"), "button-only policy edit has no unload protection"
                            cancel_reload()
                            assert page.locator("#editor-candidates > fieldset").count() == 3
                            page.click("#cancel-policy-edit")
                            page.focus("#answer-true");page.keyboard.press("Enter")
                            before = record()
                            assert page.evaluate("() => {const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;}"), "answered work has no unload protection"
                            assert "true" in page.locator("#answer-true").get_attribute("aria-label").lower()
                            assert "<" in page.locator("#answer-true").get_attribute("aria-label")
                            expect(page.locator("#save-status")).to_contain_text("Unsaved")
                            cancel_reload()
                            assert record() == before
                            seen = []
                            def dismiss_reset(dialog, seen=seen):
                                seen.append(dialog.type)
                                dialog.dismiss()
                            page.once("dialog", dismiss_reset)
                            page.click("#reset")
                            assert seen == ["confirm"]
                            assert record() == before
                            page.click("#open-editor")
                            seen = []
                            def dismiss_apply(dialog, seen=seen):
                                seen.append(dialog.type)
                                dialog.dismiss()
                            page.once("dialog", dismiss_apply)
                            page.click("#apply-policy")
                            assert seen == ["confirm"], "unsaved integer review was replaced without confirmation"
                            assert record() == before
                            page.click("#cancel-policy-edit")
                            replacement = page.evaluate("window.CLARIFICATION_CASES[1].nodes.root.record")
                            def dismiss_import(dialog):
                                dialog.dismiss()
                            page.once("dialog", dismiss_import)
                            with page.expect_event("dialog"):
                                upload(replacement)
                            assert record() == before
                            expect(page.locator("#policy-file")).to_have_value("")
                            page.click("#open-editor")
                            page.locator("#editor-fields > fieldset").first.get_by_label("Name", exact=True).fill("pending")
                            page.once("dialog", lambda dialog: dialog.accept())
                            page.click("#reset")
                            expect(page.locator("#policy-editor")).to_be_hidden()
                            assert record()["decisions"] == []
                            page.click("#answer-true")
                            before = record()
                            page.click("#start-examples")
                            name = page.locator("#examples-fields > fieldset").first.get_by_label("Name", exact=True)
                            name.focus();page.keyboard.press("ControlOrMeta+A");page.keyboard.type("toString")
                            # Input stays focused and uncommitted when reload is cancelled.
                            cancel_reload()
                            assert name.input_value() == "toString"
                            download("#download-record", "policy-only.json")
                            expect(page.locator("#save-status")).to_contain_text("Unsaved")
                            cancel_reload()
                            assert record() == before
                            assert page.locator("#examples-fields > fieldset").first.get_by_label("Name", exact=True).input_value() == "toString"
                            page.click("#examples-cancel")
                            expect(page.locator("#save-status")).not_to_contain_text("Unsaved")
                            page.reload()
                            checks.append(f"{width}: keyboard rule names; cancel real reload/reset; focused draft retained; one download does not save other app")
                        if only in (None, "sample"):
                            page.goto(prefix + "session.html")
                            assert page.locator("#try-examples").count() == 1, "supplied example starting path missing"
                            page.focus("#try-examples");page.keyboard.press("Enter")
                            expect(page.locator("#examples-confirm")).to_be_enabled()
                            assert page.locator("#examples-preview article").count() == 5
                            assert page.locator("#examples-review-title").evaluate("(n)=>n===document.activeElement")
                            expect(page.locator("#examples-export")).to_be_disabled()
                            page.click("#examples-confirm")
                            reviewed = json.loads(download("#examples-save", "sample-review.json"))
                            assert reviewed["confirmed"] is True
                            assert reviewed["example_set"] == json.loads((root/"tests/fixtures/known_examples.json").read_text())
                            expect(page.locator("#save-status")).not_to_contain_text("Unsaved")
                            page.locator("#examples-panel").screenshot(path=str(out/f"{width}-known-examples.png"))
                            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                            page.click("#examples-edit")
                            draft_name = page.locator("#examples-fields > fieldset").first.get_by_label("Name", exact=True)
                            draft_name.fill("draft_channel");draft_name.press("Tab")
                            seen = []
                            def dismiss_sample(dialog, seen=seen):
                                seen.append(dialog.type);dialog.dismiss()
                            page.once("dialog", dismiss_sample)
                            page.click("#try-examples")
                            assert seen == ["confirm"], "sample silently replaced an edited example draft"
                            expect(page.locator("#examples-editor")).to_be_visible()
                            assert page.locator("#examples-fields > fieldset").first.get_by_label("Name", exact=True).input_value() == "draft_channel"
                            page.click("#examples-cancel")
                            checks.append(f"{width}: keyboard supplied example start, explicit confirm/save, cancel draft replacement and no overflow")
                        if only in (None, "originals"):
                            page.goto(prefix + "session.html")
                            policy = {"schema":"executable-clarifications/policy-v1","fields":{"x":"integer"},
                                      "candidates":[{"id":"inclusive","rule":{"field":"x","op":"<=","value":10}},
                                                    {"id":"exclusive","rule":{"field":"x","op":"<","value":10}}],
                                      "cases":[{"id":"boundary","input":{"x":10}}]}
                            upload(policy)
                            expect(page.locator("#import-status")).to_contain_text("Imported locally:")
                            page.click("#answer-true");original=record()
                            page.click("#open-editor")
                            value=page.locator("#editor-candidates > fieldset").first.get_by_label("Value",exact=True)
                            value.fill("11");value.press("Tab");page.click("#apply-policy")
                            expect(page.locator("#start-revision")).to_be_visible()
                            page.click("#start-revision")
                            page.click("#open-editor");page.click("#cancel-policy-edit")
                            expect(page.locator("#download-original")).to_be_visible()
                            page.click("#open-editor")
                            value=page.locator("#editor-candidates > fieldset").first.get_by_label("Value",exact=True)
                            value.fill("12");value.press("Tab")
                            seen = []
                            def dismiss_original(dialog, seen=seen):
                                seen.append(dialog.type);dialog.dismiss()
                            page.once("dialog",dismiss_original);page.click("#apply-policy")
                            assert seen == ["confirm"], "new revision silently replaced an unsaved original"
                            page.click("#cancel-policy-edit")
                            download("#download-record","active-revision.json")
                            expect(page.locator("#save-status")).to_contain_text("Unsaved")
                            cancel_reload()
                            assert json.loads(download("#download-original","retained-original.json")) == original
                            expect(page.locator("#save-status")).not_to_contain_text("Unsaved")
                            page.goto(prefix + "session.html")
                            page.click("#try-examples");expect(page.locator("#examples-confirm")).to_be_enabled()
                            page.click("#examples-confirm")
                            example_a=json.loads(page.locator("#examples-record").text_content())
                            page.click("#examples-edit")
                            page.locator("#examples-cases > fieldset").first.get_by_label("Expected boolean",exact=True).select_option("false")
                            page.click("#examples-review");expect(page.locator("#examples-confirm")).to_be_enabled()
                            page.click("#examples-confirm")
                            example_b=json.loads(download("#examples-save","revised-examples.json"))
                            assert example_b != example_a
                            expect(page.locator("#save-status")).to_contain_text("Unsaved")
                            cancel_reload()
                            assert json.loads(download("#examples-original","retained-example-original.json")) == example_a
                            expect(page.locator("#save-status")).not_to_contain_text("Unsaved")
                            checks.append(f"{width}: cancelling editor retains original policy; replacing it asks; revised example download retains unsaved-original protection")
                        if only in (None, "interleavings"):
                            page.goto(prefix + "session.html")
                            policy = {"schema":"executable-clarifications/policy-v1","fields":{"x":"integer"},
                                      "candidates":[{"id":"inclusive","rule":{"field":"x","op":"<=","value":10}},
                                                    {"id":"exclusive","rule":{"field":"x","op":"<","value":10}}],
                                      "cases":[{"id":"boundary","input":{"x":10}},{"id":"extra","input":{"x":5}}]}
                            upload(policy)
                            expect(page.locator("#import-status")).to_contain_text("Imported locally:")
                            page.click("#answer-true");page.click("#open-editor")
                            value=page.locator("#editor-candidates > fieldset").first.get_by_label("Value",exact=True)
                            value.fill("11");value.press("Tab");page.click("#apply-policy")
                            expect(page.locator("#start-revision")).to_be_visible()
                            page.locator('#case-review article[data-case-id="extra"]').get_by_role("button",name="Label true",exact=True).click()
                            latest=record()
                            assert len(latest["actions"]) == 2
                            page.click("#start-revision")
                            assert json.loads(download("#download-original","latest-preview-original.json")) == latest, "starting revision lost a label added after preview"
                            download("#download-record","empty-revision.json")
                            page.goto(prefix + "session.html")
                            upload(policy)
                            expect(page.locator("#import-status")).to_contain_text("Imported locally:")
                            page.click("#open-editor")
                            value=page.locator("#editor-candidates > fieldset").first.get_by_label("Value",exact=True)
                            value.fill("11");value.press("Tab");page.click("#suggest-cases")
                            seen=[]
                            def dismiss_draft(dialog, seen=seen):
                                seen.append(dialog.type);dialog.dismiss()
                            page.once("dialog",dismiss_draft);page.click("#apply-suggestions")
                            assert seen == ["confirm"], "suggestions replaced an edited form without asking"
                            expect(page.locator("#policy-editor")).to_be_visible()
                            expect(value).to_have_value("11")
                            page.once("dialog",lambda dialog:dialog.accept());page.click("#apply-suggestions")
                            expect(page.locator("#policy-editor")).to_be_hidden()
                            expect(page.locator("#start-revision")).to_be_visible()
                            page.once("dialog",lambda dialog:dialog.accept());page.click("#open-editor")
                            expect(page.locator("#start-revision")).to_be_hidden()
                            page.click("#cancel-policy-edit")
                            checks.append(f"{width}: revision activation retains later labels; cancelling suggestions preserves form; reopening safely discards pending preview")
                    except BaseException:
                        page.screenshot(path=str(out/f"{width}-{only or 'all'}-failure.png"), full_page=True)
                        raise
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5);lifecycle("closed")
    assert errors == [] and external == [], (errors, external)
    return {"checks": checks, "console_errors": errors, "external_requests": external,
                "browser_plugin": "not available; existing pinned Playwright",
                "scope": "agent-operated authored software checks; no human usability or intent validation"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["builtin", "unsaved", "sample", "originals", "interleavings"])
    print(json.dumps(run(parser.parse_args().case), indent=2))
