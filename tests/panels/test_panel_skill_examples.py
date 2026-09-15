"""The shipped panel skill's examples use the real descriptor and SDK contracts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.files import validate_external_references
from scistudio.previewers.models import OwnerKind

_HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = new Map();
for (const match of request.html.matchAll(/id="([^"]+)"/g)) {
  elements.set(match[1], {textContent: '', disabled: true});
}
global.window = global;
window.parent = window;
window.location = {href: 'http://panel.test/index.html'};
window.addEventListener = () => {};
window.removeEventListener = () => {};
global.document = {
  documentElement: {style: {setProperty() {}}, dataset: {}},
  getElementById: id => elements.get(id),
};
global.fetch = async () => ({ok: true, json: async () => request.sample});
vm.runInThisContext(request.sdk);
(async () => {
  await window.scistudio.ready();
  const decisions = [];
  if (window.scistudio.writeBack) {
    const submit = window.scistudio.writeBack;
    window.scistudio.writeBack = async value => {
      decisions.push(value);
      return submit(value);
    };
  }
  for (const script of request.html.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
    vm.runInThisContext(script[1]);
  }
  await new Promise(resolve => setImmediate(resolve));
  const confirm = elements.get('confirm');
  const enabled = confirm ? !confirm.disabled : null;
  if (confirm) {
    await confirm.onclick();
    await confirm.onclick(); // an accidental second click must not submit twice
  }
  process.stdout.write(JSON.stringify({
    text: elements.get('text')?.textContent,
    question: elements.get('question')?.textContent,
    status: elements.get('status')?.textContent,
    enabled,
    decisions,
    disabled: confirm?.disabled,
  }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


@pytest.mark.parametrize("context", ["preview", "interactive"])
def test_panel_skill_example_runs_with_sdk_sample(tmp_path: Path, context: str) -> None:
    root = files("scistudio")
    body = (root / "_skills/scistudio/scistudio-write-panel/SKILL.md").read_text(encoding="utf-8")
    example = body.split("## Example: ")[1 if context == "preview" else 2].split("\n## ")[0]
    descriptor_json, sample_json = re.findall(r"```json\n(.*?)\n```", example, re.DOTALL)
    html = re.findall(r"```html\n(.*?)\n```", example, re.DOTALL)[0]
    descriptor = json.loads(descriptor_json)
    directory = tmp_path / descriptor["id"]
    directory.mkdir()
    (directory / "panel.json").write_text(descriptor_json, encoding="utf-8")
    (directory / "index.html").write_text(html, encoding="utf-8")
    (directory / "panel.sample.json").write_text(sample_json, encoding="utf-8")
    parsed, warnings = parse_descriptor(
        directory, owner_kind=OwnerKind.PROJECT, owner_name="skill-example", registered_types=("Text",)
    )
    assert parsed.contexts == (context,)
    assert not warnings
    assert not validate_external_references(directory)

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to exercise the SDK sample examples")
    result = subprocess.run(
        [node, "-e", _HARNESS],
        input=json.dumps(
            {
                "sdk": (root / "panels/sdk/1/scistudio-panel.js").read_text(encoding="utf-8"),
                "html": html,
                "sample": json.loads(sample_json),
            }
        ),
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    observed = json.loads(result.stdout)
    if context == "preview":
        assert observed["text"] == "A sample trace description."
        assert observed["status"] == "Complete text"
        assert not observed["decisions"]
    else:
        assert observed["question"] == "Accept this candidate?"
        assert observed["enabled"]
        assert observed["decisions"] == [{"accepted": True}]
        assert observed["disabled"]
        assert observed["status"] == "Decision submitted"
