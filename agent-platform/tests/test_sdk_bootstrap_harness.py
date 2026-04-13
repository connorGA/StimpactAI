from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from services.sdk_bootstrap import SdkBootstrapPlannedFile, SdkBootstrapStrategy, _apply_strategy, plan_sdk_bootstrap_from_checkout
from services.sdk_bootstrap_harness import (
    SdkBootstrapHarnessTarget,
    compile_safe_change_policy,
    decode_preview_artifact,
    encode_preview_artifact,
)


def test_next_repo_fixture_uses_browser_recipe_with_heartbeat(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package.json",
        {
            "name": "web-app",
            "dependencies": {
                "next": "15.0.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
            },
        },
    )
    app_dir = tmp_path / "src" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "layout.tsx").write_text(
        "export default function RootLayout({ children }) { return <html><body>{children}</body></html>; }\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
    )

    assert plan.strategies
    strategy = plan.strategies[0]
    assert strategy.id.startswith("javascript-next:")
    assert strategy.framework == "Next.js"
    assert any("heartbeat" in step.content.lower() for step in strategy.manual_steps)
    assert any("pingstimpact" in step.content.lower() for step in strategy.manual_steps)
    assert strategy.preview_snippet is not None
    assert "export async function pingStimpact" in strategy.preview_snippet
    assert "scope.pingStimpact = pingStimpact" in strategy.preview_snippet
    assert any("provider" in item.reason.lower() for item in strategy.planned_files)


def test_fastapi_repo_fixture_uses_python_recipe_with_heartbeat(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi==0.111.0\nuvicorn==0.30.0\n", encoding="utf-8")
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="billing-api",
        environment="production",
        base_url="https://stimpact.example.com",
    )

    assert plan.strategies
    strategy = next(item for item in plan.strategies if item.language == "python")
    assert strategy.id.startswith("python-fastapi:")
    assert strategy.framework == "FastAPI"
    assert any("heartbeat" in step.content.lower() for step in strategy.manual_steps)


def test_vite_repo_fixture_surfaces_handled_error_boundaries(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package.json",
        {
            "name": "web-app",
            "dependencies": {
                "vite": "5.4.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
            },
        },
    )
    src_dir = tmp_path / "src"
    lib_dir = src_dir / "lib"
    lib_dir.mkdir(parents=True)
    (src_dir / "main.tsx").write_text(
        'import { createRoot } from "react-dom/client";\nimport App from "./App";\n\ncreateRoot(document.getElementById("root")!).render(<App />);\n',
        encoding="utf-8",
    )
    (lib_dir / "queryClient.ts").write_text(
        'async function throwIfResNotOk(res: Response) {\n  if (!res.ok) {\n    const text = (await res.text()) || res.statusText;\n    throw new Error(`${res.status}: ${text}`);\n  }\n}\n',
        encoding="utf-8",
    )
    (lib_dir / "xanoClient.ts").write_text(
        "export async function xanoRequest<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {\n"
        "  const response = await fetch(endpoint, options);\n"
        "  if (!response.ok) {\n"
        "    throw new Error('boom');\n"
        "  }\n"
        "  return await response.json();\n"
        "}\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
    )

    strategy = next(item for item in plan.strategies if item.id.startswith("javascript-vite-react:"))
    assert any("capturehandlederror" in step.content.lower() for step in strategy.manual_steps)
    assert strategy.preview_snippet is not None
    assert "export async function captureHandledError" in strategy.preview_snippet
    assert "export async function wrapStimpactAsync" in strategy.preview_snippet
    planned_paths = {item.path for item in strategy.planned_files}
    assert "src/lib/queryClient.ts" in planned_paths
    assert "src/lib/xanoClient.ts" in planned_paths


