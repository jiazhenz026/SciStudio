import fs from "node:fs/promises";
import path from "node:path";

export type MinimalWorkflowOptions = {
  inputImagePath: string;
  outputImagePath: string;
  workflowId?: string;
};

function yamlString(value: string): string {
  return JSON.stringify(value);
}

export function minimalImageWorkflowYaml({
  inputImagePath,
  outputImagePath,
  workflowId = "minimal-image-threshold-save",
}: MinimalWorkflowOptions): string {
  return `workflow:
  id: ${workflowId}
  version: "1.0.0"
  description: "E2E fixture: load image, threshold, save mask."
  nodes:
    - id: load_image
      block_type: imaging.load_image
      config:
        path: ${yamlString(inputImagePath)}
    - id: threshold
      block_type: imaging.threshold
      config:
        method: otsu
    - id: save_mask
      block_type: imaging.save_image
      config:
        path: ${yamlString(outputImagePath)}
        capability_id: scistudio-blocks-imaging.image.png.save
  edges:
    - source: load_image:images
      target: threshold:image
    - source: threshold:mask
      target: save_mask:images
  metadata:
    fixture: issue-1384-e2e-discovery
`;
}

export async function writeMinimalImageWorkflowFixture(
  filePath: string,
  options: MinimalWorkflowOptions,
): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, minimalImageWorkflowYaml(options), "utf-8");
}
