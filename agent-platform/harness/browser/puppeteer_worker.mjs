import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

import puppeteer from "puppeteer";

let browser = null;
const sessions = new Map();
const MAX_DIAGNOSTIC_EVENTS = 100;

function pushLimited(list, item) {
  list.push(item);
  if (list.length > MAX_DIAGNOSTIC_EVENTS) {
    list.shift();
  }
}

function getSession(sessionId) {
  return sessions.get(sessionId) || null;
}

async function getBrowser() {
  if (!browser) {
    browser = await puppeteer.launch({ headless: true });
  }
  return browser;
}

async function getPage(sessionId, options = {}) {
  const existing = getSession(sessionId);
  if (existing) {
    return existing.page;
  }

  const launchedBrowser = await getBrowser();
  const page = await launchedBrowser.newPage();
  if (options.width && options.height) {
    await page.setViewport({ width: options.width, height: options.height });
  }
  const sessionState = {
    page,
    consoleLogs: [],
    jsExceptions: [],
    networkEvents: [],
  };

  page.on("console", (message) => {
    const location = message.location ? message.location() : null;
    pushLimited(sessionState.consoleLogs, {
      level: message.type(),
      text: message.text(),
      url: location?.url || null,
      line_number: location?.lineNumber ?? null,
    });
  });

  page.on("pageerror", (error) => {
    pushLimited(sessionState.jsExceptions, {
      message: error.message,
      stack: error.stack || null,
    });
  });

  page.on("response", (response) => {
    const request = response.request();
    pushLimited(sessionState.networkEvents, {
      url: response.url(),
      method: request.method(),
      resource_type: request.resourceType(),
      status: response.status(),
      ok: response.ok(),
      failure_text: null,
    });
  });

  page.on("requestfailed", (request) => {
    pushLimited(sessionState.networkEvents, {
      url: request.url(),
      method: request.method(),
      resource_type: request.resourceType(),
      status: null,
      ok: false,
      failure_text: request.failure()?.errorText || "request failed",
    });
  });

  sessions.set(sessionId, sessionState);
  return page;
}

async function handleOpen(payload) {
  const page = await getPage(payload.session_id, {
    width: payload.width,
    height: payload.height,
  });
  await page.goto(payload.url, {
    waitUntil: payload.wait_until,
    timeout: payload.timeout_ms,
  });
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    message: `Opened ${payload.url}`,
  };
}

async function handleClick(payload) {
  const page = await getPage(payload.session_id);
  await page.click(payload.selector);
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    message: `Clicked ${payload.selector}`,
  };
}

async function handleType(payload) {
  const page = await getPage(payload.session_id);
  if (payload.clear_first) {
    await page.$eval(payload.selector, (element) => {
      if ("value" in element) {
        element.value = "";
      }
    });
  }
  await page.click(payload.selector);
  await page.type(payload.selector, payload.text);
  if (payload.press_enter) {
    await page.keyboard.press("Enter");
  }
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    message: `Typed into ${payload.selector}`,
  };
}

async function handleWaitFor(payload) {
  const page = await getPage(payload.session_id);
  if (payload.selector) {
    await page.waitForSelector(payload.selector, { timeout: payload.timeout_ms });
  }
  if (payload.text) {
    await page.waitForFunction(
      (text, selector) => {
        const root = selector ? document.querySelector(selector) : document.body;
        return Boolean(root && root.innerText.includes(text));
      },
      { timeout: payload.timeout_ms },
      payload.text,
      payload.selector || null,
    );
  }
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    message: payload.text
      ? `Observed text ${payload.text}`
      : `Observed selector ${payload.selector}`,
  };
}

async function handleSnapshotDom(payload) {
  const page = await getPage(payload.session_id);
  const domSnapshot = await page.content();
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    dom_snapshot: domSnapshot,
    message: "Captured DOM snapshot",
  };
}

function buildNetworkSummary(sessionState, limit) {
  const recentRequests = sessionState.networkEvents.slice(-limit);
  const failures = sessionState.networkEvents.filter((entry) => entry.failure_text);
  const errorResponses = sessionState.networkEvents.filter(
    (entry) => entry.status !== null && entry.status >= 400,
  );
  return {
    total_requests: sessionState.networkEvents.length,
    total_failures: failures.length,
    total_error_responses: errorResponses.length,
    recent_requests: recentRequests,
  };
}

async function handleScreenshot(payload) {
  const page = await getPage(payload.session_id);
  fs.mkdirSync(path.dirname(payload.output_path), { recursive: true });
  await page.screenshot({
    path: payload.output_path,
    fullPage: payload.full_page,
  });
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    screenshot_path: payload.output_path,
    message: `Captured screenshot to ${payload.output_path}`,
  };
}

async function handleCaptureConsoleLogs(payload) {
  const sessionState = getSession(payload.session_id);
  if (!sessionState) {
    throw new Error(`Unknown browser session: ${payload.session_id}`);
  }
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: sessionState.page.url(),
    console_logs: sessionState.consoleLogs.slice(-payload.limit),
    js_exceptions: sessionState.jsExceptions.slice(-payload.limit),
    message: "Captured console logs and JavaScript exceptions",
  };
}