def test_vite_query_client_patch_adds_global_react_query_capture(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package.json",
        {
            "name": "web-app",
            "dependencies": {
                "vite": "5.4.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
                "@tanstack/react-query": "5.0.0",
            },
        },
    )
    src_dir = tmp_path / "src"
    lib_dir = src_dir / "lib"
    lib_dir.mkdir(parents=True)
    (src_dir / "main.tsx").write_text(
        'import { createRoot } from "react-dom/client";\nimport App from "./App";\n\ncreateRoot(document.getElementById("root")!).render(<App />);\n',
        encoding="utf-8",
    )
    (lib_dir / "queryClient.ts").write_text(
        'import { QueryClient, QueryFunction } from "@tanstack/react-query";\n'
        'import { getAuthToken } from "./xanoClient";\n\n'
        'async function throwIfResNotOk(res: Response) {\n'
        '  if (!res.ok) {\n'
        '    const text = (await res.text()) || res.statusText;\n'
        '    throw new Error(`${res.status}: ${text}`);\n'
        "  }\n"
        "}\n\n"
        'export async function apiRequest(method: string, url: string, data?: unknown | undefined): Promise<Response> {\n'
        '  const headers: Record<string, string> = data ? { "Content-Type": "application/json" } : {};\n'
        "  const token = getAuthToken();\n"
        "  if (token) {\n"
        '    headers["Authorization"] = `Bearer ${token}`;\n'
        "  }\n\n"
        "  const res = await fetch(url, {\n"
        "    method,\n"
        "    headers,\n"
        '    body: data ? JSON.stringify(data) : undefined,\n'
        '    credentials: "include",\n'
        "  });\n\n"
        "  await throwIfResNotOk(res);\n"
        "  return res;\n"
        "}\n\n"
        'type UnauthorizedBehavior = "returnNull" | "throw";\n'
        "export const getQueryFn: <T>(options: {\n"
        "  on401: UnauthorizedBehavior;\n"
        "}) => QueryFunction<T> =\n"
        "  ({ on401: unauthorizedBehavior }) =>\n"
        "  async ({ queryKey }) => {\n"
        '    const res = await fetch(queryKey.join("/") as string, {\n'
        '      credentials: "include",\n'
        "    });\n\n"
        '    if (unauthorizedBehavior === "returnNull" && res.status === 401) {\n'
        "      return null;\n"
        "    }\n\n"
        "    await throwIfResNotOk(res);\n"
        "    return await res.json();\n"
        "  };\n\n"
        "export const queryClient = new QueryClient({\n"
        "  defaultOptions: {\n"
        "    queries: {\n"
        '      queryFn: getQueryFn({ on401: "throw" }),\n'
        "      retry: false,\n"
        "    },\n"
        "    mutations: {\n"
        "      retry: false,\n"
        "    },\n"
        "  },\n"
        "});\n",
        encoding="utf-8",
    )
    (lib_dir / "xanoClient.ts").write_text(
        "export function getAuthToken(): string | null {\n"
        "  return localStorage.getItem('xano_auth_token');\n"
        "}\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
    )
    strategy = next(item for item in plan.strategies if item.id.startswith("javascript-vite-react:"))

    _apply_strategy(
        repo_dir=tmp_path,
        strategy=strategy,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
        api_key="stimp_browser_replace_me",
    )
    _apply_strategy(
        repo_dir=tmp_path,
        strategy=strategy,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
        api_key="stimp_browser_replace_me",
    )

    query_client_source = (lib_dir / "queryClient.ts").read_text(encoding="utf-8")
    assert 'import { QueryClient, QueryFunction, MutationCache, QueryCache } from "@tanstack/react-query";' in query_client_source
    assert "captureHandledError" in query_client_source
    assert "async function reportHandledError(input: {" in query_client_source
    assert "const stimpactQueryCache = new QueryCache({" in query_client_source
    assert "const stimpactMutationCache = new MutationCache({" in query_client_source
    assert 'method: "MUTATION"' in query_client_source
    assert 'method: "QUERY"' in query_client_source
    assert "queryCache: stimpactQueryCache" in query_client_source
    assert "mutationCache: stimpactMutationCache" in query_client_source
    assert query_client_source.count("const stimpactMutationCache = new MutationCache({") == 1
    stimpact_source = (src_dir / "stimpact.ts").read_text(encoding="utf-8")
    assert "captureError: (payload: HandledErrorInput) => Promise<void>;" in stimpact_source
    assert "await runtimeClient.captureError(input);" in stimpact_source


