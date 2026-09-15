import { describe, expect, it } from "vitest";

import {
  isPathWorkflowIdentity,
  workflowIdentityLabel,
  workflowIdentityPath,
} from "../workflowIdentity";

describe("workflow run identity (#2394)", () => {
  it("recognises the path form the backend gives a subworkflow file", () => {
    expect(isPathWorkflowIdentity("@subworkflows@qc.yaml")).toBe(true);
    expect(isPathWorkflowIdentity("@workflows@nested@main.yml")).toBe(true);
    expect(isPathWorkflowIdentity("main")).toBe(false);
    expect(isPathWorkflowIdentity("@legacy")).toBe(false);
    expect(isPathWorkflowIdentity("@sub@..@x.yaml")).toBe(false);
    expect(isPathWorkflowIdentity(null)).toBe(false);
  });

  it("labels a workflow by its file name", () => {
    expect(workflowIdentityLabel("main")).toBe("main");
    expect(workflowIdentityLabel("@subworkflows@qc.yaml")).toBe("qc");
    expect(workflowIdentityLabel("@subworkflows@qc.swf.yaml")).toBe("qc");
    expect(workflowIdentityLabel("@sub@a%40b%25c.yaml")).toBe("a@b%c");
    expect(workflowIdentityLabel("")).toBe("");
  });

  it("maps an identity back to the file it names", () => {
    expect(workflowIdentityPath("main")).toBe("workflows/main.yaml");
    expect(workflowIdentityPath("@subworkflows@qc.yaml")).toBe("subworkflows/qc.yaml");
    expect(workflowIdentityPath("@sub@a%40b.yaml")).toBe("sub/a@b.yaml");
  });
});
