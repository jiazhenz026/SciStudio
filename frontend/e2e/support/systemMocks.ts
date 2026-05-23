import type { Page, Route } from "@playwright/test";

type JsonBody = Record<string, unknown> | unknown[];

const project = {
  id: "project-e2e",
  name: "E2E Project",
  description: "Browser automation fixture",
  path: "C:\\tmp\\scistudio-e2e",
  created_at: "2026-05-22T12:00:00Z",
  updated_at: "2026-05-22T12:00:00Z",
};

const workflow = {
  id: "main",
  version: "1.0.0",
  description: "Browser e2e workflow",
  nodes: [
    {
      id: "load",
      block_type: "io_block",
      config: { params: {} },
      layout: { x: 50, y: 60 },
    },
    {
      id: "process",
      block_type: "process_block",
      config: { params: {} },
      layout: { x: 280, y: 60 },
    },
  ],
  edges: [{ source: "load:data", target: "process:input" }],
  metadata: {},
};

const blockList = {
  blocks: [
    {
      name: "IO Block",
      type_name: "io_block",
      category: "io",
      description: "Load a fixture table",
      version: "0.1.0",
      input_ports: [],
      output_ports: [{ name: "data", type: "table" }],
    },
    {
      name: "Process Block",
      type_name: "process_block",
      category: "process",
      description: "Transform a fixture table",
      version: "0.1.0",
      input_ports: [{ name: "input", type: "table" }],
      output_ports: [{ name: "output", type: "table" }],
    },
  ],
};

const blockSchema = (typeName: string) => ({
  name: typeName === "io_block" ? "IO Block" : "Process Block",
  type_name: typeName,
  category: typeName === "io_block" ? "io" : "process",
  description: "E2E schema",
  version: "0.1.0",
  input_ports: typeName === "io_block" ? [] : [{ name: "input", type: "table" }],
  output_ports: [{ name: typeName === "io_block" ? "data" : "output", type: "table" }],
  config_schema: { properties: {} },
  type_hierarchy: [],
});

const runSummary = {
  run_id: "run-1",
  workflow_id: "main",
  workflow_git_commit: "1111111111111111111111111111111111111111",
  workflow_dirty: false,
  started_at: "2026-05-22T12:00:00Z",
  finished_at: "2026-05-22T12:00:01Z",
  status: "completed",
  triggered_by: "user",
  parent_run_id: null,
  execute_from_block_id: null,
  block_count: 2,
};

const runDetail = {
  run: runSummary,
  block_executions: [
    {
      block_execution_id: "be-1",
      block_id: "process",
      block_type: "process_block",
      block_version: "0.1.0",
      block_config_resolved: "{}",
      started_at: "2026-05-22T12:00:00Z",
      finished_at: "2026-05-22T12:00:01Z",
      termination: "completed",
      outputs: [
        {
          object_id: "obj-1",
          type_name: "table",
          port_name: "output",
          position: 0,
          storage_path: "data/out.csv",
        },
      ],
    },
  ],
};

const commits = [
  {
    sha: "1111111111111111111111111111111111111111",
    short_sha: "1111111",
    subject: "user: version A",
    author_name: "E2E",
    author_email: "e2e@example.test",
    author_date: "2026-05-22T12:00:00Z",
    parents: [],
    refs: ["HEAD", "main"],
  },
];

async function fulfill(route: Route, body: JsonBody): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function installSystemMocks(page: Page): Promise<void> {
  let projectCreated = false;
  await page.addInitScript(() => {
    class MockWebSocket extends EventTarget {
      static instances: MockWebSocket[] = [];
      readyState = 1;
      url: string;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;

      constructor(url: string) {
        super();
        this.url = url;
        MockWebSocket.instances.push(this);
        setTimeout(() => this.onopen?.(new Event("open")), 0);
      }

      send(): void {}
      close(): void {
        this.readyState = 3;
        this.onclose?.(new CloseEvent("close"));
      }
      emit(payload: unknown): void {
        const event = new MessageEvent("message", { data: JSON.stringify(payload) });
        this.onmessage?.(event);
        this.dispatchEvent(event);
      }
    }

    Object.assign(window, {
      WebSocket: MockWebSocket,
      __scistudioE2EEmitWs(payload: unknown) {
        for (const socket of MockWebSocket.instances) socket.emit(payload);
      },
    });
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (!path.startsWith("/api/")) return route.continue();

    if (path === "/api/projects/" && request.method() === "GET") {
      return fulfill(route, projectCreated ? [project] : []);
    }
    if (path === "/api/projects/" && request.method() === "POST") {
      projectCreated = true;
      return fulfill(route, project);
    }
    if (path === "/api/projects/project-e2e") return fulfill(route, project);
    if (path === "/api/projects/project-e2e/tree") return fulfill(route, { entries: [] });
    if (path === "/api/workflows/list") return fulfill(route, ["main"]);
    if (path === "/api/workflows/main") return fulfill(route, workflow);
    if (path === "/api/workflows/main/execute") {
      return fulfill(route, { workflow_id: "main", status: "started", message: "started" });
    }
    if (path === "/api/workflows/main/execute-from") {
      return fulfill(route, {
        workflow_id: "main",
        status: "started",
        reused_blocks: ["load"],
        reset_blocks: ["process"],
      });
    }
    if (path === "/api/blocks/") return fulfill(route, blockList);
    if (path.startsWith("/api/blocks/") && path.endsWith("/schema")) {
      const typeName = path.split("/")[3];
      return fulfill(route, blockSchema(typeName));
    }
    if (path === "/api/runs") return fulfill(route, { runs: [runSummary] });
    if (path === "/api/runs/run-1") return fulfill(route, runDetail);
    if (path === "/api/data/obj-1/preview") {
      return fulfill(route, {
        ref: "obj-1",
        type_name: "table",
        preview: { columns: ["a"], rows: [{ a: 1 }] },
      });
    }
    if (path === "/api/git/status") {
      return fulfill(route, { branch: "main", dirty: false, ahead: 0, behind: 0, changed_files: [] });
    }
    if (path === "/api/git/branches") return fulfill(route, [{ name: "main", current: true }]);
    if (path === "/api/git/log") return fulfill(route, commits);
    if (path === "/api/git/restore") return fulfill(route, { status: "ok", auto_commit_sha: null });

    return fulfill(route, {});
  });
}

export async function openMockProject(page: Page): Promise<void> {
  await installSystemMocks(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New Project" }).click();
  await page.getByLabel("Project name").fill(project.name);
  await page.locator('input[placeholder*="projects"]').fill("C:\\tmp");
  await page.getByLabel("Description").fill(project.description);
  await page.getByRole("button", { name: "Create project" }).click();
}