def test_vite_query_client_patch_recovers_missing_report_helper(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "package.json",
        {
            "name": "web-app",
            "dependencies": {
                "vite": "5.4.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
                "@tanstack/react-query": "5.0.0",
            },
        },
    )
    src_dir = tmp_path / "src"
    lib_dir = src_dir / "lib"
    lib_dir.mkdir(parents=True)
    (src_dir / "main.tsx").write_text(
        'import { createRoot } from "react-dom/client";\nimport App from "./App";\n\ncreateRoot(document.getElementById("root")!).render(<App />);\n',
        encoding="utf-8",
    )
    (lib_dir / "queryClient.ts").write_text(
        'import { QueryClient, QueryFunction, MutationCache, QueryCache } from "@tanstack/react-query";\n'
        'import { getAuthToken } from "./xanoClient";\n'
        'import { getStimpactClient } from "../stimpact";\n\n'
        'async function throwIfResNotOk(\n'
        '  res: Response,\n'
        '  request?: { method?: string; url?: string },\n'
        ') {\n'
        '  if (!res.ok) {\n'
        '    const text = (await res.text()) || res.statusText;\n'
        '    const error = new Error(`${res.status}: ${text}`);\n'
        '    await reportHandledError({ error, request, response: { status_code: res.status } });\n'
        '    throw error;\n'
        '  }\n'
        '}\n\n'
        'const stimpactQueryCache = new QueryCache({\n'
        '  onError: (error, query) => {\n'
        '    void reportHandledError({ error, request: { method: "QUERY", url: String(query.queryKey?.[0] ?? "react-query") } });\n'
        '  },\n'
        '});\n\n'
        'export const queryClient = new QueryClient({\n'
        '  queryCache: stimpactQueryCache,\n'
        '  mutationCache: new MutationCache(),\n'
        '  defaultOptions: {\n'
        '    queries: {\n'
        '      retry: false,\n'
        '    },\n'
        '  },\n'
        '});\n',
        encoding="utf-8",
    )
    (lib_dir / "xanoClient.ts").write_text(
        "export function getAuthToken(): string | null {\n"
        "  return localStorage.getItem('xano_auth_token');\n"
        "}\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
    )
    strategy = next(item for item in plan.strategies if item.id.startswith("javascript-vite-react:"))

    _apply_strategy(
        repo_dir=tmp_path,
        strategy=strategy,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
        api_key="stimp_browser_replace_me",
    )

    query_client_source = (lib_dir / "queryClient.ts").read_text(encoding="utf-8")
    assert "async function reportHandledError(input: {" in query_client_source
    assert query_client_source.count("async function reportHandledError(input: {") == 1
    assert "await captureHandledError(input);" in query_client_source