async function handleCaptureNetworkSummary(payload) {
  const sessionState = getSession(payload.session_id);
  if (!sessionState) {
    throw new Error(`Unknown browser session: ${payload.session_id}`);
  }
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: sessionState.page.url(),
    network_summary: buildNetworkSummary(sessionState, payload.limit),
    message: "Captured network summary",
  };
}

async function handleGetUrl(payload) {
  const page = await getPage(payload.session_id);
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    message: "Retrieved current URL",
  };
}

async function handleCurrentPageState(payload) {
  const sessionState = getSession(payload.session_id);
  if (!sessionState) {
    throw new Error(`Unknown browser session: ${payload.session_id}`);
  }
  const { page } = sessionState;
  const readyState = await page.evaluate(() => document.readyState);
  const title = await page.title();
  const domLength = payload.include_dom ? (await page.content()).length : null;
  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    page_state: {
      current_url: page.url(),
      title,
      ready_state: readyState,
      console_error_count: sessionState.consoleLogs.filter((entry) => entry.level === "error").length,
      js_exception_count: sessionState.jsExceptions.length,
      failed_request_count: sessionState.networkEvents.filter((entry) => entry.failure_text).length,
      dom_length: domLength,
    },
    message: "Captured current page state",
  };
}

async function handleAssertText(payload) {
  const page = await getPage(payload.session_id);
  const matchedText = await page.evaluate(
    ({ selector, exact, text }) => {
      const root = selector ? document.querySelector(selector) : document.body;
      if (!root) {
        return null;
      }
      const actualText = root.innerText || "";
      if (exact) {
        return actualText.trim() === text ? text : null;
      }
      return actualText.includes(text) ? text : null;
    },
    {
      selector: payload.selector || null,
      exact: payload.exact,
      text: payload.text,
    },
  );

  if (!matchedText) {
    return {
      ok: false,
      session_id: payload.session_id,
      current_url: page.url(),
      error: `Expected text not found: ${payload.text}`,
      message: `Expected text not found: ${payload.text}`,
    };
  }

  return {
    ok: true,
    session_id: payload.session_id,
    current_url: page.url(),
    matched_text: matchedText,
    message: `Verified text ${payload.text}`,
  };
}

async function handleClose(payload) {
  const sessionState = getSession(payload.session_id);
  if (sessionState) {
    await sessionState.page.close();
    sessions.delete(payload.session_id);
  }
  return {
    ok: true,
    session_id: payload.session_id,
    message: `Closed session ${payload.session_id}`,
  };
}

async function shutdown() {
  for (const sessionState of sessions.values()) {
    await sessionState.page.close();
  }
  sessions.clear();
  if (browser) {
    await browser.close();
    browser = null;
  }
}

async function dispatch(command) {
  const startedAt = Date.now();
  if (command.action === "shutdown") {
    await shutdown();
    return {
      ok: true,
      provider: "puppeteer",
      action: "shutdown",
      session_id: "shutdown",
      message: "Worker shutdown complete",
      elapsed_ms: Date.now() - startedAt,
      __shutdown: true,
    };
  }

  const payload = command.payload || {};
  let result;
  switch (command.action) {
    case "browser_open":
      result = await handleOpen(payload);
      break;
    case "browser_click":
      result = await handleClick(payload);
      break;
    case "browser_type":
      result = await handleType(payload);
      break;
    case "browser_wait_for":
      result = await handleWaitFor(payload);
      break;
    case "browser_snapshot_dom":
      result = await handleSnapshotDom(payload);
      break;
    case "browser_screenshot":
      result = await handleScreenshot(payload);
      break;
    case "capture_console_logs":
      result = await handleCaptureConsoleLogs(payload);
      break;
    case "capture_network_summary":
      result = await handleCaptureNetworkSummary(payload);
      break;
    case "browser_get_url":
      result = await handleGetUrl(payload);
      break;
    case "current_page_state":
      result = await handleCurrentPageState(payload);
      break;
    case "browser_assert_text":
      result = await handleAssertText(payload);
      break;
    case "dom_snapshot":
      result = await handleSnapshotDom(payload);
      break;
    case "take_screenshot":
      result = await handleScreenshot(payload);
      break;
    case "browser_close":
      result = await handleClose(payload);
      break;
    default:
      result = {
        ok: false,
        session_id: payload.session_id || "unknown",
        error: `Unsupported action: ${command.action}`,
        message: `Unsupported action: ${command.action}`,
      };
  }

  return {
    provider: "puppeteer",
    action: command.action,
    elapsed_ms: Date.now() - startedAt,
    ...result,
  };
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

rl.on("line", async (line) => {
  if (!line.trim()) {
    return;
  }

  let response;
  try {
    const command = JSON.parse(line);
    response = await dispatch(command);
  } catch (error) {
    response = {
      ok: false,
      provider: "puppeteer",
      action: "unknown",
      session_id: "unknown",
      message: error instanceof Error ? error.message : String(error),
      error: error instanceof Error ? error.stack || error.message : String(error),
      elapsed_ms: 0,
    };
  }

  process.stdout.write(`${JSON.stringify(response)}\n`);
  if (response.__shutdown) {
    process.exit(0);
  }
});

rl.on("close", async () => {
  await shutdown();
  process.exit(0);
});
