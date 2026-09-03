/**
 * ADR-054 spec 1 — the panel host's public surface.
 *
 * One import site for everything outside `frontend/src/panels/`. Nothing under
 * this directory imports from the two retired loaders
 * (`DataPreview.parts/dynamicPreviewer.ts`,
 * `InteractiveModals.parts/panelModuleLoader.ts`) or from anything else in
 * `App.parts/`: the mounting mechanism is new, not merged.
 *
 * TODO(#2229): wiring this host into the preview surface and the
 *   interactive-modal surface, and deleting the two retired loaders, is spec
 *   task T-007 of docs/specs/adr-054-panel-contract.md, owned by a later agent
 *   in this same issue.
 */

export { PanelHost } from "./PanelHost";
export type { PanelHostHandle, PanelHostProps, PanelHostStatus } from "./PanelHost";

export { validatePanelDescriptor } from "./panelDescriptor";
export type { PanelDescriptor } from "./panelDescriptor";

export { PanelDiagnosticsBanner, PanelErrorSurface } from "./PanelErrorSurface";
export type {
  PanelDiagnostic,
  PanelDiagnosticsBannerProps,
  PanelErrorSurfaceProps,
} from "./PanelErrorSurface";

export {
  PANEL_FRAME_LOAD_TIMEOUT_MS,
  PANEL_FRAME_SANDBOX,
  PANEL_HANDSHAKE_TIMEOUT_MS,
  PANEL_READ_TIMEOUT_MS,
  PANEL_STATE_REQUEST_TIMEOUT_MS,
  createSandboxedPanelFrame,
  isPanelDocumentUrl,
  issuePanelToken,
  mountPanelFrame,
  panelFailure,
} from "./panelFrame";
export type {
  PanelFailure,
  PanelFailureReason,
  PanelFrameConnection,
  PanelFrameFactory,
  PanelFrameHandle,
  PanelFrameMountOptions,
  PanelFrameSpec,
  PanelMountInit,
  PanelMountResult,
  PanelReadOutcome,
  PanelReadResolver,
} from "./panelFrame";

export {
  PANEL_CAPABILITIES,
  PANEL_PRODUCING_TYPES,
  PANEL_PROTOCOL_TYPES,
  capabilitySatisfies,
  createPanelCapabilityGate,
  grantedOutboundTypes,
  isPanelCapability,
} from "./panelCapability";
export type {
  PanelCapabilityDenial,
  PanelCapabilityGate,
  PanelEmitConsumer,
  PanelGateDecision,
} from "./panelCapability";

export {
  HOST_TO_PANEL_TYPES,
  PANEL_MESSAGE_MARKER,
  PANEL_TO_HOST_TYPES,
  hostToPanelMessage,
  isAcceptedApiVersion,
  isHostToPanelMessage,
  isPanelEnvelope,
  isPanelToHostMessage,
  panelToHostMessage,
  parseHostToPanelMessage,
  parsePanelToHostMessage,
  sanitizePanelState,
} from "./panelMessages";
export type {
  HostToPanelMessage,
  HostToPanelPayloads,
  HostToPanelType,
  PanelBindingSnapshot,
  PanelCapability,
  PanelEmitPayload,
  PanelEnvelope,
  PanelErrorPayload,
  PanelHostErrorPayload,
  PanelInitPayload,
  PanelReadLimits,
  PanelReadPayload,
  PanelReadResultPayload,
  PanelReadyPayload,
  PanelStatePayload,
  PanelStateSnapshot,
  PanelToHostMessage,
  PanelToHostPayloads,
  PanelToHostType,
  PanelUpdatePayload,
} from "./panelMessages";