def test_vite_strategy_builds_against_packed_sdk_tarball(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sdk_dir = repo_root / "sdk"
    npm_command = "npm.cmd" if os.name == "nt" else "npm"

    _write_json(
        tmp_path / "package.json",
        {
            "name": "web-app",
            "private": True,
            "type": "module",
            "scripts": {
                "build": "tsc --noEmit && vite build",
            },
            "dependencies": {
                "vite": "5.4.20",
                "react": "18.3.1",
                "react-dom": "18.3.1",
                "@tanstack/react-query": "5.60.5",
            },
            "devDependencies": {
                "typescript": "5.6.3",
                "@vitejs/plugin-react": "4.7.0",
                "@types/react": "18.3.11",
                "@types/react-dom": "18.3.1",
            },
        },
    )
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "module": "ES2022",
                    "moduleResolution": "Bundler",
                    "lib": ["ES2022", "DOM"],
                    "jsx": "react-jsx",
                    "strict": True,
                    "esModuleInterop": True,
                    "skipLibCheck": True,
                    "types": ["vite/client"],
                },
                "include": ["src", "vite.config.ts"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "vite.config.ts").write_text(
        'import { defineConfig } from "vite";\nimport react from "@vitejs/plugin-react";\n\nexport default defineConfig({ plugins: [react()] });\n',
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>Fixture</title></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>\n',
        encoding="utf-8",
    )

    src_dir = tmp_path / "src"
    lib_dir = src_dir / "lib"
    lib_dir.mkdir(parents=True)
    (src_dir / "App.tsx").write_text("export default function App() { return <main>Fixture</main>; }\n", encoding="utf-8")
    (src_dir / "main.tsx").write_text(
        'import React from "react";\n'
        'import ReactDOM from "react-dom/client";\n'
        'import { QueryClientProvider } from "@tanstack/react-query";\n'
        'import App from "./App";\n'
        'import { queryClient } from "./lib/queryClient";\n\n'
        'ReactDOM.createRoot(document.getElementById("root")!).render(\n'
        "  <React.StrictMode>\n"
        "    <QueryClientProvider client={queryClient}>\n"
        "      <App />\n"
        "    </QueryClientProvider>\n"
        "  </React.StrictMode>,\n"
        ");\n",
        encoding="utf-8",
    )
    (lib_dir / "queryClient.ts").write_text(
        'import { QueryClient, QueryFunction } from "@tanstack/react-query";\n'
        'import { getAuthToken } from "./xanoClient";\n\n'
        'async function throwIfResNotOk(res: Response) {\n'
        "  if (!res.ok) {\n"
        '    const text = (await res.text()) || res.statusText;\n'
        '    throw new Error(`${res.status}: ${text}`);\n'
        "  }\n"
        "}\n\n"
        'export async function apiRequest(method: string, url: string, data?: unknown | undefined): Promise<Response> {\n'
        '  const headers: Record<string, string> = data ? { "Content-Type": "application/json" } : {};\n'
        "  const token = getAuthToken();\n"
        "  if (token) {\n"
        '    headers["Authorization"] = `Bearer ${token}`;\n'
        "  }\n\n"
        "  const res = await fetch(url, {\n"
        "    method,\n"
        "    headers,\n"
        '    body: data ? JSON.stringify(data) : undefined,\n'
        '    credentials: "include",\n'
        "  });\n\n"
        "  await throwIfResNotOk(res);\n"
        "  return res;\n"
        "}\n\n"
        'type UnauthorizedBehavior = "returnNull" | "throw";\n'
        "export const getQueryFn: <T>(options: {\n"
        "  on401: UnauthorizedBehavior;\n"
        "}) => QueryFunction<T> =\n"
        "  ({ on401: unauthorizedBehavior }) =>\n"
        "  async ({ queryKey }) => {\n"
        '    const res = await fetch(queryKey.join("/") as string, {\n'
        '      credentials: "include",\n'
        "    });\n\n"
        '    if (unauthorizedBehavior === "returnNull" && res.status === 401) {\n'
        "      return null;\n"
        "    }\n\n"
        "    await throwIfResNotOk(res);\n"
        "    return await res.json();\n"
        "  };\n\n"
        "export const queryClient = new QueryClient({\n"
        "  defaultOptions: {\n"
        "    queries: {\n"
        '      queryFn: getQueryFn({ on401: "throw" }),\n'
        "      retry: false,\n"
        "    },\n"
        "    mutations: {\n"
        "      retry: false,\n"
        "    },\n"
        "  },\n"
        "});\n",
        encoding="utf-8",
    )
    (lib_dir / "xanoClient.ts").write_text(
        "export function getAuthToken(): string | null {\n"
        "  return localStorage.getItem('xano_auth_token');\n"
        "}\n\n"
        "export async function xanoRequest<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {\n"
        "  const response = await fetch(endpoint, options);\n"
        "  if (!response.ok) {\n"
        "    throw new Error('boom');\n"
        "  }\n"
        "  return await response.json();\n"
        "}\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
    )
    strategy = next(item for item in plan.strategies if item.id.startswith("javascript-vite-react:"))

    _apply_strategy(
        repo_dir=tmp_path,
        strategy=strategy,
        project_id="project-1",
        service_name="web-app",
        environment="production",
        base_url="https://stimpact.example.com",
        api_key="stimp_browser_replace_me",
    )

    pack_result = subprocess.run(
        [npm_command, "pack", "--pack-destination", str(tmp_path)],
        cwd=sdk_dir,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    tarball_name = pack_result.stdout.strip().splitlines()[-1]
    tarball_path = tmp_path / tarball_name

    package_json_path = tmp_path / "package.json"
    package_data = json.loads(package_json_path.read_text(encoding="utf-8"))
    assert package_data["dependencies"]["@stimpact/sdk"] == "^0.2.0"
    package_data["dependencies"]["@stimpact/sdk"] = f"file:{tarball_path}"
    package_json_path.write_text(json.dumps(package_data, indent=2) + "\n", encoding="utf-8")

    install_result = subprocess.run(
        [npm_command, "install"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    build_result = subprocess.run(
        [npm_command, "run", "build"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert (src_dir / "stimpact.ts").exists()
    assert "captureHandledError" in (src_dir / "stimpact.ts").read_text(encoding="utf-8")
    assert "reportHandledError" in (lib_dir / "queryClient.ts").read_text(encoding="utf-8")
    assert install_result.returncode == 0
    assert build_result.returncode == 0


def test_connected_repo_reference_shape_rewrites_old_get_stimpact_client_usage(tmp_path: Path) -> None:
    client_dir = tmp_path / "client"
    client_dir.mkdir()
    _write_json(
        client_dir / "package.json",
        {
            "name": "rest-express",
            "private": True,
            "type": "module",
            "scripts": {
                "build": "vite build",
            },
            "dependencies": {
                "vite": "5.4.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
                "@tanstack/react-query": "5.0.0",
            },
        },
    )
    src_dir = client_dir / "src"
    lib_dir = src_dir / "lib"
    lib_dir.mkdir(parents=True)
    (src_dir / "main.tsx").write_text(
        'import { createRoot } from "react-dom/client";\nimport App from "./App";\n\ncreateRoot(document.getElementById("root")!).render(<App />);\n',
        encoding="utf-8",
    )
    (src_dir / "stimpact.ts").write_text(
        'import { StimpactClient } from "@stimpact/sdk";\n\n'
        "let installed = false;\n"
        "let stimpactClient: StimpactClient | null = null;\n\n"
        "export function getStimpactClient(): StimpactClient | null {\n"
        "  return stimpactClient;\n"
        "}\n\n"
        "export async function pingStimpact(): Promise<void> {\n"
        "  if (!stimpactClient) {\n"
        "    return;\n"
        "  }\n"
        "  await stimpactClient.ping();\n"
        "}\n\n"
        "export function installStimpact() {\n"
        "  if (installed) {\n"
        "    return;\n"
        "  }\n"
        "  installed = true;\n\n"
        "  const baseUrl = import.meta.env.VITE_STIMPACT_BASE_URL;\n"
        "  const projectId = import.meta.env.VITE_STIMPACT_PROJECT_ID;\n"
        "  const browserKey = import.meta.env.VITE_STIMPACT_BROWSER_KEY;\n"
        '  const service = "Soul Song Service";\n'
        '  const runtimeEnvironment = "production";\n\n'
        "  if (!baseUrl || !projectId || !browserKey || !service) {\n"
        "    return;\n"
        "  }\n\n"
        "  const client = new StimpactClient({\n"
        "    baseUrl,\n"
        "    projectId,\n"
        "    browserKey,\n"
        "    service,\n"
        "    environment: runtimeEnvironment,\n"
        "  });\n"
        "  stimpactClient = client;\n\n"
        "  client.startHeartbeat();\n"
        "  client.registerBrowserAutoCapture();\n"
        "}\n",
        encoding="utf-8",
    )
    (lib_dir / "queryClient.ts").write_text(
        'import { QueryClient, QueryFunction } from "@tanstack/react-query";\n'
        'import { getAuthToken } from "./xanoClient";\n\n'
        'async function throwIfResNotOk(res: Response) {\n'
        "  if (!res.ok) {\n"
        '    const text = (await res.text()) || res.statusText;\n'
        '    throw new Error(`${res.status}: ${text}`);\n'
        "  }\n"
        "}\n\n"
        "export async function apiRequest(\n"
        "  method: string,\n"
        "  url: string,\n"
        "  data?: unknown | undefined,\n"
        "): Promise<Response> {\n"
        '  const headers: Record<string, string> = data ? { "Content-Type": "application/json" } : {};\n'
        "  \n"
        "  const token = getAuthToken();\n"
        "  if (token) {\n"
        '    headers["Authorization"] = `Bearer ${token}`;\n'
        "  }\n\n"
        "  const res = await fetch(url, {\n"
        "    method,\n"
        "    headers,\n"
        '    body: data ? JSON.stringify(data) : undefined,\n'
        '    credentials: "include",\n'
        "  });\n\n"
        "  await throwIfResNotOk(res);\n"
        "  return res;\n"
        "}\n\n"
        'type UnauthorizedBehavior = "returnNull" | "throw";\n'
        "export const getQueryFn: <T>(options: {\n"
        "  on401: UnauthorizedBehavior;\n"
        "}) => QueryFunction<T> =\n"
        "  ({ on401: unauthorizedBehavior }) =>\n"
        "  async ({ queryKey }) => {\n"
        '    const res = await fetch(queryKey.join("/") as string, {\n'
        '      credentials: "include",\n'
        "    });\n\n"
        '    if (unauthorizedBehavior === "returnNull" && res.status === 401) {\n'
        "      return null;\n"
        "    }\n\n"
        "    await throwIfResNotOk(res);\n"
        "    return await res.json();\n"
        "  };\n\n"
        "export const queryClient = new QueryClient({\n"
        "  defaultOptions: {\n"
        "    queries: {\n"
        '      queryFn: getQueryFn({ on401: "throw" }),\n'
        "      refetchInterval: false,\n"
        "      refetchOnWindowFocus: false,\n"
        "      staleTime: Infinity,\n"
        "      retry: false,\n"
        "    },\n"
        "    mutations: {\n"
        "      retry: false,\n"
        "    },\n"
        "  },\n"
        "});\n",
        encoding="utf-8",
    )
    (lib_dir / "xanoClient.ts").write_text(
        "// Xano API Client Configuration\n"
        "const AUTH_BASE_URL = 'https://xvaz-5ufg-teim.n7e.xano.io/api:rVbvzJH3';\n"
        "const DEFAULT_BASE_URL = 'https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H';\n\n"
        "function getBaseUrl(endpoint: string): string {\n"
        "  if (endpoint.startsWith('/auth')) {\n"
        "    return AUTH_BASE_URL;\n"
        "  }\n"
        "  return DEFAULT_BASE_URL;\n"
        "}\n\n"
        "export const AUTH_TOKEN_KEY = 'xano_auth_token';\n\n"
        "export function getAuthToken(): string | null {\n"
        "  return localStorage.getItem(AUTH_TOKEN_KEY);\n"
        "}\n\n"
        "export function setAuthToken(token: string): void {\n"
        "  localStorage.setItem(AUTH_TOKEN_KEY, token);\n"
        "}\n\n"
        "export function removeAuthToken(): void {\n"
        "  localStorage.removeItem(AUTH_TOKEN_KEY);\n"
        "}\n\n"
        "export async function xanoRequest<T = any>(\n"
        "  endpoint: string,\n"
        "  options: RequestInit = {}\n"
        "): Promise<T> {\n"
        "  const token = getAuthToken();\n"
        "  \n"
        "  const headers: Record<string, string> = {\n"
        "    'Content-Type': 'application/json',\n"
        "  };\n\n"
        "  if (options.headers) {\n"
        "    const existingHeaders = new Headers(options.headers);\n"
        "    existingHeaders.forEach((value, key) => {\n"
        "      headers[key] = value;\n"
        "    });\n"
        "  }\n\n"
        "  if (token) {\n"
        "    headers['Authorization'] = `Bearer ${token}`;\n"
        "  }\n\n"
        "  const url = endpoint.startsWith('http') ? endpoint : `${getBaseUrl(endpoint)}${endpoint}`;\n\n"
        "  const response = await fetch(url, {\n"
        "    ...options,\n"
        "    headers,\n"
        "  });\n\n"
        "  if (response.status === 401) {\n"
        "    removeAuthToken();\n"
        "    window.dispatchEvent(new CustomEvent('auth:unauthorized'));\n"
        "    throw new Error('Your session has expired. Please log in again.');\n"
        "  }\n\n"
        "  if (!response.ok) {\n"
        "    const errorText = await response.text();\n"
        "    \n"
        "    let errorMessage: string | null = null;\n"
        "    try {\n"
        "      const errorData = JSON.parse(errorText);\n"
        "      if (errorData.message) {\n"
        "        errorMessage = errorData.message;\n"
        "      }\n"
        "    } catch (parseError) {\n"
        "    }\n"
        "    \n"
        "    if (errorMessage) {\n"
        "      throw new Error(errorMessage);\n"
        "    }\n"
        "    \n"
        "    const statusMessages: Record<number, string> = {\n"
        "      400: 'Invalid request. Please check your input and try again.',\n"
        "      403: 'Access denied. Please check your credentials.',\n"
        "      404: 'The requested resource was not found.',\n"
        "      409: 'This action conflicts with existing data.',\n"
        "      500: 'Server error. Please try again later.',\n"
        "      503: 'Service temporarily unavailable. Please try again later.',\n"
        "    };\n"
        "    \n"
        "    const message = statusMessages[response.status] || `An error occurred (${response.status}). Please try again.`;\n"
        "    throw new Error(message);\n"
        "  }\n\n"
        "  return await response.json();\n"
        "}\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="Soul Song Service",
        environment="production",
        base_url="https://stimpact.example.com",
    )
    strategy = next(item for item in plan.strategies if item.id.startswith("javascript-vite-react:"))

    _apply_strategy(
        repo_dir=tmp_path,
        strategy=strategy,
        project_id="project-1",
        service_name="Soul Song Service",
        environment="production",
        base_url="https://stimpact.example.com",
        api_key="stimp_browser_replace_me",
    )

    helper_source = (src_dir / "stimpact.ts").read_text(encoding="utf-8")
    query_client_source = (lib_dir / "queryClient.ts").read_text(encoding="utf-8")
    xano_client_source = (lib_dir / "xanoClient.ts").read_text(encoding="utf-8")

    assert "export async function captureHandledError" in helper_source
    assert "getStimpactClient" not in query_client_source
    assert "getStimpactClient" not in xano_client_source
    assert 'import { captureHandledError } from "../stimpact";' in query_client_source
    assert 'import { captureHandledError } from "../stimpact";' in xano_client_source
    assert "async function reportHandledError(input: {" in query_client_source
    assert "async function reportHandledError(input: {" in xano_client_source


def test_previously_patched_repo_with_stale_report_handled_error_gets_rewritten(tmp_path: Path) -> None:
    """Simulates the exact user scenario: repo was merged with a previous
    generator run that left a broken ``reportHandledError`` calling
    ``getStimpactClient()`` instead of ``captureHandledError``.  The generator
    must detect this stale pattern and rewrite it."""
    client_dir = tmp_path / "client"
    client_dir.mkdir()
    _write_json(
        client_dir / "package.json",
        {
            "name": "rest-express",
            "private": True,
            "type": "module",
            "scripts": {"build": "vite build"},
            "dependencies": {
                "vite": "5.4.0",
                "react": "19.0.0",
                "react-dom": "19.0.0",
                "@tanstack/react-query": "5.0.0",
                "@stimpact/sdk": "^0.1.0",
            },
        },
    )
    src_dir = client_dir / "src"
    lib_dir = src_dir / "lib"
    lib_dir.mkdir(parents=True)
    (src_dir / "main.tsx").write_text(
        'import { installStimpact } from "./stimpact";\n'
        'import { createRoot } from "react-dom/client";\n'
        'import App from "./App";\n\n'
        "installStimpact();\n\n"
        'createRoot(document.getElementById("root")!).render(<App />);\n',
        encoding="utf-8",
    )
    (src_dir / "stimpact.ts").write_text(
        'import { StimpactClient } from "@stimpact/sdk";\n\n'
        "let installed = false;\n"
        "let stimpactClient: StimpactClient | null = null;\n\n"
        "export function getStimpactClient(): StimpactClient | null {\n"
        "  return stimpactClient;\n"
        "}\n\n"
        "export function installStimpact() {\n"
        "  if (installed) return;\n"
        "  installed = true;\n"
        '  const baseUrl = import.meta.env.VITE_STIMPACT_BASE_URL;\n'
        '  const projectId = import.meta.env.VITE_STIMPACT_PROJECT_ID;\n'
        '  const browserKey = import.meta.env.VITE_STIMPACT_BROWSER_KEY;\n'
        '  const service = "Soul Song Service";\n'
        '  const runtimeEnvironment = "production";\n'
        "  if (!baseUrl || !projectId || !browserKey || !service) return;\n"
        "  const client = new StimpactClient({ baseUrl, projectId, browserKey, service, environment: runtimeEnvironment });\n"
        "  stimpactClient = client;\n"
        "  client.startHeartbeat();\n"
        "  client.registerBrowserAutoCapture();\n"
        "}\n",
        encoding="utf-8",
    )
    (lib_dir / "queryClient.ts").write_text(
        'import { QueryClient, QueryFunction } from "@tanstack/react-query";\n'
        'import { getStimpactClient } from "../stimpact";\n\n'
        "async function reportHandledError(input: {\n"
        "  error: unknown;\n"
        "  request?: { method?: string; url?: string };\n"
        "  response?: { status_code?: number };\n"
        "}) {\n"
        "  const client = getStimpactClient();\n"
        "  if (client) {\n"
        "    void client.captureError({ error: input.error });\n"
        "  }\n"
        "}\n\n"
        'async function throwIfResNotOk(res: Response) {\n'
        "  if (!res.ok) {\n"
        '    const text = (await res.text()) || res.statusText;\n'
        '    throw new Error(`${res.status}: ${text}`);\n'
        "  }\n"
        "}\n\n"
        "export async function apiRequest(\n"
        "  method: string,\n"
        "  url: string,\n"
        "  data?: unknown | undefined,\n"
        "): Promise<Response> {\n"
        '  const headers: Record<string, string> = data ? { "Content-Type": "application/json" } : {};\n'
        "  const res = await fetch(url, {\n"
        "    method,\n"
        "    headers,\n"
        '    body: data ? JSON.stringify(data) : undefined,\n'
        '    credentials: "include",\n'
        "  });\n\n"
        "  await throwIfResNotOk(res);\n"
        "  return res;\n"
        "}\n\n"
        'type UnauthorizedBehavior = "returnNull" | "throw";\n'
        "export const getQueryFn: <T>(options: {\n"
        "  on401: UnauthorizedBehavior;\n"
        "}) => QueryFunction<T> =\n"
        "  ({ on401: unauthorizedBehavior }) =>\n"
        "  async ({ queryKey }) => {\n"
        '    const res = await fetch(queryKey.join("/") as string, {\n'
        '      credentials: "include",\n'
        "    });\n\n"
        '    if (unauthorizedBehavior === "returnNull" && res.status === 401) {\n'
        "      return null;\n"
        "    }\n\n"
        "    await throwIfResNotOk(res);\n"
        "    return await res.json();\n"
        "  };\n\n"
        "export const queryClient = new QueryClient({\n"
        "  defaultOptions: {\n"
        "    queries: {\n"
        '      queryFn: getQueryFn({ on401: "throw" }),\n'
        "      refetchInterval: false,\n"
        "      refetchOnWindowFocus: false,\n"
        "      staleTime: Infinity,\n"
        "      retry: false,\n"
        "    },\n"
        "    mutations: {\n"
        "      retry: false,\n"
        "    },\n"
        "  },\n"
        "});\n",
        encoding="utf-8",
    )

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="Soul Song Service",
        environment="production",
        base_url="https://stimpact.example.com",
    )
    strategy = next(item for item in plan.strategies if item.id.startswith("javascript-vite-react:"))

    _apply_strategy(
        repo_dir=tmp_path,
        strategy=strategy,
        project_id="project-1",
        service_name="Soul Song Service",
        environment="production",
        base_url="https://stimpact.example.com",
        api_key="stimp_browser_replace_me",
    )

    helper_source = (src_dir / "stimpact.ts").read_text(encoding="utf-8")
    query_client_source = (lib_dir / "queryClient.ts").read_text(encoding="utf-8")

    assert "// @stimpact-integration v" in helper_source
    assert "export async function captureHandledError" in helper_source

    assert "getStimpactClient" not in query_client_source, (
        "Stale getStimpactClient references must be purged from boundary files"
    )
    assert 'import { captureHandledError } from "../stimpact";' in query_client_source
    assert "await captureHandledError(input);" in query_client_source, (
        "reportHandledError must delegate to captureHandledError, not getStimpactClient"
    )


def test_unsupported_repo_fixture_stays_manual_only(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Notes only\n", encoding="utf-8")

    plan = plan_sdk_bootstrap_from_checkout(
        repo_dir=tmp_path,
        project_id="project-1",
        service_name="notes",
        environment="production",
        base_url="https://stimpact.example.com",
    )

    assert plan.strategies == []
    assert any("No supported JavaScript or Python" in warning for warning in plan.warnings)


def test_safe_change_policy_blocks_deployment_surface_changes() -> None:
    strategy = SdkBootstrapStrategy(
        id="fixture",
        language="javascript",
        framework="Express",
        summary="Fixture",
        confidence="high",
        pr_supported=True,
        target_subpath=".",
        planned_files=[
            SdkBootstrapPlannedFile(path="Dockerfile", action="update", reason="Rewrite container entrypoint."),
            SdkBootstrapPlannedFile(path="src/index.ts", action="update", reason="Install SDK."),
        ],
    )

    policy = compile_safe_change_policy(strategy=strategy)

    assert "deployment_surface" in policy.prohibited_categories
    assert policy.requires_manual_review is True


def test_preview_artifact_round_trip_preserves_exact_patch_bundle() -> None:
    artifact = encode_preview_artifact(
        secret="test-secret",
        strategy_id="nextjs",
        target=SdkBootstrapHarnessTarget(
            project_id="project-1",
            provider_repository_id="provider-repo-1",
            service="web-app",
            environment="production",
            base_url="https://stimpact.example.com",
        ),
        safe_change_policy=compile_safe_change_policy(
            strategy=SdkBootstrapStrategy(
                id="nextjs",
                language="javascript",
                framework="Next.js",
                summary="Fixture",
                confidence="high",
                pr_supported=True,
                target_subpath=".",
                planned_files=[SdkBootstrapPlannedFile(path="src/app/layout.tsx", action="update", reason="Install SDK.")],
            )
        ),
        patch_diff="diff --git a/file b/file\n+hello\n",
        branch_name="stimpact/sdk-bootstrap-preview",
        credential_kind="api_key",
        framework="Next.js",
        summary="Install SDK",
        entrypoints=["src/app/layout.tsx"],
        attempt={
            "strategy_id": "nextjs",
            "patch_source": "deterministic",
            "patch_generated": True,
            "patch_applied": True,
            "verification": {"status": "passed", "summary": "ok", "command": None, "output": None},
            "preview_available": True,
            "change_request_allowed": True,
            "changed_files": ["src/app/layout.tsx"],
            "warnings": [],
            "failure_stage": None,
            "failure_reason": None,
            "rejection_reason_code": None,
            "attempt_number": 1,
            "candidate_id": "nextjs",
            "generation_duration_ms": 10,
            "apply_duration_ms": 10,
            "verification_duration_ms": 10,
        },
    )

    payload = decode_preview_artifact(secret="test-secret", artifact_id=artifact.artifact_id)

    assert payload["patch_diff"] == "diff --git a/file b/file\n+hello\n"
    assert payload["target"]["service"] == "web-app"
    assert artifact.checksum is not None


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
