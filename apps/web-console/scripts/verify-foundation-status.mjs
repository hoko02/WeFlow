import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { renderFoundationStatus } from "../check-dist/foundation-status.js";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const fixturePath = resolve(packageRoot, "../../fixtures/console/redacted-not-ready.json");
const fixture = JSON.parse(readFileSync(fixturePath, "utf8"));
const rendered = renderFoundationStatus(fixture);
const renderedText = JSON.stringify(rendered);

assert.equal(rendered.status, "not-ready");
assert.equal(rendered.mode, "unknown");
assert.equal(rendered.modeLabel, "未知（unknown）");
assert.match(rendered.headline, /^运行状态：未就绪$/);
assert.match(rendered.detail, /^提供方或配置能力被拒绝/);
assert.deepEqual(rendered.policyDenial, {
  capability: "live_provider",
  reasonCode: "replay_only",
});
assert.ok(!renderedText.includes(fixture.blocked_setting));
assert.ok(!renderedText.includes("blocked_setting"));

console.log(
  JSON.stringify({
    report_type: "weflow-console-status-check.v1",
    rendered_status: rendered.status,
    configuration_values_rendered: false,
    chinese_localization_verified: true,
  }),
);
