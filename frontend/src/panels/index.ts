/**
 * ADR-054 spec 1 — the panel host's public surface.
 *
 * One import site for everything outside `frontend/src/panels/`. The two
 * retired ES-module loaders (`DataPreview.parts/dynamicPanel.ts`,
 * `InteractiveModals.parts/panelModuleLoader.ts`) and the retired host API
 * (`DataPreview.parts/panelHostApi.ts`) no longer exist: T-007 deleted them
 * rather than wrapping them, and `mountPanelFrame` below is the one loader that
 * replaced both (SC-001, SC-002).
 *
 * Nothing under this directory imports from `App.parts/`, from the store, or
 * from the API client. That is what lets the same host mount a panel over a
 * preview session and over a paused interactive block without either surface
 * knowing about the other.
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
  PanelRevertOffer,
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
  PanelHostActionOutcome,
  PanelHostActionPerformer,
  PanelMountInit,
  PanelMountResult,
  PanelReadOutcome,
  PanelReadResolver,
  PanelRequestOutcome,
  PanelResourceResolver,
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
  PANEL_HOST_ACTIONS,
  PANEL_MESSAGE_MARKER,
  PANEL_REQUEST_RESULT_TYPES,
  PANEL_REQUEST_TYPES,
  PANEL_TO_HOST_TYPES,
  hostToPanelMessage,
  isAcceptedApiVersion,
  isHostToPanelMessage,
  isPanelEnvelope,
  isPanelHostAction,
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
  PanelHostAction,
  PanelHostActionPayload,
  PanelHostActionResultPayload,
  PanelHostErrorPayload,
  PanelInitPayload,
  PanelReadLimits,
  PanelReadPayload,
  PanelReadResultPayload,
  PanelReadyPayload,
  PanelRequestType,
  PanelResourcePayload,
  PanelResourceResultPayload,
  PanelStatePayload,
  PanelStateSnapshot,
  PanelToHostMessage,
  PanelToHostPayloads,
  PanelToHostType,
  PanelUpdatePayload,
} from "./panelMessages";
