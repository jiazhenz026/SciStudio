export {};

declare global {
  interface Window {
    __scistudioE2EEmitWs?: (payload: unknown) => void;
  }
}
