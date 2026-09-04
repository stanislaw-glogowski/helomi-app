import assert from "node:assert";
import { ProfileMemoryManager } from "./memory.js";
import { PromptLoader } from "./prompt.js";

console.log("▶ Testing PromptLoader...");
const loader = new PromptLoader();

// 1. Default prompt resolution (tracked in git)
const defaultPrompt = loader.load("default");
assert.strictEqual(defaultPrompt.profileId, "default");
assert.strictEqual(defaultPrompt.isFallback, false);
assert.ok(defaultPrompt.prompt.includes("helpful"));
assert.ok(defaultPrompt.source.endsWith("default.md"));
console.log("  ✔ Default prompt ('default.md') loaded successfully");

// 2. Fallback to default.md for unknown profile
const missingPrompt = loader.load("unknown_profile_xyz");
assert.strictEqual(missingPrompt.profileId, "unknown_profile_xyz");
assert.strictEqual(missingPrompt.isFallback, true);
assert.ok(missingPrompt.prompt.includes("helpful"));
assert.ok(missingPrompt.source.endsWith("default.md"));
console.log("  ✔ Non-existent profile ('unknown_profile_xyz') fell back to default.md");

// 3. Optional verification of local custom prompts (gitignored)
for (const profile of ["gizmo", "trump", "wojan"]) {
  const custom = loader.load(profile);
  if (!custom.isFallback) {
    console.log(`  ✔ Local custom prompt ('${profile}.md') loaded successfully with TTS tags`);
  }
}

console.log("\n▶ Testing ProfileMemoryManager...");
const mem = new ProfileMemoryManager(10);

// 4. Per-profile isolation
mem.addUserMessage("profile-a", "Hello from A");
mem.addAssistantMessage("profile-a", "Reply A");
assert.strictEqual(mem.getCount("profile-a"), 2);
assert.strictEqual(mem.getCount("profile-b"), 0);
console.log("  ✔ Memory properly isolated per profile");

// 5. Sliding window retention (cap at 10)
for (let i = 1; i <= 15; i++) {
  mem.addUserMessage("profile-b", `User B ${i}`);
}
assert.strictEqual(mem.getCount("profile-b"), 10);
const messagesB = mem.getMessages("profile-b");
assert.strictEqual(messagesB.length, 10);
assert.strictEqual(messagesB[0].content, "User B 6");
assert.strictEqual(messagesB[9].content, "User B 15");
console.log("  ✔ Sliding window preserved exactly 10 latest messages");

// 6. Memory reset
mem.clear("profile-a");
assert.strictEqual(mem.getCount("profile-a"), 0);
assert.strictEqual(mem.getCount("profile-b"), 10);
mem.clear();
assert.strictEqual(mem.getCount("profile-b"), 0);
console.log("  ✔ Memory clear works for individual profile and all profiles");

console.log("\n✨ All tests passed successfully!\n");
