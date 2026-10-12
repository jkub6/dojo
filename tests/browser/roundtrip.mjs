// Exercise the shipped decoder over CDP pipes, with HTTP(S) resources blocked.
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { pathToFileURL } from "node:url";

const [chrome, profile, filename, expectation] = process.argv.slice(2);
const browser = spawn(
	chrome,
	[
		"--headless",
		"--no-sandbox",
		"--disable-gpu",
		"--disable-background-networking",
		"--no-first-run",
		`--user-data-dir=${profile}`,
		"--remote-debugging-pipe",
	],
	{ stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"] },
);
let browserErrors = "";
browser.stderr.setEncoding("utf8");
browser.stderr.on("data", (chunk) => {
	browserErrors = (browserErrors + chunk).slice(-8192);
});
let sequence = 0;
let buffer = "";
const pending = new Map();
const events = [];
browser.stdio[4].setEncoding("utf8");
browser.stdio[4].on("data", (chunk) => {
	buffer += chunk;
	let boundary = buffer.indexOf("\0");
	while (boundary >= 0) {
		const message = JSON.parse(buffer.slice(0, boundary));
		buffer = buffer.slice(boundary + 1);
		if (message.id) {
			const request = pending.get(message.id);
			pending.delete(message.id);
			if (message.error)
				request.reject(new Error(JSON.stringify(message.error)));
			else request.resolve(message.result);
		} else events.push(message);
		boundary = buffer.indexOf("\0");
	}
});
function send(method, params = {}, sessionId) {
	const id = ++sequence;
	return new Promise((resolve, reject) => {
		pending.set(id, { resolve, reject });
		browser.stdio[3].write(
			JSON.stringify({ id, method, params, sessionId }) + "\0",
		);
	});
}
const deadline = setTimeout(() => {
	browser.kill("SIGKILL");
	console.error("Browser round trip timed out.", browserErrors);
	process.exitCode = 1;
}, 15000);
try {
	const { targetId } = await send("Target.createTarget", {
		url: "about:blank",
	});
	const { sessionId } = await send("Target.attachToTarget", {
		targetId,
		flatten: true,
	});
	await send("Network.enable", {}, sessionId);
	await send(
		"Network.setBlockedURLs",
		{ urls: ["http://*", "https://*"] },
		sessionId,
	);
	await send("Page.navigate", { url: pathToFileURL(filename).href }, sessionId);
	let observed;
	for (let attempt = 0; attempt < 100; attempt++) {
		const { result } = await send(
			"Runtime.evaluate",
			{
				expression:
					"JSON.stringify({text:document.body?.textContent,executed:document.body?.dataset.executed})",
				returnByValue: true,
			},
			sessionId,
		);
		observed = JSON.parse(result.value);
		if (
			expectation === "success" &&
			observed.executed === "yes" &&
			observed.text.includes("α 東京")
		)
			break;
		if (
			expectation === "corrupt" &&
			observed.text.includes("Unable to open compressed HTML:")
		)
			break;
		await delay(100);
	}
	if (
		expectation === "success"
			? observed.executed !== "yes"
			: !observed.text.includes("Unable to open compressed HTML:")
	) {
		throw new Error(
			`Unexpected restored document: ${JSON.stringify(observed)}`,
		);
	}
	const external = events.filter(
		(event) =>
			event.method === "Network.requestWillBeSent" &&
			/^https?:/.test(event.params.request.url),
	);
	if (external.length)
		throw new Error("Publication attempted external requests.");
} finally {
	clearTimeout(deadline);
	browser.kill("SIGTERM");
}
